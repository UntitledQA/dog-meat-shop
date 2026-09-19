"""Подсказки адреса для поля доставки.

Эндпоинт — прокси к внешнему сервису: ключ провайдера остаётся на сервере,
доступ закрыт обычной авторизацией Telegram, а частота запросов ограничена
отдельным scope `addresses` — автодополнение шлёт запрос почти на каждую букву.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser
from app.schemas.address import (
    DEFAULT_SUGGEST_LIMIT,
    MAX_QUERY_LENGTH,
    MAX_SUGGEST_LIMIT,
    MIN_QUERY_LENGTH,
    AddressSuggestionsOut,
)
from app.services import address_service

router = APIRouter(prefix="/addresses", tags=["Адреса"])

QueryText = Annotated[
    str,
    Query(max_length=MAX_QUERY_LENGTH, description="Часть адреса, которую вводит покупатель"),
]
LimitQuery = Annotated[
    int,
    Query(ge=1, le=MAX_SUGGEST_LIMIT, description="Сколько подсказок вернуть"),
]


@router.get(
    "/suggest",
    response_model=AddressSuggestionsOut,
    summary="Подсказки адреса",
    description=(
        "Прокси к внешнему сервису подсказок: ключ провайдера на фронтенд не передаётся. "
        f"Запрос короче {MIN_QUERY_LENGTH} символов наружу не уходит вовсе. "
        "Выключенные подсказки (`enabled: false`) и недоступный внешний сервис дают "
        "пустой список, а не ошибку, — поле адреса должно продолжать работать "
        "как обычный текстовый ввод. Координаты приходят строками."
    ),
)
async def suggest_addresses(
    _user: CurrentUser,
    query: QueryText,
    limit: LimitQuery = DEFAULT_SUGGEST_LIMIT,
) -> AddressSuggestionsOut:
    return await address_service.suggest(query, limit=limit)
