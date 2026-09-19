"""Pydantic-схемы API. Все Decimal сериализуются строками."""

from app.schemas.address import (
    DEFAULT_SUGGEST_LIMIT,
    MAX_QUERY_LENGTH,
    MAX_SUGGEST_LIMIT,
    MIN_QUERY_LENGTH,
    AddressSuggestion,
    AddressSuggestionsOut,
)
from app.schemas.common import (
    DEFAULT_PAGE_LIMIT,
    MAX_PAGE_LIMIT,
    AppSettingsOut,
    MoneyDecimal,
    NonNegativeMoney,
    NonNegativeWeight,
    OrderWeight,
    Page,
    PhoneStr,
    ShortText,
    WeightDecimal,
)
from app.schemas.order import (
    MAX_ORDER_ITEMS,
    PAYMENT_METHOD,
    AdminOrderOut,
    OrderCreate,
    OrderItemCreate,
    OrderItemOut,
    OrderOut,
    OrderStatusUpdate,
)
from app.schemas.product import ProductCreate, ProductOut, ProductPhotoOut, ProductUpdate
from app.schemas.user import UserOut

__all__ = [
    "DEFAULT_PAGE_LIMIT",
    "DEFAULT_SUGGEST_LIMIT",
    "MAX_ORDER_ITEMS",
    "MAX_PAGE_LIMIT",
    "MAX_QUERY_LENGTH",
    "MAX_SUGGEST_LIMIT",
    "MIN_QUERY_LENGTH",
    "PAYMENT_METHOD",
    "AddressSuggestion",
    "AddressSuggestionsOut",
    "AdminOrderOut",
    "AppSettingsOut",
    "MoneyDecimal",
    "NonNegativeMoney",
    "NonNegativeWeight",
    "OrderCreate",
    "OrderItemCreate",
    "OrderItemOut",
    "OrderOut",
    "OrderStatusUpdate",
    "OrderWeight",
    "Page",
    "PhoneStr",
    "ProductCreate",
    "ProductOut",
    "ProductPhotoOut",
    "ProductUpdate",
    "ShortText",
    "UserOut",
    "WeightDecimal",
]
