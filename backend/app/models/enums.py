"""Перечисления домена."""

from __future__ import annotations

from enum import Enum


class OrderStatus(str, Enum):
    CONFIRMED = "confirmed"
    DELIVERING = "delivering"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class DeliveryType(str, Enum):
    DELIVERY = "delivery"
    PICKUP = "pickup"


class ProductCategory(str, Enum):
    """Категория товара каталога.

    Значения — латинские slug (как у OrderStatus/DeliveryType): в БД хранится slug,
    покупателю показывается русская подпись из CATEGORY_LABELS. Набор фиксированный;
    новая категория добавляется сюда И в миграцию (VARCHAR + CHECK). Порядок членов
    задаёт порядок отображения в каталоге и админке.
    """

    BEEF = "beef"
    VEAL = "veal"
    HORSE_MEAT = "horse-meat"
    DUCK = "duck"
    FISH = "fish"
    DRIED_TREATS = "dried-treats"


STATUS_LABELS: dict[OrderStatus, str] = {
    OrderStatus.CONFIRMED: "Подтверждён",
    OrderStatus.DELIVERING: "Доставляется",
    OrderStatus.COMPLETED: "Готово",
    OrderStatus.CANCELLED: "Отменён",
}

DELIVERY_TYPE_LABELS: dict[DeliveryType, str] = {
    DeliveryType.DELIVERY: "Доставка",
    DeliveryType.PICKUP: "Самовывоз",
}

#: Русские подписи категорий для витрины, бота и админки.
CATEGORY_LABELS: dict[ProductCategory, str] = {
    ProductCategory.BEEF: "Говядина",
    ProductCategory.VEAL: "Телятина",
    ProductCategory.HORSE_MEAT: "Конина",
    ProductCategory.DUCK: "Утка",
    ProductCategory.FISH: "Рыба",
    ProductCategory.DRIED_TREATS: "Сушёные лакомства",
}


def category_label(category: ProductCategory) -> str:
    """Русское название категории; для неизвестного значения — сам slug."""
    return CATEGORY_LABELS.get(category, category.value)

#: Разрешённые переходы.
#:
#: Заказ сразу создаётся подтверждённым: отдельного «нового» статуса нет.
#: Самовывоз:  Подтверждён -> Готово.
#: Доставка:   Подтверждён -> Доставляется -> Готово.
#: Переход сразу в «Готово» разрешён и для доставки — курьер мог отдать заказ
#: без промежуточной отметки. Отмена возможна из любого нетерминального статуса
#: и остаётся единственным способом отклонить заказ, вернув остаток на склад.
STATUS_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.CONFIRMED: {
        OrderStatus.DELIVERING,
        OrderStatus.COMPLETED,
        OrderStatus.CANCELLED,
    },
    OrderStatus.DELIVERING: {OrderStatus.COMPLETED, OrderStatus.CANCELLED},
    OrderStatus.COMPLETED: set(),
    OrderStatus.CANCELLED: set(),
}

TERMINAL_STATUSES = {OrderStatus.COMPLETED, OrderStatus.CANCELLED}

#: Статусы, осмысленные только для доставки.
DELIVERY_ONLY_STATUSES = {OrderStatus.DELIVERING}


def status_label(status: OrderStatus) -> str:
    return STATUS_LABELS.get(status, status.value)


def can_transition(current: OrderStatus, target: OrderStatus) -> bool:
    return target in STATUS_TRANSITIONS.get(current, set())


def is_allowed_for_delivery_type(status: OrderStatus, delivery_type: DeliveryType) -> bool:
    """Подходит ли статус способу получения.

    «Доставляется» бессмысленно для самовывоза: забирают сами, везти некому.
    """
    if status in DELIVERY_ONLY_STATUSES:
        return delivery_type == DeliveryType.DELIVERY
    return True


def allowed_transitions(
    current: OrderStatus, delivery_type: DeliveryType
) -> list[OrderStatus]:
    """Куда можно перевести заказ с учётом способа получения."""
    targets = STATUS_TRANSITIONS.get(current, set())
    return [
        status
        for status in OrderStatus
        if status in targets and is_allowed_for_delivery_type(status, delivery_type)
    ]
