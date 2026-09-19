"""Модели заказа и его позиций."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.enums import DeliveryType, OrderStatus
from app.models.product import MONEY, WEIGHT

if TYPE_CHECKING:
    from app.models.user import User

# native_enum=False -> VARCHAR + CHECK: одна и та же схема работает в PostgreSQL и SQLite.
# create_constraint нужен явно: с SQLAlchemy 1.4 он по умолчанию False, и без него
# колонка остаётся обычным VARCHAR, куда мимо приложения можно записать что угодно.
ORDER_STATUS_ENUM = SAEnum(
    OrderStatus,
    name="order_status",
    native_enum=False,
    create_constraint=True,
    length=20,
    values_callable=lambda enum: [member.value for member in enum],
)
DELIVERY_TYPE_ENUM = SAEnum(
    DeliveryType,
    name="delivery_type",
    native_enum=False,
    create_constraint=True,
    length=20,
    values_callable=lambda enum: [member.value for member in enum],
)

#: Географические координаты. Только Decimal — как деньги и вес, никакого float:
#: двоичная дробь даёт «хвост» вида 55.75581400000001 уже на сериализации.
#: Numeric(9, 6) — шесть знаков после точки (примерно 0.1 м на местности) и три
#: до неё, чего ровно хватает предельной долготе 180.000000.
COORDINATE = Numeric(9, 6)


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("subtotal >= 0", name="ck_orders_subtotal_non_negative"),
        CheckConstraint("delivery_price >= 0", name="ck_orders_delivery_non_negative"),
        CheckConstraint("total >= 0", name="ck_orders_total_non_negative"),
        Index("ix_orders_user_created", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_number: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False
    )

    status: Mapped[OrderStatus] = mapped_column(
        ORDER_STATUS_ENUM, default=OrderStatus.CONFIRMED, nullable=False, index=True
    )
    delivery_type: Mapped[DeliveryType] = mapped_column(DELIVERY_TYPE_ENUM, nullable=False)

    customer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str] = mapped_column(String(32), nullable=False)
    #: Адрес одной строкой — то, что покупатель видит и правит руками.
    address: Mapped[str | None] = mapped_column(String(512))

    #: Разобранный адрес из сервиса подсказок. Все части необязательны: подсказка
    #: может не знать индекс или номер дома, и это не повод отклонять заказ.
    address_city: Mapped[str | None] = mapped_column(String(120))
    address_street: Mapped[str | None] = mapped_column(String(255))
    address_house: Mapped[str | None] = mapped_column(String(32))
    address_postal_code: Mapped[str | None] = mapped_column(String(16))
    address_lat: Mapped[Decimal | None] = mapped_column(COORDINATE)
    address_lon: Mapped[Decimal | None] = mapped_column(COORDINATE)

    delivery_date: Mapped[date | None] = mapped_column(Date)
    comment: Mapped[str | None] = mapped_column(Text)

    subtotal: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    delivery_price: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"))
    total: Mapped[Decimal] = mapped_column(MONEY, nullable=False)

    #: Проставляется ровно один раз при отмене — защита от повторного возврата остатков.
    stock_restored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped[User] = relationship(back_populates="orders", lazy="selectin")
    items: Mapped[list[OrderItem]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="OrderItem.id",
    )

    def __repr__(self) -> str:  # pragma: no cover - отладочное представление
        return f"<Order {self.order_number} status={self.status}>"


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (
        CheckConstraint("weight_kg > 0", name="ck_order_items_weight_positive"),
        CheckConstraint("price_per_kg >= 0", name="ck_order_items_price_non_negative"),
        CheckConstraint("line_total >= 0", name="ck_order_items_total_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), index=True, nullable=False
    )
    #: Товар может быть удалён — заказ обязан сохраниться.
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"), index=True
    )

    #: Снимок на момент оформления: изменение каталога не меняет старые заказы.
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    weight_kg: Mapped[Decimal] = mapped_column(WEIGHT, nullable=False)
    price_per_kg: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    line_total: Mapped[Decimal] = mapped_column(MONEY, nullable=False)

    order: Mapped[Order] = relationship(back_populates="items")

    def __repr__(self) -> str:  # pragma: no cover - отладочное представление
        return f"<OrderItem {self.product_name} {self.weight_kg}кг>"
