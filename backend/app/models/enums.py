"""Перечисления домена."""

from __future__ import annotations

from enum import Enum


class OrderStatus(str, Enum):
    NEW = "new"
    CONFIRMED = "confirmed"
    PREPARING = "preparing"
    DELIVERING = "delivering"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class DeliveryType(str, Enum):
    DELIVERY = "delivery"
    PICKUP = "pickup"


STATUS_LABELS: dict[OrderStatus, str] = {
    OrderStatus.NEW: "Новый",
    OrderStatus.CONFIRMED: "Подтверждён",
    OrderStatus.PREPARING: "Готовится",
    OrderStatus.DELIVERING: "В доставке",
    OrderStatus.COMPLETED: "Выполнен",
    OrderStatus.CANCELLED: "Отменён",
}

DELIVERY_TYPE_LABELS: dict[DeliveryType, str] = {
    DeliveryType.DELIVERY: "Доставка",
    DeliveryType.PICKUP: "Самовывоз",
}

#: Разрешённые переходы. Отмена возможна из любого нетерминального статуса.
STATUS_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.NEW: {OrderStatus.CONFIRMED, OrderStatus.PREPARING, OrderStatus.CANCELLED},
    OrderStatus.CONFIRMED: {OrderStatus.PREPARING, OrderStatus.DELIVERING, OrderStatus.CANCELLED},
    OrderStatus.PREPARING: {OrderStatus.DELIVERING, OrderStatus.COMPLETED, OrderStatus.CANCELLED},
    OrderStatus.DELIVERING: {OrderStatus.COMPLETED, OrderStatus.CANCELLED},
    OrderStatus.COMPLETED: set(),
    OrderStatus.CANCELLED: set(),
}

TERMINAL_STATUSES = {OrderStatus.COMPLETED, OrderStatus.CANCELLED}


def status_label(status: OrderStatus) -> str:
    return STATUS_LABELS.get(status, status.value)


def can_transition(current: OrderStatus, target: OrderStatus) -> bool:
    return target in STATUS_TRANSITIONS.get(current, set())
