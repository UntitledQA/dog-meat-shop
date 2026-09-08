"""Единственный экземпляр aiogram-бота на процесс.

Бот создаётся лениво: и веб-приложение (для уведомлений), и `python -m app.bot_main`
(для polling) берут его через `get_bot()`. Если `BOT_TOKEN` не задан — возвращается `None`,
и вызывающий код просто ничего не отправляет. Это нормальный режим для тестов и локальной
разработки без бота: приложение обязано работать и без Telegram.
"""

from __future__ import annotations

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_bot: Bot | None = None
_dispatcher: Dispatcher | None = None


def _build_bot(token: str) -> Bot:
    return Bot(
        token=token,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML,
            link_preview_is_disabled=True,
        ),
    )


def get_bot() -> Bot | None:
    """Общий экземпляр бота или `None`, если токен не настроен.

    Токен НИКОГДА не попадает в логи — логируем только факт отсутствия настройки.
    """
    global _bot

    token = settings.bot_token.strip()
    if not token:
        return None

    if _bot is None:
        _bot = _build_bot(token)
        logger.info("bot_instance_created", mode=settings.bot_mode)
    return _bot


def get_dispatcher() -> Dispatcher:
    """Диспетчер с подключёнными роутерами (создаётся один раз)."""
    global _dispatcher

    if _dispatcher is None:
        from app.bot.handlers import router as commands_router

        _dispatcher = Dispatcher(storage=MemoryStorage())
        _dispatcher.include_router(commands_router)
        logger.info("bot_dispatcher_created")
    return _dispatcher


def is_configured() -> bool:
    """Есть ли у нас рабочий токен бота."""
    return bool(settings.bot_token.strip())


async def shutdown() -> None:
    """Аккуратно закрывает HTTP-сессию бота (вызывать при остановке приложения)."""
    global _bot, _dispatcher

    if _bot is not None:
        try:
            await _bot.session.close()
        except Exception as exc:  # pragma: no cover - закрытие не должно ронять выход
            logger.warning("bot_session_close_failed", error=type(exc).__name__)
        finally:
            _bot = None
            logger.info("bot_stopped")

    _dispatcher = None


def reset() -> None:
    """Сбрасывает кэшированные объекты без сетевых вызовов (для тестов)."""
    global _bot, _dispatcher

    _bot = None
    _dispatcher = None


__all__ = ["get_bot", "get_dispatcher", "is_configured", "reset", "shutdown"]
