"""Тексты бота и уведомлений.

Всё, что пришло от пользователя (имя, телефон, адрес, комментарий, username, название
товара), проходит через `html.escape` — иначе символы `<`, `>`, `&` ломают HTML-разметку
Telegram, а в худшем случае позволяют подмешать чужую разметку в сообщение администратору.
"""

from __future__ import annotations

import html
from datetime import date
from decimal import Decimal
from typing import Iterable

from app.core.config import settings
from app.core.money import format_money, format_weight
from app.models import DELIVERY_TYPE_LABELS, STATUS_LABELS, DeliveryType, Order, OrderStatus

PAYMENT_NOTE = "Оплата при получении"

# ---------------------------------------------------------------------------
# Команды бота
# ---------------------------------------------------------------------------

START_TEXT = (
    "🐕 <b>Мясо для собак</b>\n\n"
    "Привет! Здесь можно заказать свежее мясо для вашего питомца — "
    "говядину, курицу, субпродукты и наборы для натурального кормления.\n\n"
    "🥩 Продаём на развес, от 100 граммов\n"
    "🚚 Доставим по городу или отдадим самовывозом\n"
    "💵 Оплата при получении\n\n"
    "Нажмите кнопку ниже, чтобы открыть магазин и собрать заказ."
)

CATALOG_TEXT = (
    "🛒 <b>Каталог</b>\n\n"
    "Выбирайте мясо, указывайте нужный вес — корзина сама посчитает сумму.\n"
    "Минимальный вес позиции — 100 г, шаг — 100 г."
)

ORDERS_TEXT = (
    "📦 <b>Ваши заказы</b>\n\n"
    "Здесь видно, что вы заказывали и на каком этапе заказ сейчас.\n"
    "О смене статуса мы сообщим сюда же, в этот чат."
)

HELP_TEXT = (
    "❓ <b>Как это работает</b>\n\n"
    "1️⃣ Открываете магазин и выбираете мясо\n"
    "2️⃣ Указываете вес — от 100 г, шагом по 100 г\n"
    "3️⃣ В корзине выбираете доставку или самовывоз, дату и удобное время\n"
    "4️⃣ Оставляете имя и телефон — и оформляете заказ\n"
    "5️⃣ Оплачиваете при получении\n\n"
    "<b>Команды</b>\n"
    "/start — открыть магазин\n"
    "/catalog — перейти в каталог\n"
    "/orders — мои заказы\n"
    "/help — эта подсказка\n\n"
    "Если что-то пошло не так — просто напишите нам сюда, мы на связи."
)

FALLBACK_TEXT = (
    "Я пока умею немного 🙂\n\n"
    "Чтобы выбрать мясо и оформить заказ, откройте магазин кнопкой ниже "
    "или отправьте /start. Подсказка по командам — /help.\n\n"
    "Если нужен живой человек — напишите, что именно вас интересует, "
    "и мы обязательно ответим."
)


# ---------------------------------------------------------------------------
# Вспомогательные форматтеры
# ---------------------------------------------------------------------------


def esc(value: object) -> str:
    """Экранирует пользовательский текст для HTML-разметки Telegram."""
    if value is None:
        return ""
    return html.escape(str(value), quote=False)


def format_date(value: date | None) -> str:
    if value is None:
        return "не указана"
    return value.strftime("%d.%m.%Y")


def _delivery_label(delivery_type: DeliveryType | str) -> str:
    if isinstance(delivery_type, DeliveryType):
        return DELIVERY_TYPE_LABELS.get(delivery_type, delivery_type.value)
    return DELIVERY_TYPE_LABELS.get(DeliveryType(delivery_type), str(delivery_type))


def _status_label(status: OrderStatus | str) -> str:
    if isinstance(status, OrderStatus):
        return STATUS_LABELS.get(status, status.value)
    return STATUS_LABELS.get(OrderStatus(status), str(status))


def _items_block(items: Iterable) -> str:
    lines = []
    for index, item in enumerate(items, start=1):
        lines.append(
            f"{index}. {esc(item.product_name)} — "
            f"{format_weight(item.weight_kg)} × {format_money(item.price_per_kg)}/кг = "
            f"<b>{format_money(item.line_total)}</b>"
        )
    return "\n".join(lines) if lines else "— состав заказа пуст —"


def _totals_block(order: Order) -> str:
    delivery_price: Decimal = order.delivery_price or Decimal("0")
    lines = [f"Товары: {format_money(order.subtotal)}"]
    if order.delivery_type == DeliveryType.DELIVERY:
        lines.append(f"Доставка: {format_money(delivery_price)}")
    else:
        lines.append("Доставка: самовывоз, бесплатно")
    lines.append(f"<b>Итого: {format_money(order.total)}</b>")
    return "\n".join(lines)


