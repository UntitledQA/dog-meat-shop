"""Подсказки адресов от внешнего сервиса — серверный прокси.

Почему прокси, а не прямой запрос из Mini App
---------------------------------------------
Ключ провайдера (`DADATA_API_KEY`) живёт только в окружении сервера. Уехав в
браузер, он немедленно стал бы общедоступным: его видно и в исходниках бандла,
и во вкладке «Сеть». Поэтому наружу ходит backend, а Mini App обращается к
нашему эндпоинту с обычной авторизацией Telegram.

Правило отказоустойчивости — то же, что у `notification_service`: **внешняя
система не имеет права ронять наш запрос**. Таймаут, 500 от провайдера, мусор
вместо JSON — всё это превращается в пустой список подсказок и запись в
structlog. Покупатель просто вводит адрес руками.

В лог уходят только имя провайдера и тип ошибки: ни ключа, ни заголовков там
быть не должно.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.address import (
    DEFAULT_SUGGEST_LIMIT,
    MAX_LATITUDE,
    MAX_LONGITUDE,
    MAX_QUERY_LENGTH,
    MAX_SUGGEST_LIMIT,
    MIN_QUERY_LENGTH,
    AddressSuggestion,
    AddressSuggestionsOut,
)

__all__ = [
    "DADATA_URL",
    "PHOTON_URL",
    "PROVIDER_DADATA",
    "PROVIDER_NONE",
    "PROVIDER_PHOTON",
    "get_client",
    "reset",
    "shutdown",
    "suggest",
]

logger = get_logger(__name__)

PROVIDER_PHOTON = "photon"
PROVIDER_DADATA = "dadata"
PROVIDER_NONE = "none"

#: Photon (OpenStreetMap) — бесплатный, без ключа, сделан под автодополнение.
PHOTON_URL = "https://photon.komoot.io/api/"
#: Язык ответа Photon НЕ задаём. Публичный инстанс принимает только
#: default, de, en и fr, а на `lang=ru` отвечает 400 Bad Request — из-за чего
#: подсказки молча приходили пустыми. Режим по умолчанию отдаёт названия на
#: местном языке, то есть для российских адресов как раз по-русски.

#: DaData — лучшее качество по российским адресам, но только с ключом.
DADATA_URL = "https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/address"

#: Подставляется, если оператор стёр ADDRESS_SUGGEST_USER_AGENT: правила Photon
#: требуют осмысленный User-Agent, безымянные запросы там режут.
_FALLBACK_USER_AGENT = "MeatForDogsShop/1.0 (Telegram Mini App)"


# ---------------------------------------------------------------------------
# HTTP-клиент: один на процесс
# ---------------------------------------------------------------------------

_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    """Общий httpx-клиент (создаётся лениво, переиспользует соединения).

    Новый клиент на каждый запрос означал бы TCP- и TLS-рукопожатие на каждую
    набранную букву — для автодополнения это неприемлемо.
    """
    global _client

    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(float(settings.address_suggest_timeout_seconds)),
            headers={"User-Agent": _user_agent()},
            follow_redirects=True,
        )
        logger.info("address_client_created", provider=settings.address_suggest_provider_name)
    return _client


async def shutdown() -> None:
    """Закрывает HTTP-клиент (вызывается из lifespan приложения)."""
    global _client

    if _client is not None:
        try:
            await _client.aclose()
        except Exception as exc:  # pragma: no cover - закрытие не должно ронять выход
            logger.warning("address_client_close_failed", error=type(exc).__name__)
        finally:
            _client = None


def reset() -> None:
    """Сбрасывает кэшированный клиент без сетевых вызовов (для тестов)."""
    global _client

    _client = None


def _user_agent() -> str:
    return settings.address_suggest_user_agent.strip() or _FALLBACK_USER_AGENT


# ---------------------------------------------------------------------------
# Запросы к провайдерам
# ---------------------------------------------------------------------------


async def _request_photon(query: str, limit: int) -> Any:
    """GET к Photon. Ключ не нужен, но User-Agent обязателен по правилам сервиса."""
    response = await get_client().get(
        PHOTON_URL,
        params={"q": query, "limit": limit},
    )
    response.raise_for_status()
    # parse_float=Decimal: числа не проходят через float ни на мгновение.
    return response.json(parse_float=Decimal)


async def _request_dadata(query: str, limit: int) -> Any:
    """POST к DaData. Ключ подставляется здесь и никуда больше не уходит."""
    response = await get_client().post(
        DADATA_URL,
        json={"query": query, "count": limit},
        headers={
            "Accept": "application/json",
            "Authorization": f"Token {settings.dadata_api_key.strip()}",
        },
    )
    response.raise_for_status()
    return response.json(parse_float=Decimal)


# ---------------------------------------------------------------------------
# Разбор ответов
# ---------------------------------------------------------------------------


def _text(value: Any) -> str | None:
    """Строка из ответа провайдера или None: всё остальное игнорируем."""
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split())
    return cleaned or None


def _coordinate(value: Any, bound: Decimal) -> Decimal | None:
    """Координата провайдера -> Decimal. Мусор отбрасывается: адрес важнее координат."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        number = value
    else:
        try:
            # Через str, а не через float: иначе теряется точность.
            number = Decimal(str(value).strip().replace(",", "."))
        except (InvalidOperation, ValueError):
            return None
    if not number.is_finite() or abs(number) > bound:
        return None
    return number


