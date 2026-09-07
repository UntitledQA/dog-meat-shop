"""Уведомления в Telegram о заказах.

Главное правило: **эти функции никогда не бросают исключений наружу**. Заказ уже создан
и оплачен «при получении» — падение Telegram, отсутствие сети или заблокированный бот не
должны откатывать транзакцию или ломать HTTP-ответ покупателю. Любая ошибка попадает в
structlog (с `order_id` и типом ошибки, без токенов и текстов сообщений).

Повторная отправка
------------------
Функции идемпотентны по побочным эффектам: они только читают БД и отправляют сообщения,
поэтому их безопасно вызвать повторно — придёт ещё одна копия сообщения, ничего не
сломается. Недоставленные сообщения складываются в очередь в памяти; вызов
`await retry_failed()` пытается отправить их снова (например, из фоновой задачи или из
админ-эндпоинта). Очередь живёт в процессе и не переживает рестарт: для гарантированной
доставки нужна таблица `outbox` в БД — сознательное ограничение MVP.
"""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.bot import messages
from app.bot.bot import get_bot
from app.bot.keyboards import order_link_keyboard
from app.core.config import settings
from app.core.db import SessionLocal
from app.core.logging import get_logger
from app.models import Order, OrderStatus

logger = get_logger(__name__)

#: Сколько недоставленных сообщений храним для повторной отправки.
FAILED_QUEUE_MAXLEN = 500

#: Сколько раз пытаться доставить одно сообщение через `retry_failed()`.
MAX_DELIVERY_ATTEMPTS = 3

#: Пауза между сообщениями, чтобы не упереться в лимиты Telegram (≈30 msg/s).
SEND_DELAY_SECONDS = 0.05

# Ошибки aiogram импортируем мягко: модуль должен импортироваться даже там,
# где aiogram не установлен (например, в урезанном тестовом окружении).
try:  # pragma: no cover - зависит от окружения
    from aiogram.exceptions import (
        TelegramBadRequest,
        TelegramForbiddenError,
        TelegramRetryAfter,
    )

    _PERMANENT_ERRORS: tuple[type[Exception], ...] = (TelegramForbiddenError, TelegramBadRequest)
    _RETRY_AFTER_ERROR: Optional[type[Exception]] = TelegramRetryAfter
except Exception:  # pragma: no cover - aiogram отсутствует
    _PERMANENT_ERRORS = ()
    _RETRY_AFTER_ERROR = None


@dataclass
class PendingMessage:
    """Сообщение, которое не удалось отправить."""

    chat_id: int
    text: str
    order_id: int
    kind: str
    attempts: int = 0
    with_keyboard: bool = True


_failed: deque = deque(maxlen=FAILED_QUEUE_MAXLEN)


# ---------------------------------------------------------------------------
# Внутренние помощники
# ---------------------------------------------------------------------------


async def _load_order(order_id: int) -> Order | None:
    """Читает заказ вместе с позициями и покупателем в собственной сессии."""
    async with SessionLocal() as session:
        return await session.scalar(
            select(Order)
            .options(selectinload(Order.items), selectinload(Order.user))
            .where(Order.id == order_id)
        )


def _recipients_admin() -> list[int]:
    return sorted(settings.admin_ids)


async def _send(pending: PendingMessage) -> bool:
    """Отправляет одно сообщение. Никогда не бросает исключений.

    Возвращает True при успехе. Неуспешные сообщения кладутся в очередь повтора,
    кроме случаев, когда повтор бессмысленен (бот заблокирован, чат не найден).
    """
    bot = get_bot()
    if bot is None:
        # Нормальный режим: тесты и локальный запуск без BOT_TOKEN.
        logger.warning(
            "notification_skipped",
            reason="bot_token_not_configured",
            order_id=pending.order_id,
            kind=pending.kind,
        )
        return False

    pending.attempts += 1
    try:
        await bot.send_message(
            chat_id=pending.chat_id,
            text=pending.text,
            reply_markup=order_link_keyboard() if pending.with_keyboard else None,
            disable_notification=False,
        )
        logger.info(
            "notification_sent",
            order_id=pending.order_id,
            kind=pending.kind,
            chat_id=pending.chat_id,
        )
        return True
    except Exception as exc:
        error = type(exc).__name__

        # Flood control: Telegram сам говорит, через сколько секунд можно повторить.
        if _RETRY_AFTER_ERROR is not None and isinstance(exc, _RETRY_AFTER_ERROR):
            logger.warning(
                "notification_flood_control",
                order_id=pending.order_id,
                kind=pending.kind,
                retry_after=getattr(exc, "retry_after", None),
            )
            if pending.attempts < MAX_DELIVERY_ATTEMPTS:
                _failed.append(pending)
            return False

        permanent = bool(_PERMANENT_ERRORS) and isinstance(exc, _PERMANENT_ERRORS)

        if permanent and pending.with_keyboard:
            # Частая причина Bad Request — web_app-кнопка с не-https адресом.
            # Пробуем ещё раз без клавиатуры: текст важнее кнопки.
            pending.with_keyboard = False
            logger.warning(
                "notification_retry_without_keyboard",
                order_id=pending.order_id,
                kind=pending.kind,
                error=error,
            )
            return await _send(pending)

        logger.error(
            "notification_failed",
            order_id=pending.order_id,
            kind=pending.kind,
            chat_id=pending.chat_id,
            error=error,
            attempts=pending.attempts,
            permanent=permanent,
        )

        if not permanent and pending.attempts < MAX_DELIVERY_ATTEMPTS:
            _failed.append(pending)
        return False


