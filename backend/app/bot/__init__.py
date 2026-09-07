"""Telegram-бот на aiogram 3.

Точка входа для локального запуска: `python -m app.bot_main`.

Здесь только «тонкий» слой Telegram: экземпляр бота, клавиатуры, тексты и команды.
Бизнес-логика заказов живёт в `app/services`, уведомления — в
`app/services/notification_service.py`.
"""

from app.bot.bot import get_bot, get_dispatcher, is_configured, shutdown

__all__ = ["get_bot", "get_dispatcher", "is_configured", "shutdown"]