def _join_parts(*parts: str | None) -> str:
    """Склеивает непустые части адреса, отбрасывая повторы («Москва, Москва»)."""
    result: list[str] = []
    for part in parts:
        if part and part not in result:
            result.append(part)
    return ", ".join(result)


def _photon_feature(feature: Any) -> AddressSuggestion | None:
    """Одна точка GeoJSON от Photon -> подсказка."""
    if not isinstance(feature, dict):
        return None
    props = feature.get("properties")
    if not isinstance(props, dict):
        return None

    city = (
        _text(props.get("city"))
        or _text(props.get("town"))
        or _text(props.get("village"))
        or _text(props.get("state"))
    )
    street = _text(props.get("street"))
    house = _text(props.get("housenumber"))
    name = _text(props.get("name"))
    if street is None and name is not None and name != city:
        # Точка без улицы: в name лежит либо объект, либо сам населённый пункт.
        street = name

    lat: Decimal | None = None
    lon: Decimal | None = None
    geometry = feature.get("geometry")
    coordinates = geometry.get("coordinates") if isinstance(geometry, dict) else None
    if isinstance(coordinates, list) and len(coordinates) >= 2:
        # GeoJSON хранит порядок [долгота, широта] — перепутать легко.
        lon = _coordinate(coordinates[0], MAX_LONGITUDE)
        lat = _coordinate(coordinates[1], MAX_LATITUDE)

    value = _join_parts(city, street, house) or name or city
    if not value:
        return None

    return AddressSuggestion(
        value=value,
        city=city,
        street=street,
        house=house,
        postal_code=_text(props.get("postcode")),
        lat=lat,
        lon=lon,
    )


def _parse_photon(payload: Any) -> list[AddressSuggestion]:
    features = payload.get("features") if isinstance(payload, dict) else None
    if not isinstance(features, list):
        return []
    parsed = (_photon_feature(feature) for feature in features)
    return [item for item in parsed if item is not None]


def _dadata_item(item: Any) -> AddressSuggestion | None:
    """Одна подсказка DaData -> наша схема."""
    if not isinstance(item, dict):
        return None
    raw = item.get("data")
    data: dict[str, Any] = raw if isinstance(raw, dict) else {}

    city = (
        _text(data.get("city"))
        or _text(data.get("settlement_with_type"))
        or _text(data.get("settlement"))
        or _text(data.get("region_with_type"))
    )
    street = _text(data.get("street_with_type")) or _text(data.get("street"))
    house = _text(data.get("house"))

    value = _text(item.get("value")) or _join_parts(city, street, house)
    if not value:
        return None

    return AddressSuggestion(
        value=value,
        city=city,
        street=street,
        house=house,
        postal_code=_text(data.get("postal_code")),
        lat=_coordinate(data.get("geo_lat"), MAX_LATITUDE),
        lon=_coordinate(data.get("geo_lon"), MAX_LONGITUDE),
    )


def _parse_dadata(payload: Any) -> list[AddressSuggestion]:
    suggestions = payload.get("suggestions") if isinstance(payload, dict) else None
    if not isinstance(suggestions, list):
        return []
    parsed = (_dadata_item(item) for item in suggestions)
    return [item for item in parsed if item is not None]


async def _fetch(provider: str, query: str, limit: int) -> list[AddressSuggestion]:
    """Ходит к выбранному провайдеру и разбирает ответ."""
    if provider == PROVIDER_PHOTON:
        return _parse_photon(await _request_photon(query, limit))
    if provider == PROVIDER_DADATA:
        return _parse_dadata(await _request_dadata(query, limit))
    return []


# ---------------------------------------------------------------------------
# Публичная функция сервиса
# ---------------------------------------------------------------------------


def _normalize_query(query: str) -> str:
    """Схлопывает пробелы и обрезает длину: наружу уходит только разумный текст."""
    return " ".join(query.split())[:MAX_QUERY_LENGTH]


async def suggest(query: str, *, limit: int = DEFAULT_SUGGEST_LIMIT) -> AddressSuggestionsOut:
    """Подсказки адреса. Никогда не бросает исключений наружу.

    Пустой список возвращается, когда подсказки выключены, запрос слишком
    короткий или внешний сервис не ответил. Это осознанный выбор: поле адреса
    в Mini App обязано работать как обычный текстовый ввод при любой погоде.
    """
    provider = settings.address_suggest_provider_name
    if provider == PROVIDER_NONE:
        return AddressSuggestionsOut(enabled=False, provider=PROVIDER_NONE, items=[])

    safe_limit = max(1, min(limit, MAX_SUGGEST_LIMIT))
    text = _normalize_query(query)
    if len(text) < MIN_QUERY_LENGTH:
        return AddressSuggestionsOut(enabled=True, provider=provider, items=[])

    try:
        items = await _fetch(provider, text, safe_limit)
    except Exception as exc:
        # Сюда попадают таймауты, сетевые сбои, 4xx/5xx провайдера и кривой JSON.
        logger.warning(
            "address_suggest_failed",
            provider=provider,
            error=type(exc).__name__,
            query_length=len(text),
        )
        return AddressSuggestionsOut(enabled=True, provider=provider, items=[])

    return AddressSuggestionsOut(enabled=True, provider=provider, items=items[:safe_limit])