async def _broadcast(items: list[PendingMessage]) -> int:
    """Последовательно отправляет сообщения, не прерываясь на ошибках."""
    delivered = 0
    for index, pending in enumerate(items):
        if index:
            await asyncio.sleep(SEND_DELAY_SECONDS)
        if await _send(pending):
            delivered += 1
    return delivered


# ---------------------------------------------------------------------------
# Публичный интерфейс (зафиксирован контрактом)
# ---------------------------------------------------------------------------


async def notify_new_order(order_id: int) -> None:
    """Сообщает покупателю о принятом заказе и присылает карточку администраторам."""
    try:
        order = await _load_order(order_id)
        if order is None:
            logger.warning("notification_order_missing", order_id=order_id, kind="new_order")
            return

        queue: list[PendingMessage] = []

        customer_chat = getattr(order.user, "telegram_id", None)
        if customer_chat:
            queue.append(
                PendingMessage(
                    chat_id=int(customer_chat),
                    text=messages.new_order_for_customer(order),
                    order_id=order_id,
                    kind="new_order_customer",
                )
            )
        else:
            logger.warning("notification_no_customer_chat", order_id=order_id)

        admin_text = messages.new_order_for_admin(order)
        for admin_id in _recipients_admin():
            if customer_chat and admin_id == int(customer_chat):
                # Админ сам сделал заказ — не дублируем ему два сообщения подряд.
                continue
            queue.append(
                PendingMessage(
                    chat_id=admin_id,
                    text=admin_text,
                    order_id=order_id,
                    kind="new_order_admin",
                )
            )

        if not queue:
            logger.warning("notification_no_recipients", order_id=order_id, kind="new_order")
            return

        delivered = await _broadcast(queue)
        logger.info(
            "notification_new_order_done",
            order_id=order_id,
            delivered=delivered,
            planned=len(queue),
        )
    except Exception as exc:  # noqa: BLE001 - наружу не должно выйти ничего
        logger.error(
            "notification_unexpected_error",
            order_id=order_id,
            kind="new_order",
            error=type(exc).__name__,
        )


async def notify_order_status_changed(order_id: int, new_status: OrderStatus) -> None:
    """Сообщает покупателю о смене статуса заказа понятным текстом."""
    try:
        order = await _load_order(order_id)
        if order is None:
            logger.warning("notification_order_missing", order_id=order_id, kind="status_changed")
            return

        chat_id = getattr(order.user, "telegram_id", None)
        if not chat_id:
            logger.warning("notification_no_customer_chat", order_id=order_id)
            return

        status = new_status if isinstance(new_status, OrderStatus) else OrderStatus(new_status)

        await _send(
            PendingMessage(
                chat_id=int(chat_id),
                text=messages.order_status_changed(order, status),
                order_id=order_id,
                kind=f"status_{status.value}",
            )
        )
    except Exception as exc:  # noqa: BLE001 - наружу не должно выйти ничего
        logger.error(
            "notification_unexpected_error",
            order_id=order_id,
            kind="status_changed",
            error=type(exc).__name__,
        )


async def retry_failed(limit: int = FAILED_QUEUE_MAXLEN) -> int:
    """Повторно отправляет накопившиеся недоставленные уведомления.

    Возвращает число доставленных сообщений. Безопасно вызывать в любой момент:
    ошибки не выбрасываются, а сообщения, исчерпавшие попытки, отбрасываются.
    """
    try:
        if not _failed:
            return 0
        if get_bot() is None:
            logger.warning("notification_retry_skipped", reason="bot_token_not_configured")
            return 0

        batch: list[PendingMessage] = []
        while _failed and len(batch) < limit:
            batch.append(_failed.popleft())

        delivered = await _broadcast(batch)
        logger.info(
            "notification_retry_done",
            delivered=delivered,
            attempted=len(batch),
            still_pending=len(_failed),
        )
        return delivered
    except Exception as exc:  # noqa: BLE001 - наружу не должно выйти ничего
        logger.error("notification_retry_error", error=type(exc).__name__)
        return 0


def pending_count() -> int:
    """Сколько уведомлений ждёт повторной отправки (для диагностики и тестов)."""
    return len(_failed)


def clear_pending() -> None:
    """Очищает очередь повторов (для тестов)."""
    _failed.clear()


__all__ = [
    "MAX_DELIVERY_ATTEMPTS",
    "PendingMessage",
    "clear_pending",
    "notify_new_order",
    "notify_order_status_changed",
    "pending_count",
    "retry_failed",
]
