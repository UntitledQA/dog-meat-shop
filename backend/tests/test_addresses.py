"""Подсказки адреса: авторизация, деградация и формат координат.

Внешний сервис здесь не дёргается ни разу: запрос к провайдеру подменяется
через monkeypatch, а счётчик вызовов доказывает, что короткий запрос и
выключенные подсказки наружу не уходят вовсе.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from app.core.config import settings
from app.core.ratelimit import reset_rate_limits
from app.services import address_service

PREFIX = "/api/v1"
SUGGEST_URL = f"{PREFIX}/addresses/suggest"

#: Кусок настоящего ответа Photon (GeoJSON). Порядок координат — [долгота, широта].
PHOTON_RESPONSE: dict[str, Any] = {
    "features": [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [37.617635, 55.755814]},
            "properties": {
                "country": "Россия",
                "state": "Москва",
                "city": "Москва",
                "street": "Тверская улица",
                "housenumber": "7",
                "postcode": "125009",
                "name": "Центральный телеграф",
            },
        },
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [30.315868, 59.939095]},
            "properties": {
                "country": "Россия",
                "state": "Санкт-Петербург",
                "name": "Санкт-Петербург",
                "osm_key": "place",
            },
        },
    ]
}

#: Кусок настоящего ответа DaData: координаты приходят строками.
DADATA_RESPONSE: dict[str, Any] = {
    "suggestions": [
        {
            "value": "г Москва, ул Тверская, д 7",
            "data": {
                "postal_code": "125009",
                "city": "Москва",
                "street_with_type": "ул Тверская",
                "house": "7",
                "geo_lat": "55.7558140",
                "geo_lon": "37.6176350",
            },
        }
    ]
}

DADATA_TEST_KEY = "test-key-only-for-pytest"


class ProviderStub:
    """Подменяет запрос к провайдеру и считает обращения к нему."""

    def __init__(self, payload: Any = None, error: BaseException | None = None) -> None:
        self.payload = payload
        self.error = error
        self.calls: list[tuple[str, int]] = []

    async def __call__(self, query: str, limit: int) -> Any:
        self.calls.append((query, limit))
        if self.error is not None:
            raise self.error
        return self.payload

    @property
    def count(self) -> int:
        return len(self.calls)


@pytest.fixture(autouse=True)
def _addresses_env(monkeypatch: pytest.MonkeyPatch):
    """Предсказуемые настройки: провайдер photon, лимит выключен, клиент чистый."""
    monkeypatch.setattr(settings, "address_suggest_provider", "photon")
    monkeypatch.setattr(settings, "dadata_api_key", "")
    # Лимит автодополнения проверяется в tests/test_ratelimit.py, здесь он мешает.
    monkeypatch.setattr(settings, "rate_limit_addresses", "off")
    reset_rate_limits()
    address_service.reset()
    yield
    reset_rate_limits()
    address_service.reset()


@pytest.fixture
def photon(monkeypatch: pytest.MonkeyPatch):
    """Фабрика заглушек Photon: подменяет сетевой вызов и возвращает счётчик."""

    def _install(payload: Any = None, error: BaseException | None = None) -> ProviderStub:
        stub = ProviderStub(payload=payload, error=error)
        monkeypatch.setattr(address_service, "_request_photon", stub)
        return stub

    return _install


@pytest.fixture
def dadata(monkeypatch: pytest.MonkeyPatch):
    """То же для DaData, вместе с ключом в настройках."""

    def _install(payload: Any = None, error: BaseException | None = None) -> ProviderStub:
        monkeypatch.setattr(settings, "address_suggest_provider", "dadata")
        monkeypatch.setattr(settings, "dadata_api_key", DADATA_TEST_KEY)
        stub = ProviderStub(payload=payload, error=error)
        monkeypatch.setattr(address_service, "_request_dadata", stub)
        return stub

    return _install


# ---------------------------------------------------------------------------
# Авторизация
# ---------------------------------------------------------------------------


async def test_suggest_requires_authorization(client, photon) -> None:
    """Публичных ручек под /api/v1 нет: иначе прокси к чужому API открыт всем."""
    stub = photon(PHOTON_RESPONSE)

    response = await client.get(SUGGEST_URL, params={"query": "Тверская улица"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
    assert stub.count == 0, "неавторизованный запрос не должен уходить к провайдеру"


# ---------------------------------------------------------------------------
# Когда наружу ходить не нужно
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("query", ["", "т", "мо", "  м  "])
async def test_short_query_does_not_touch_provider(client, user_headers, photon, query) -> None:
    """Меньше трёх символов — пустой список без единого внешнего запроса."""
    stub = photon(PHOTON_RESPONSE)

    response = await client.get(SUGGEST_URL, params={"query": query}, headers=user_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is True
    assert body["items"] == []
    assert stub.count == 0


async def test_provider_none_disables_suggestions(
    client, user_headers, photon, monkeypatch
) -> None:
    """Выключенные подсказки — это 200 с enabled=false, а не 404 и не 500."""
    monkeypatch.setattr(settings, "address_suggest_provider", "none")
    stub = photon(PHOTON_RESPONSE)

    response = await client.get(
        SUGGEST_URL, params={"query": "Тверская улица"}, headers=user_headers
    )

    assert response.status_code == 200
    assert response.json() == {"enabled": False, "provider": "none", "items": []}
    assert stub.count == 0


async def test_dadata_without_key_is_disabled(client, user_headers, monkeypatch) -> None:
    """dadata без ключа = выключенные подсказки, а не падение приложения."""
    monkeypatch.setattr(settings, "address_suggest_provider", "dadata")
    monkeypatch.setattr(settings, "dadata_api_key", "")
    stub = ProviderStub(DADATA_RESPONSE)
    monkeypatch.setattr(address_service, "_request_dadata", stub)

    response = await client.get(
        SUGGEST_URL, params={"query": "Тверская улица"}, headers=user_headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is False
    assert body["provider"] == "none"
    assert body["items"] == []
    assert stub.count == 0


# ---------------------------------------------------------------------------
# Разбор ответа провайдера
# ---------------------------------------------------------------------------


async def test_photon_response_is_parsed(client, user_headers, photon) -> None:
    stub = photon(PHOTON_RESPONSE)

    response = await client.get(
        SUGGEST_URL, params={"query": "Тверская улица", "limit": 5}, headers=user_headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is True
    assert body["provider"] == "photon"
    assert stub.calls == [("Тверская улица", 5)]

    first = body["items"][0]
    assert first["value"] == "Москва, Тверская улица, 7"
    assert first["city"] == "Москва"
    assert first["street"] == "Тверская улица"
    assert first["house"] == "7"
    assert first["postal_code"] == "125009"

    # Точка без улицы и дома: остаётся хотя бы город.
    assert body["items"][1]["value"] == "Санкт-Петербург"


async def test_photon_coordinates_are_strings(client, user_headers, photon) -> None:
    """Инвариант 2: Decimal уезжает строкой, иначе JS теряет точность."""
    photon(PHOTON_RESPONSE)

    response = await client.get(
        SUGGEST_URL, params={"query": "Тверская улица"}, headers=user_headers
    )

    first = response.json()["items"][0]
    assert isinstance(first["lat"], str)
    assert isinstance(first["lon"], str)
    # Широта и долгота не перепутаны: GeoJSON отдаёт их в обратном порядке.
    assert first["lat"] == "55.755814"
    assert first["lon"] == "37.617635"


async def test_dadata_response_is_parsed(client, user_headers, dadata) -> None:
    stub = dadata(DADATA_RESPONSE)

    response = await client.get(
        SUGGEST_URL, params={"query": "Тверская 7"}, headers=user_headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "dadata"
    assert stub.count == 1

    first = body["items"][0]
    assert first["value"] == "г Москва, ул Тверская, д 7"
    assert first["street"] == "ул Тверская"
    assert first["lat"] == "55.755814"
    assert first["lon"] == "37.617635"


async def test_api_key_never_leaks_to_client(client, user_headers, dadata) -> None:
    """Ключ провайдера живёт только на сервере и не появляется в ответе."""
    dadata(DADATA_RESPONSE)

    response = await client.get(
        SUGGEST_URL, params={"query": "Тверская 7"}, headers=user_headers
    )

    assert DADATA_TEST_KEY not in response.text
    assert "authorization" not in {key.lower() for key in response.headers}


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"features": "мусор"},
        {"features": [None, 42, {"properties": {}}, {"properties": {"name": "   "}}]},
        [1, 2, 3],
        None,
    ],
)
async def test_garbage_payload_gives_empty_list(client, user_headers, photon, payload) -> None:
    """Неожиданный формат ответа провайдера не должен превращаться в 500."""
    photon(payload)

    response = await client.get(
        SUGGEST_URL, params={"query": "Тверская улица"}, headers=user_headers
    )

    assert response.status_code == 200
    assert response.json()["items"] == []


# ---------------------------------------------------------------------------
# Внешний сервис недоступен
# ---------------------------------------------------------------------------


def _http_status_error(status_code: int) -> httpx.HTTPStatusError:
    """Ответ провайдера с кодом ошибки — то, что бросает `raise_for_status()`."""
    request = httpx.Request("GET", "https://example.test")
    return httpx.HTTPStatusError(
        str(status_code), request=request, response=httpx.Response(status_code, request=request)
    )


@pytest.mark.parametrize(
    "error",
    [
        httpx.TimeoutException("таймаут"),
        httpx.ConnectError("нет сети"),
        _http_status_error(429),
        _http_status_error(500),
        ValueError("это не JSON"),
    ],
)
async def test_provider_failure_does_not_break_request(
    client, user_headers, photon, error
) -> None:
    """Падение внешнего сервиса — пустой список, а не 500: заказ важнее подсказки."""
    stub = photon(error=error)

    response = await client.get(
        SUGGEST_URL, params={"query": "Тверская улица"}, headers=user_headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is True
    assert body["items"] == []
    assert stub.count == 1


# ---------------------------------------------------------------------------
# Валидация параметров
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("limit", [0, -1, 11, 100, "много"])
async def test_limit_out_of_range_is_rejected(client, user_headers, photon, limit) -> None:
    stub = photon(PHOTON_RESPONSE)

    response = await client.get(
        SUGGEST_URL, params={"query": "Тверская улица", "limit": limit}, headers=user_headers
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert stub.count == 0


async def test_query_is_required(client, user_headers, photon) -> None:
    stub = photon(PHOTON_RESPONSE)

    response = await client.get(SUGGEST_URL, headers=user_headers)

    assert response.status_code == 422
    assert stub.count == 0


async def test_too_long_query_is_rejected(client, user_headers, photon) -> None:
    """Прокси не должен прокачивать наружу произвольный текст."""
    stub = photon(PHOTON_RESPONSE)

    response = await client.get(
        SUGGEST_URL, params={"query": "а" * 201}, headers=user_headers
    )

    assert response.status_code == 422
    assert stub.count == 0


async def test_limit_is_passed_to_provider_and_applied(client, user_headers, photon) -> None:
    stub = photon(PHOTON_RESPONSE)

    response = await client.get(
        SUGGEST_URL, params={"query": "Тверская улица", "limit": 1}, headers=user_headers
    )

    assert stub.calls == [("Тверская улица", 1)]
    assert len(response.json()["items"]) == 1


async def test_photon_request_does_not_send_lang(monkeypatch: pytest.MonkeyPatch) -> None:
    """Публичный Photon не знает lang=ru и отвечает 400.

    Параметр поддерживается только для default/de/en/fr, а на `ru` сервис отдаёт
    400 Bad Request — подсказки при этом молча приходили пустыми. Режим по
    умолчанию и так отдаёт названия на местном языке. Тест сторожит, чтобы
    параметр не вернулся незаметно.
    """
    captured: dict[str, object] = {}

    class _Response:
        def raise_for_status(self) -> None:
            return None

        def json(self, **_kwargs: object) -> dict[str, object]:
            return {"features": []}

    class _Client:
        async def get(self, url: str, params: dict[str, object] | None = None) -> _Response:
            captured["url"] = url
            captured["params"] = params or {}
            return _Response()

    monkeypatch.setattr(address_service, "get_client", lambda: _Client())

    await address_service._request_photon("Омск Солнечная", 5)

    assert captured["url"] == address_service.PHOTON_URL
    assert "lang" not in captured["params"]
    assert captured["params"]["q"] == "Омск Солнечная"
    assert captured["params"]["limit"] == 5


def test_suggestions_are_disabled_by_default() -> None:
    """Без явной настройки подсказки выключены.

    Включение отправляет набранный покупателем адрес стороннему сервису —
    это осознанный выбор владельца магазина, а не значение по умолчанию.
    Тест сторожит, чтобы провайдер не включился обратно незаметно.
    """
    from app.core.config import Settings

    assert Settings.model_fields["address_suggest_provider"].default == "none"
    assert Settings.model_fields["dadata_api_key"].default == ""
