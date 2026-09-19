"""Схемы подсказок адреса.

Координаты — только `Decimal`, как деньги и вес в `app/schemas/common.py`:
числа от внешнего сервиса приводятся к Decimal **через строку** (иначе в
значение утекает двоичная погрешность float) и уезжают в JSON строками.
"""

from __future__ import annotations

from pydantic import (
    BaseModel,
    Field,
)

# Константы и типы координат — общие для всего API, живут в common.py рядом
# с деньгами и весом. Здесь они реэкспортируются: address_service берёт
# границы диапазонов отсюда.
from app.schemas.common import MAX_LATITUDE, MAX_LONGITUDE, Latitude, Longitude

__all__ = [
    "DEFAULT_SUGGEST_LIMIT",
    "MAX_LATITUDE",
    "MAX_LONGITUDE",
    "MAX_QUERY_LENGTH",
    "MAX_SUGGEST_LIMIT",
    "MIN_QUERY_LENGTH",
    "AddressSuggestion",
    "AddressSuggestionsOut",
    "Latitude",
    "Longitude",
]

#: Короче трёх символов внешний сервис отдаёт мусор, а лимит запросов тратится
#: по-настоящему: такие запросы наружу не уходят вовсе.
MIN_QUERY_LENGTH = 3

#: Адресная строка длиннее 200 символов — это уже не адрес, а попытка
#: прокачать через наш прокси произвольный текст.
MAX_QUERY_LENGTH = 200

#: Сколько подсказок показывать по умолчанию и максимум.
DEFAULT_SUGGEST_LIMIT = 5
MAX_SUGGEST_LIMIT = 10


class AddressSuggestion(BaseModel):
    """Одна подсказка адреса.

    `value` — готовая строка для подстановки в поле адреса. Остальные поля
    необязательны: внешние сервисы заполняют их далеко не всегда.
    """

    value: str = Field(description="Полная строка адреса для подстановки в поле")
    city: str | None = Field(default=None, description="Город или населённый пункт")
    street: str | None = Field(default=None, description="Улица")
    house: str | None = Field(default=None, description="Номер дома")
    postal_code: str | None = Field(default=None, description="Почтовый индекс")
    lat: Latitude | None = Field(default=None, description='Широта строкой: "55.755814"')
    lon: Longitude | None = Field(default=None, description='Долгота строкой: "37.617635"')


class AddressSuggestionsOut(BaseModel):
    """Ответ эндпоинта подсказок.

    `enabled=false` означает «подсказки выключены на сервере»: фронтенд обязан
    молча деградировать до обычного текстового поля, а не показывать ошибку.
    Пустой `items` при `enabled=true` — это короткий запрос или недоступный
    провайдер, тоже не ошибка.
    """

    enabled: bool = Field(description="Включены ли подсказки на сервере")
    provider: str = Field(description="Провайдер подсказок: photon, dadata или none")
    items: list[AddressSuggestion] = Field(
        default_factory=list, description="Найденные адреса"
    )
