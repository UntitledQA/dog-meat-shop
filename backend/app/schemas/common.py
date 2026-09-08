"""Общие типы и схемы для всего API.

Ключевое правило проекта: **все Decimal уезжают в JSON строками**
(`"890.00"`, `"12.500"`), чтобы JavaScript не терял точность на больших числах.
На входе принимается и строка, и число — приводим к Decimal через str.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Annotated, Any, Generic, TypeVar

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PlainSerializer,
    StringConstraints,
)

from app.core.money import (
    MIN_WEIGHT,
    WEIGHT_STEP,
    is_valid_weight_step,
    round_money,
    round_weight,
)

__all__ = [
    "DEFAULT_PAGE_LIMIT",
    "MAX_PAGE_LIMIT",
    "AppSettingsOut",
    "MoneyDecimal",
    "NonNegativeMoney",
    "NonNegativeWeight",
    "OrderWeight",
    "Page",
    "PhoneStr",
    "ShortText",
    "WeightDecimal",
]

#: Пагинация одинакова во всех списках API.
DEFAULT_PAGE_LIMIT = 20
MAX_PAGE_LIMIT = 100


def _coerce_decimal(value: Any) -> Any:
    """Принимает строку/int/float/Decimal и возвращает Decimal.

    float переводится через str — иначе в значение утекает двоичная погрешность.
    """
    if value is None or isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        raise ValueError("Ожидалось число, а не логическое значение")
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, str):
        # Убираем любые пробельные разделители разрядов и принимаем запятую как разделитель.
        text = "".join(ch for ch in value if not ch.isspace()).replace(",", ".")
        if not text:
            raise ValueError("Значение не может быть пустым")
        try:
            return Decimal(text)
        except InvalidOperation:
            raise ValueError("Некорректное числовое значение") from None
    return value


#: Границы столбцов Numeric(10, 2) и Numeric(10, 3): 10 значащих цифр всего.
#: Без явной проверки значение вроде 999999999999 проходит валидацию и падает уже
#: в БД (DataError -> 500), поэтому отсекаем его здесь и отвечаем 422.
MAX_MONEY = Decimal("99999999.99")
MAX_WEIGHT = Decimal("9999999.999")


def _money(value: Decimal) -> Decimal:
    result = round_money(value)
    if abs(result) > MAX_MONEY:
        raise ValueError(f"Сумма не может превышать {MAX_MONEY}")
    return result


def _weight(value: Decimal) -> Decimal:
    result = round_weight(value)
    if abs(result) > MAX_WEIGHT:
        raise ValueError(f"Вес не может превышать {MAX_WEIGHT} кг")
    return result


def _non_negative_money(value: Decimal) -> Decimal:
    result = _money(value)
    if result < 0:
        raise ValueError("Сумма не может быть отрицательной")
    return result


def _non_negative_weight(value: Decimal) -> Decimal:
    result = _weight(value)
    if result < 0:
        raise ValueError("Вес не может быть отрицательным")
    return result


def _order_weight(value: Decimal) -> Decimal:
    """Вес позиции заказа: минимум 0.100 кг и кратность шагу 0.100 кг."""
    result = round_weight(value)
    if result < MIN_WEIGHT:
        raise ValueError(f"Минимальный вес — {MIN_WEIGHT} кг")
    if not is_valid_weight_step(result):
        raise ValueError(f"Вес должен быть кратен {WEIGHT_STEP} кг")
    return result


def _money_to_str(value: Decimal) -> str:
    return f"{round_money(value):.2f}"


def _weight_to_str(value: Decimal) -> str:
    return f"{round_weight(value):.3f}"


_MoneySerializer = PlainSerializer(_money_to_str, return_type=str, when_used="always")
_WeightSerializer = PlainSerializer(_weight_to_str, return_type=str, when_used="always")

#: Деньги: два знака, в JSON — строка ("890.00").
MoneyDecimal = Annotated[
    Decimal,
    BeforeValidator(_coerce_decimal),
    AfterValidator(_money),
    _MoneySerializer,
]
#: Деньги, которые не могут быть отрицательными (цены на входе).
NonNegativeMoney = Annotated[
    Decimal,
    BeforeValidator(_coerce_decimal),
    AfterValidator(_non_negative_money),
    _MoneySerializer,
]
#: Вес: три знака, в JSON — строка ("12.500").
WeightDecimal = Annotated[
    Decimal,
    BeforeValidator(_coerce_decimal),
    AfterValidator(_weight),
    _WeightSerializer,
]
#: Вес, который не может быть отрицательным (остатки на входе).
NonNegativeWeight = Annotated[
    Decimal,
    BeforeValidator(_coerce_decimal),
    AfterValidator(_non_negative_weight),
    _WeightSerializer,
]
#: Вес позиции заказа: >= 0.100 кг и кратен 0.100 кг.
OrderWeight = Annotated[
    Decimal,
    BeforeValidator(_coerce_decimal),
    AfterValidator(_order_weight),
    _WeightSerializer,
]

#: Непустая строка: пробелы по краям срезаются до проверки длины.
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]

_PHONE_ALLOWED = set("0123456789+-() .")


def _check_phone(value: str) -> str:
    phone = value.strip()
    if not 10 <= len(phone) <= 20:
        raise ValueError("Телефон должен содержать от 10 до 20 символов")
    if set(phone) - _PHONE_ALLOWED:
        raise ValueError("Телефон может содержать только цифры и символы + - ( ) . пробел")
    if sum(char.isdigit() for char in phone) < 10:
        raise ValueError("В телефоне должно быть не меньше 10 цифр")
    return phone


#: Телефон покупателя.
PhoneStr = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=20),
    AfterValidator(_check_phone),
]

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """Страница списка: `{"items": [], "total": 0, "limit": 20, "offset": 0}`."""

    items: list[T] = Field(default_factory=list, description="Элементы страницы")
    total: int = Field(default=0, ge=0, description="Всего элементов по фильтру")
    limit: int = Field(default=DEFAULT_PAGE_LIMIT, ge=1, description="Размер страницы")
    offset: int = Field(default=0, ge=0, description="Смещение от начала списка")


class AppSettingsOut(BaseModel):
    """Публичные настройки магазина для витрины."""

    model_config = ConfigDict(from_attributes=True)

    delivery_price: MoneyDecimal = Field(description="Стоимость доставки")
    pickup_address: str = Field(description="Адрес самовывоза")
    min_weight_kg: WeightDecimal = Field(description="Минимальный вес позиции, кг")
    weight_step_kg: WeightDecimal = Field(description="Шаг изменения веса, кг")
    currency: str = Field(default="RUB", description="Код валюты")
    payment_note: str = Field(default="Оплата при получении", description="Способ оплаты")
