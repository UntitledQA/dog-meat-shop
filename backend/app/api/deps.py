"""FastAPI-зависимости: сессия БД и авторизация Telegram.

Это точка интеграции между слоями — сигнатуры менять нельзя.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_db
from app.core.errors import ForbiddenError, UnauthorizedError
from app.core.security import TelegramUserData, parse_and_verify_init_data
from app.models import User
from app.services.auth_service import upsert_user_from_telegram

DbSession = Annotated[AsyncSession, Depends(get_db)]


def _dev_user(dev_telegram_id: str | None) -> TelegramUserData:
    """Пользователь для запуска фронтенда вне Telegram.

    Работает только когда DEV_AUTH_ENABLED=true И ENVIRONMENT != production.
    """
    raw_id = (dev_telegram_id or "").strip() or str(settings.dev_telegram_id)
    try:
        telegram_id = int(raw_id)
    except ValueError:
        raise UnauthorizedError("Некорректный X-Dev-Telegram-Id") from None
    if telegram_id == 0:
        raise UnauthorizedError("DEV_TELEGRAM_ID не задан")
    return TelegramUserData(
        telegram_id=telegram_id,
        username="dev",
        first_name="Разработчик",
        is_dev=True,
    )


async def get_telegram_data(
    request: Request,
    x_telegram_init_data: Annotated[str | None, Header(alias="X-Telegram-Init-Data")] = None,
    x_dev_telegram_id: Annotated[str | None, Header(alias="X-Dev-Telegram-Id")] = None,
) -> TelegramUserData:
    """Извлекает проверенные данные Telegram из заголовка запроса."""
    if x_telegram_init_data:
        data = parse_and_verify_init_data(
            x_telegram_init_data,
            settings.bot_token,
            settings.init_data_ttl_seconds,
        )
        request.state.telegram_id = data.telegram_id
        return data

    if settings.dev_auth_allowed:
        data = _dev_user(x_dev_telegram_id)
        request.state.telegram_id = data.telegram_id
        return data

    raise UnauthorizedError("Откройте приложение через Telegram")


async def get_current_user(
    session: DbSession,
    data: Annotated[TelegramUserData, Depends(get_telegram_data)],
) -> User:
    """Текущий пользователь. Создаётся при первом входе."""
    return await upsert_user_from_telegram(session, data)


async def get_current_admin(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Проверка прав администратора выполняется на бэкенде, а не только в UI."""
    if not (user.is_admin or user.telegram_id in settings.admin_ids):
        raise ForbiddenError("Раздел доступен только администраторам")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(get_current_admin)]
