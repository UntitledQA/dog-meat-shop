"""Команды бота: /start, /catalog, /orders, /help и подсказка на любое сообщение."""

from __future__ import annotations

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import BotCommand, InlineKeyboardMarkup, Message

from app.bot import keyboards, messages
from app.core.logging import get_logger

logger = get_logger(__name__)

router = Router(name="commands")

#: Список команд для меню Telegram (устанавливается в runner.py).
BOT_COMMANDS = [
    BotCommand(command="start", description="Открыть магазин"),
    BotCommand(command="catalog", description="Каталог мяса"),
    BotCommand(command="orders", description="Мои заказы"),
    BotCommand(command="help", description="Как сделать заказ"),
]


async def safe_answer(
    message: Message,
    text: str,
    keyboard: InlineKeyboardMarkup | None = None,
) -> None:
    """Отправляет ответ, а при отказе Telegram по клавиатуре — повторяет без неё.

    Локально `WEBAPP_URL` часто выглядит как `http://localhost:5173`; такую кнопку
    Telegram отклоняет. Пользователь всё равно должен получить текст, а не молчание.
    """
    try:
        await message.answer(text, reply_markup=keyboard)
        return
    except TelegramBadRequest as exc:
        if keyboard is None:
            logger.warning("bot_answer_failed", error="TelegramBadRequest", detail=str(exc)[:200])
            return
        logger.warning(
            "bot_keyboard_rejected",
            detail=str(exc)[:200],
            hint="Проверьте WEBAPP_URL: Telegram принимает web_app-кнопки только по https",
        )
    except Exception as exc:  # pragma: no cover - сеть/таймауты
        logger.warning("bot_answer_failed", error=type(exc).__name__)
        return

    try:
        await message.answer(text)
    except Exception as exc:  # pragma: no cover - сеть/таймауты
        logger.warning("bot_answer_failed", error=type(exc).__name__)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    logger.info("bot_command", command="start", chat_id=message.chat.id)
    await safe_answer(message, messages.START_TEXT, keyboards.shop_keyboard())


@router.message(Command("catalog"))
async def cmd_catalog(message: Message) -> None:
    logger.info("bot_command", command="catalog", chat_id=message.chat.id)
    await safe_answer(message, messages.CATALOG_TEXT, keyboards.catalog_keyboard())


@router.message(Command("orders"))
async def cmd_orders(message: Message) -> None:
    logger.info("bot_command", command="orders", chat_id=message.chat.id)
    await safe_answer(message, messages.ORDERS_TEXT, keyboards.orders_keyboard())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    logger.info("bot_command", command="help", chat_id=message.chat.id)
    await safe_answer(message, messages.HELP_TEXT, keyboards.shop_keyboard())


@router.message()
async def fallback(message: Message) -> None:
    """Любое другое сообщение — мягкая подсказка, что делать дальше.

    Хендлер зарегистрирован последним, поэтому команды выше до него не доходят.
    """
    logger.info("bot_fallback", chat_id=message.chat.id)
    await safe_answer(message, messages.FALLBACK_TEXT, keyboards.shop_keyboard())


__all__ = ["BOT_COMMANDS", "router", "safe_answer"]
