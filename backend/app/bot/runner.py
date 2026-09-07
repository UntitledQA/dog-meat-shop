"""Запуск бота: polling для разработки и управление webhook для продакшена."""

from __future__ import annotations

from aiogram.exceptions import TelegramAPIError
from aiogram.types import BotCommandScopeAllPrivateChats

from app.bot.bot import get_bot, get_dispatcher, shutdown
from app.bot.handlers import BOT_COMMANDS
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def webhook_url() -> str:
    """Полный адрес webhook: `PUBLIC_BASE_URL` + `WEBHOOK_PATH`."""
    base = settings.public_base_url.strip().rstrip("/")
    path = settings.webhook_path.strip()
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{base}{path}"


async def setup_bot_commands() -> None:
    """Показывает список команд в меню Telegram."""
    bot = get_bot()
    if bot is None:
        return
    try:
        await bot.set_my_commands(BOT_COMMANDS, scope=BotCommandScopeAllPrivateChats())
        logger.info("bot_commands_set", count=len(BOT_COMMANDS))
    except TelegramAPIError as exc:
        logger.warning("bot_commands_failed", error=type(exc).__name__, detail=str(exc)[:200])


async def run_polling() -> None:
    """Long polling. Блокирует до Ctrl+C / SIGTERM, затем корректно закрывает сессию."""
    bot = get_bot()
    if bot is None:
        logger.error("bot_not_configured", hint="Задайте BOT_TOKEN в .env")
        return

    dispatcher = get_dispatcher()

    try:
        me = await bot.get_me()
        logger.info("bot_started", mode="polling", username=me.username, bot_id=me.id)
    except TelegramAPIError as exc:
        # Неверный токен и сетевые проблемы видно сразу, а не через минуту молчания.
        logger.error("bot_get_me_failed", error=type(exc).__name__, detail=str(exc)[:200])
        await shutdown()
        return

    await setup_bot_commands()

    try:
        # Polling и webhook взаимоисключающи: снимаем ранее выставленный webhook.
        await bot.delete_webhook(drop_pending_updates=True)
    except TelegramAPIError as exc:
        logger.warning("bot_delete_webhook_failed", error=type(exc).__name__)

    try:
        await dispatcher.start_polling(
            bot,
            allowed_updates=dispatcher.resolve_used_update_types(),
            handle_signals=True,
        )
    except (KeyboardInterrupt, SystemExit):  # pragma: no cover - ручная остановка
        logger.info("bot_polling_interrupted")
    finally:
        await shutdown()
        logger.info("bot_polling_stopped")


async def setup_webhook(url: str | None = None) -> bool:
    """Регистрирует webhook в Telegram. Возвращает True при успехе.

    `WEBHOOK_SECRET` передаётся как `secret_token`: Telegram будет присылать его в
    заголовке `X-Telegram-Bot-Api-Secret-Token`, и обработчик обязан его сверять —
    иначе webhook-эндпоинт может дёрнуть кто угодно.
    """
    bot = get_bot()
    if bot is None:
        logger.error("bot_not_configured", hint="Задайте BOT_TOKEN в .env")
        return False

    target = (url or webhook_url()).strip()
    if not target.lower().startswith("https://"):
        logger.error("webhook_url_not_https", url=target, hint="Telegram принимает только https")
        return False

    dispatcher = get_dispatcher()
    secret = settings.webhook_secret.strip() or None
    if secret is None:
        logger.warning(
            "webhook_secret_missing",
            hint="Задайте WEBHOOK_SECRET, иначе эндпоинт webhook не защищён",
        )

    try:
        await bot.set_webhook(
            url=target,
            secret_token=secret,
            drop_pending_updates=True,
            allowed_updates=dispatcher.resolve_used_update_types(),
            max_connections=40,
        )
    except TelegramAPIError as exc:
        logger.error("webhook_set_failed", error=type(exc).__name__, detail=str(exc)[:200])
        return False

    await setup_bot_commands()
    logger.info("webhook_set", url=target, secret_configured=secret is not None)
    return True


async def delete_webhook(drop_pending_updates: bool = False) -> bool:
    """Снимает webhook (например, перед переходом на polling)."""
    bot = get_bot()
    if bot is None:
        return False
    try:
        await bot.delete_webhook(drop_pending_updates=drop_pending_updates)
    except TelegramAPIError as exc:
        logger.error("webhook_delete_failed", error=type(exc).__name__, detail=str(exc)[:200])
        return False
    logger.info("webhook_deleted")
    return True


async def webhook_info() -> dict | None:
    """Текущее состояние webhook — удобно для диагностики."""
    bot = get_bot()
    if bot is None:
        return None
    try:
        info = await bot.get_webhook_info()
    except TelegramAPIError as exc:
        logger.error("webhook_info_failed", error=type(exc).__name__)
        return None
    return {
        "url": info.url,
        "pending_update_count": info.pending_update_count,
        "last_error_message": info.last_error_message,
        "has_custom_certificate": info.has_custom_certificate,
    }


__all__ = [
    "delete_webhook",
    "run_polling",
    "setup_bot_commands",
    "setup_webhook",
    "webhook_info",
    "webhook_url",
]
