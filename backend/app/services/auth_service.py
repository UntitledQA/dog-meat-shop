"""Создание/обновление пользователя по проверенным данным Telegram."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import TelegramUserData
from app.models import User


async def upsert_user_from_telegram(session: AsyncSession, data: TelegramUserData) -> User:
    """Возвращает пользователя, создавая или обновляя его профиль.

    Права администратора берутся исключительно из ADMIN_TELEGRAM_IDS и
    синхронизируются при каждом входе — удаление ID из списка снимает права.
    """
    is_admin = data.telegram_id in settings.admin_ids

    user = await session.scalar(select(User).where(User.telegram_id == data.telegram_id))

    if user is None:
        user = User(
            telegram_id=data.telegram_id,
            username=data.username,
            first_name=data.first_name,
            last_name=data.last_name,
            is_admin=is_admin,
        )
        session.add(user)
        try:
            await session.commit()
        except IntegrityError:
            # Гонка параллельных первых запросов: пользователь уже создан другим запросом.
            await session.rollback()
            user = await session.scalar(
                select(User).where(User.telegram_id == data.telegram_id)
            )
            if user is None:  # pragma: no cover - защитная ветка
                raise
        else:
            await session.refresh(user)
            return user

    changed = False
    for field, value in (
        ("username", data.username),
        ("first_name", data.first_name),
        ("last_name", data.last_name),
    ):
        if value is not None and getattr(user, field) != value:
            setattr(user, field, value)
            changed = True

    if user.is_admin != is_admin:
        user.is_admin = is_admin
        changed = True

    if changed:
        await session.commit()
        await session.refresh(user)

    return user
