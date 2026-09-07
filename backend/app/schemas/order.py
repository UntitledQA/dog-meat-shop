"""Схемы заказа."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from app.models.enums import DeliveryType, OrderStatus, status_label
from app.schemas.common import MoneyDecimal, OrderWeight, PhoneStr, ShortText, WeightDecimal
from app.schemas.user import UserOut

__all__ = [
    "AdminOrderOut",
    "OrderCreate",
    "OrderItemCreate",
    "OrderItemOut",
    "OrderOut",
    "OrderStatusUpdate",
]

#: Оплата в проекте одна — наличными/картой при получении.
PAYMENT_METHOD = "cash_on_delivery"

#: Верхняя граница позиций в одном заказе — защита от «мусорных» корзин.
MAX_ORDER_ITEMS = 50


class OrderItemCreate(BaseModel):
    """Позиция корзины. Цена не передаётся — бэкенд берёт её из БД."""

    model_config = ConfigDict(extra="forbid")

    product_id: int = Field(gt=0, description="Идентификатор товара")
    weight_kg: OrderWeight = Field(description="Вес, кг: >= 0.100 и кратно 0.100")


class OrderCreate(BaseModel):
    """Оформление заказа."""

    model_config = ConfigDict(extra="forbid")

    items: list[OrderItemCreate] = Field(
        min_length=1,
        max_length=MAX_ORDER_ITEMS,
        description="Позиции заказа, от 1 до 50",
    )
    delivery_type: DeliveryType = Field(description="Доставка или самовывоз")
    customer_name: ShortText = Field(description="Имя получателя")
    phone: PhoneStr = Field(description="Телефон для связи")
    address: str | None = Field(default=None, max_length=512, description="Адрес доставки")
    delivery_date: date | None = Field(default=None, description="Желаемая дата")
    delivery_time: str | None = Field(default=None, max_length=64, description="Интервал времени")
    comment: str | None = Field(default=None, max_length=2000, description="Комментарий")

    @model_validator(mode="after")
    def _check_consistency(self) -> OrderCreate:
        if self.delivery_type == DeliveryType.DELIVERY and not (self.address or "").strip():
            raise ValueError("Для доставки нужно указать адрес")

        seen: set[int] = set()
        duplicates: set[int] = set()
        for item in self.items:
            if item.product_id in seen:
                duplicates.add(item.product_id)
            seen.add(item.product_id)
        if duplicates:
            ids = ", ".join(str(pid) for pid in sorted(duplicates))
            raise ValueError(
                f"Товар не может встречаться в заказе дважды (id: {ids}) — "
                "объедините позиции в одну и укажите суммарный вес"
            )
        return self


class OrderStatusUpdate(BaseModel):
    """Смена статуса заказа администратором."""

    model_config = ConfigDict(extra="forbid")

    status: OrderStatus = Field(description="Новый статус заказа")


class OrderItemOut(BaseModel):
    """Позиция заказа — снимок товара на момент оформления."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int | None = Field(default=None, description="null, если товар удалён")
    product_name: str
    weight_kg: WeightDecimal
    price_per_kg: MoneyDecimal
    line_total: MoneyDecimal


class OrderOut(BaseModel):
    """Заказ покупателя."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    order_number: str = Field(description="Формат ORD-YYYYMMDD-NNNNN")
    status: OrderStatus
    delivery_type: DeliveryType
    customer_name: str
    phone: str
    address: str | None = None
    delivery_date: date | None = None
    delivery_time: str | None = None
    comment: str | None = None
    subtotal: MoneyDecimal = Field(description="Сумма позиций")
    delivery_price: MoneyDecimal = Field(description="Стоимость доставки")
    total: MoneyDecimal = Field(description="Итого к оплате")
    items: list[OrderItemOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    @computed_field(description="Человекочитаемый статус")  # type: ignore[prop-decorator]
    @property
    def status_label(self) -> str:
        return status_label(self.status)

    @computed_field(description="Способ оплаты")  # type: ignore[prop-decorator]
    @property
    def payment_method(self) -> str:
        return PAYMENT_METHOD


class AdminOrderOut(OrderOut):
    """Заказ в админке: то же самое плюс профиль покупателя."""

    user: UserOut = Field(description="Покупатель")
