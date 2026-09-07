"""Округление денег и веса. Только Decimal — никакого float."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

MONEY_EXP = Decimal("0.01")
WEIGHT_EXP = Decimal("0.001")

#: Шаг и минимальный вес заказа (кг).
WEIGHT_STEP = Decimal("0.1")
MIN_WEIGHT = Decimal("0.1")


def to_decimal(value: object) -> Decimal:
    """Безопасно приводит значение к Decimal (float — через str, чтобы не тащить двоичную ошибку)."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"Некорректное числовое значение: {value!r}") from exc


def round_money(value: object) -> Decimal:
    return to_decimal(value).quantize(MONEY_EXP, rounding=ROUND_HALF_UP)


def round_weight(value: object) -> Decimal:
    return to_decimal(value).quantize(WEIGHT_EXP, rounding=ROUND_HALF_UP)


def line_total(weight_kg: object, price_per_kg: object) -> Decimal:
    """Стоимость позиции: вес * цена за кг, округление до копеек."""
    return round_money(round_weight(weight_kg) * to_decimal(price_per_kg))


def is_valid_weight_step(weight_kg: Decimal) -> bool:
    """Вес должен быть кратен шагу 0.1 кг."""
    return (round_weight(weight_kg) % WEIGHT_STEP) == 0


def format_money(value: object) -> str:
    """Человекочитаемая сумма для Telegram-сообщений: 1 234,50 ₽."""
    amount = round_money(value)
    whole, _, frac = f"{amount:.2f}".partition(".")
    grouped = f"{int(whole):,}".replace(",", " ")
    return f"{grouped},{frac} ₽"


def format_weight(value: object) -> str:
    """Человекочитаемый вес: 1,5 кг."""
    weight = round_weight(value).normalize()
    text = format(weight, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return f"{text.replace('.', ',')} кг"
