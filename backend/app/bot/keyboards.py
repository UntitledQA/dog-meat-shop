"""Клавиатуры бота.

Особенность Telegram: кнопку `WebAppInfo` можно повесить только на **https**-ссылку.
В локальной разработке `WEBAPP_URL` обычно `http://localhost:5173`, и попытка отправить
такую кнопку приводит к ошибке Bad Request. Поэтому:

1. `https://…`               → настоящая WebApp-кнопка (магазин открывается внутри Telegram);
2. известен `BOT_USERNAME`   → ссылка `https://t.me/<bot>/?startapp=…` (тоже открывает Mini App);
3. иначе                     → обычная кнопка-ссылка, а если и она невалидна для Telegram,
   хендлер отправит сообщение вовсе без клавиатуры (см. `handlers.safe_answer`).

Так бот не падает ни в одной конфигурации.
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

BTN_SHOP = "🥩 Открыть магазин"
BTN_CATALOG = "🛒 Каталог"
BTN_ORDERS = "📦 Мои заказы"

_warned_about_http = False


def _base_url() -> str:
    return settings.webapp_url.strip().rstrip("/")


def is_webapp_supported() -> bool:
    """WebApp-кнопки Telegram принимает только для https-адресов."""
    return _base_url().lower().startswith("https://")


def webapp_url(path: str = "") -> str:
    """Полный адрес страницы мини-приложения."""
    base = _base_url()
    if not path:
        return base or "/"
    return f"{base}/{path.lstrip('/')}"


def _deeplink(startapp: str | None) -> str | None:
    """Ссылка `t.me`, открывающая мини-приложение (запасной вариант для http-разработки)."""
    username = settings.bot_username.strip().lstrip("@")
    if not username:
        return None
    if startapp:
        return f"https://t.me/{username}?startapp={startapp}"
    return f"https://t.me/{username}"


def _warn_once(url: str) -> None:
    global _warned_about_http
    if not _warned_about_http:
        _warned_about_http = True
        logger.warning(
            "webapp_button_downgraded",
            reason="WEBAPP_URL не https — Telegram не примет web_app-кнопку",
            url=url,
        )


def open_button(
    text: str, path: str = "", startapp: str | None = None
) -> InlineKeyboardButton | None:
    """Кнопка открытия мини-приложения с безопасными запасными вариантами."""
    url = webapp_url(path)

    if url.lower().startswith("https://"):
        return InlineKeyboardButton(text=text, web_app=WebAppInfo(url=url))

    _warn_once(url)

    deeplink = _deeplink(startapp)
    if deeplink:
        return InlineKeyboardButton(text=text, url=deeplink)

    if url.lower().startswith("http://"):
        # Telegram может отклонить локальный адрес — тогда сообщение уйдёт без клавиатуры.
        return InlineKeyboardButton(text=text, url=url)

    return None


def _markup(*buttons: InlineKeyboardButton | None) -> InlineKeyboardMarkup | None:
    rows = [[button] for button in buttons if button is not None]
    if not rows:
        return None
    return InlineKeyboardMarkup(inline_keyboard=rows)


def shop_keyboard() -> InlineKeyboardMarkup | None:
    """Главная кнопка «Открыть магазин» + быстрый переход к заказам."""
    return _markup(
        open_button(BTN_SHOP),
        open_button(BTN_ORDERS, "orders", startapp="orders"),
    )


def catalog_keyboard() -> InlineKeyboardMarkup | None:
    """Кнопка каталога (`?startapp=catalog` для deep-link режима)."""
    return _markup(open_button(BTN_CATALOG, startapp="catalog"))


def orders_keyboard() -> InlineKeyboardMarkup | None:
    """Кнопка списка заказов пользователя."""
    return _markup(
        open_button(BTN_ORDERS, "orders", startapp="orders"),
        open_button(BTN_CATALOG, startapp="catalog"),
    )


def order_link_keyboard() -> InlineKeyboardMarkup | None:
    """Клавиатура под уведомлением о заказе."""
    return _markup(open_button(BTN_ORDERS, "orders", startapp="orders"))


__all__ = [
    "BTN_CATALOG",
    "BTN_ORDERS",
    "BTN_SHOP",
    "catalog_keyboard",
    "is_webapp_supported",
    "open_button",
    "order_link_keyboard",
    "orders_keyboard",
    "shop_keyboard",
    "webapp_url",
]