def _receiving_block(order: Order, *, for_admin: bool) -> str:
    lines = [f"Способ получения: <b>{_delivery_label(order.delivery_type)}</b>"]

    if order.delivery_type == DeliveryType.DELIVERY:
        lines.append(f"Адрес: {esc(order.address) or 'не указан'}")
    else:
        pickup = settings.pickup_address.strip()
        if pickup:
            lines.append(f"Забрать по адресу: {esc(pickup)}")
        if for_admin and order.address:
            lines.append(f"Адрес в заявке: {esc(order.address)}")

    when = format_date(order.delivery_date)
    if order.delivery_time:
        when = f"{when}, {esc(order.delivery_time)}"
    lines.append(f"Когда: {when}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Уведомления о заказе
# ---------------------------------------------------------------------------


def new_order_for_customer(order: Order) -> str:
    """Подтверждение заказа покупателю."""
    return "\n".join(
        [
            f"✅ <b>Заказ {esc(order.order_number)} принят</b>",
            "",
            "<b>Состав заказа</b>",
            _items_block(order.items),
            "",
            _totals_block(order),
            "",
            _receiving_block(order, for_admin=False),
            f"Статус: <b>{_status_label(order.status)}</b>",
            "",
            f"💵 {PAYMENT_NOTE}",
            "",
            "Спасибо за заказ! Мы свяжемся с вами для подтверждения.",
        ]
    )


def new_order_for_admin(order: Order) -> str:
    """Карточка нового заказа для администратора."""
    username = getattr(order.user, "username", None) if order.user else None
    contact = f"@{esc(username)}" if username else "username не указан"
    telegram_id = getattr(order.user, "telegram_id", None) if order.user else None

    lines = [
        f"🔔 <b>Новый заказ {esc(order.order_number)}</b>",
        "",
        "<b>Состав заказа</b>",
        _items_block(order.items),
        "",
        _totals_block(order),
        "",
        _receiving_block(order, for_admin=True),
        f"Статус: <b>{_status_label(order.status)}</b>",
        "",
        "<b>Покупатель</b>",
        f"Имя: {esc(order.customer_name)}",
        f"Телефон: {esc(order.phone)}",
        f"Telegram: {contact}" + (f" (id {telegram_id})" if telegram_id else ""),
    ]

    if order.comment:
        lines.append(f"Комментарий: {esc(order.comment)}")

    lines += ["", f"💵 {PAYMENT_NOTE}"]
    return "\n".join(lines)


#: Человеческие формулировки под каждый статус (в дополнение к STATUS_LABELS).
STATUS_MESSAGES: dict[OrderStatus, str] = {
    OrderStatus.NEW: "Заказ снова в работе — мы проверим его и свяжемся с вами.",
    OrderStatus.CONFIRMED: "Мы подтвердили заказ и уже готовим его к сборке. 🥩",
    OrderStatus.PREPARING: "Собираем и взвешиваем ваш заказ — скоро будет готов.",
    OrderStatus.DELIVERING: "Заказ передан курьеру и едет к вам. Пожалуйста, будьте на связи. 🚚",
    OrderStatus.COMPLETED: "Заказ выполнен. Спасибо, что заботитесь о своём питомце! 🐕",
    OrderStatus.CANCELLED: "К сожалению, заказ отменён. Если это ошибка — напишите нам, поможем оформить заново.",
}

_STATUS_ICONS: dict[OrderStatus, str] = {
    OrderStatus.NEW: "🆕",
    OrderStatus.CONFIRMED: "✅",
    OrderStatus.PREPARING: "👨‍🍳",
    OrderStatus.DELIVERING: "🚚",
    OrderStatus.COMPLETED: "🎉",
    OrderStatus.CANCELLED: "❌",
}


def order_status_changed(order: Order, new_status: OrderStatus) -> str:
    """Понятное сообщение покупателю о смене статуса."""
    icon = _STATUS_ICONS.get(new_status, "ℹ️")
    lines = [
        f"{icon} <b>Заказ {esc(order.order_number)}: {_status_label(new_status)}</b>",
        "",
        STATUS_MESSAGES.get(new_status, "Статус заказа изменился."),
    ]

    if new_status == OrderStatus.CANCELLED:
        lines += ["", f"Сумма заказа была {format_money(order.total)}. Оплата не потребуется."]
    else:
        lines += ["", f"Сумма заказа: <b>{format_money(order.total)}</b>", f"💵 {PAYMENT_NOTE}"]
        if new_status == OrderStatus.DELIVERING and order.delivery_type == DeliveryType.DELIVERY:
            lines.append(f"Адрес доставки: {esc(order.address) or 'не указан'}")
        if new_status == OrderStatus.PREPARING and order.delivery_type == DeliveryType.PICKUP:
            pickup = settings.pickup_address.strip()
            if pickup:
                lines.append(f"Забрать можно по адресу: {esc(pickup)}")

    return "\n".join(lines)


__all__ = [
    "CATALOG_TEXT",
    "FALLBACK_TEXT",
    "HELP_TEXT",
    "ORDERS_TEXT",
    "PAYMENT_NOTE",
    "START_TEXT",
    "STATUS_MESSAGES",
    "esc",
    "format_date",
    "new_order_for_admin",
    "new_order_for_customer",
    "order_status_changed",
]
