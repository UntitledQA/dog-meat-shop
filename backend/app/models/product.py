"""Модель товара (мясо на развес)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, DateTime, Numeric, String, Text, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.enums import ProductCategory

#: Деньги — два знака после запятой, вес — три.
MONEY = Numeric(10, 2)
WEIGHT = Numeric(10, 3)

# native_enum=False -> VARCHAR + CHECK: одна схема для PostgreSQL и SQLite (тесты).
# create_constraint=True обязателен: без него SQLAlchemy 1.4+ CHECK не создаёт.
# values_callable хранит в БД .value (slug вида "horse-meat"), а не имя члена enum.
PRODUCT_CATEGORY_ENUM = SAEnum(
    ProductCategory,
    name="product_category",
    native_enum=False,
    create_constraint=True,
    length=32,
    values_callable=lambda enum: [member.value for member in enum],
)


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("price_per_kg >= 0", name="ck_products_price_non_negative"),
        CheckConstraint("stock_kg >= 0", name="ck_products_stock_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    #: Категория необязательна: у старых товаров её может не быть, и это допустимо.
    category: Mapped[ProductCategory | None] = mapped_column(
        PRODUCT_CATEGORY_ENUM, nullable=True, index=True
    )
    price_per_kg: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    stock_kg: Mapped[Decimal] = mapped_column(WEIGHT, nullable=False, default=Decimal("0"))
    photo_url: Mapped[str | None] = mapped_column(String(512))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    @property
    def in_stock(self) -> bool:
        return self.stock_kg is not None and self.stock_kg > 0

    def __repr__(self) -> str:  # pragma: no cover - отладочное представление
        return f"<Product id={self.id} name={self.name!r} stock={self.stock_kg}>"
