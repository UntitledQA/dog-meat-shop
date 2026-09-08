"""Округление денег и веса. Только Decimal — никакого float."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

MONEY_EXP = Decimal("0.01")
WEIGHT_EXP = Decimal("0.001")

#: Шаг и минимальный вес заказа (кг).
WEIGHT_STEP = Decimal("0.1")
MIN_WEIGHT = Decimal("0.1")


def to_decimal(value: object) -> Decimal:
    """Приводит значение к Decimal.

    float переводится через str, иначе в значение утекает двоичная погрешность.
    NaN и бесконечности отбрасываются: иначе они доходят до quantize и падают
    там уже как ArithmeticError, который Pydantic не превращает в 422.
    """
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, float):
        result = Decimal(str(value))
    else:
        try:
            result = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError(f"Некорректное числовое значение: {value!r}") from exc

    if not result.is_finite():
        raise ValueError("Значение должно быть конечным числом")
    return result


def round_money(value: object) -> Decimal:
    """Округляет до копеек.

    `InvalidOperation` (например, на «1e1000») превращается в `ValueError`, чтобы
    ошибка ввода стала 422, а не 500.
    """
    try:
        return to_decimal(value).quantize(MONEY_EXP, rounding=ROUND_HALF_UP)
    except InvalidOperation:
        raise ValueError("Слишком большое числовое значение") from None


def round_weight(value: object) -> Decimal:
    try:
        return to_decimal(value).quantize(WEIGHT_EXP, rounding=ROUND_HALF_UP)
    except InvalidOperation:
        raise ValueError("Слишком большое числовое значение") from None


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
