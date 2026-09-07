"""Схемы товара."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.schemas.common import (
    MoneyDecimal,
    NonNegativeMoney,
    NonNegativeWeight,
    ShortText,
    WeightDecimal,
)

__all__ = ["ProductCreate", "ProductOut", "ProductPhotoOut", "ProductUpdate"]


class ProductOut(BaseModel):
    """Товар для витрины и админки. Все Decimal уходят строками."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    price_per_kg: MoneyDecimal = Field(description="Цена за килограмм")
    stock_kg: WeightDecimal = Field(description="Остаток на складе, кг")
    photo_url: str | None = Field(default=None, description="Относительный путь к фото")
    is_active: bool = Field(description="Показывается ли товар в каталоге")
    created_at: datetime
    updated_at: datetime

    @computed_field(description="Есть ли товар в наличии")  # type: ignore[prop-decorator]
    @property
    def in_stock(self) -> bool:
        return self.stock_kg > 0


class ProductCreate(BaseModel):
    """Создание товара администратором."""

    model_config = ConfigDict(extra="forbid")

    name: ShortText = Field(description="Название товара")
    description: str | None = Field(default=None, max_length=4000)
    price_per_kg: NonNegativeMoney = Field(description="Цена за килограмм, >= 0")
    stock_kg: NonNegativeWeight = Field(default=Decimal("0"), description="Остаток, кг, >= 0")
    photo_url: str | None = Field(default=None, max_length=512)
    is_active: bool = Field(default=True)


class ProductUpdate(BaseModel):
    """Частичное обновление товара: передаются только изменяемые поля."""

    model_config = ConfigDict(extra="forbid")

    name: ShortText | None = Field(default=None)
    description: str | None = Field(default=None, max_length=4000)
    price_per_kg: NonNegativeMoney | None = Field(default=None)
    stock_kg: NonNegativeWeight | None = Field(default=None)
    photo_url: str | None = Field(default=None, max_length=512)
    is_active: bool | None = Field(default=None)


class ProductPhotoOut(BaseModel):
    """Ответ загрузки изображения без привязки к товару."""

    photo_url: str = Field(description="Относительный путь вида /uploads/ab12.jpg")
