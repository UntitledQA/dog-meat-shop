"""Тесты ограничения частоты запросов.

Приложение здесь собирается прямо в тесте: лимитер — независимый ASGI-слой, и проверять
его удобнее без базы, авторизации и остальных роутов.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.cors import CORSMiddleware

from app.core import ratelimit
from app.core.config import settings
from app.core.ratelimit import (
    Limit,
    RateLimitMiddleware,
    parse_limit,
    reset_rate_limits,
    scope_for_request,
)

PREFIX = "/api/v1"


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch: pytest.MonkeyPatch):
    """Каждый тест начинается с пустых счётчиков и предсказуемых лимитов."""
    reset_rate_limits()
    monkeypatch.setattr(ratelimit, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(ratelimit, "TRUST_PROXY_HEADERS", False)
    monkeypatch.setattr(settings, "rate_limit_auth", "3/60")
    monkeypatch.setattr(settings, "rate_limit_orders", "2/60")
    monkeypatch.setattr(settings, "rate_limit_uploads", "2/60")
    yield
    reset_rate_limits()


def build_app(with_cors: bool = True) -> FastAPI:
    app = FastAPI()
    # Порядок как в main.py: лимитер добавляется первым, CORS — последним,
    # поэтому CORS оказывается снаружи и успевает разметить даже ответ 429.
    app.add_middleware(RateLimitMiddleware)
    if with_cors:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://localhost:5173"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.post(f"{PREFIX}/auth/telegram")
    async def auth() -> dict:
        return {"ok": True}

    @app.post(f"{PREFIX}/orders")
    async def create_order() -> dict:
        return {"ok": True}

    @app.get(f"{PREFIX}/orders")
    async def list_orders() -> dict:
        return {"items": []}

    @app.post(f"{PREFIX}/admin/uploads/photo")
    async def upload() -> dict:
        return {"photo_url": "/uploads/x.jpg"}

    @app.get(f"{PREFIX}/catalog")
    async def catalog() -> dict:
        return {"items": []}

    return app


@pytest.fixture()
def rl_client() -> TestClient:
    """Клиент тестового приложения (имя отличается от общей фикстуры `client`)."""
    return TestClient(build_app(), raise_server_exceptions=False)


@pytest.fixture()
def bare_client() -> TestClient:
    """То же приложение, но без CORSMiddleware — видно поведение самого лимитера."""
    return TestClient(build_app(with_cors=False), raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Разбор настроек
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("30/60", Limit(30, 60.0)),
        ("10/1", Limit(10, 1.0)),
        ("5", Limit(5, 60.0)),
    ],
)
def test_parse_limit_valid(raw: str, expected: Limit) -> None:
    assert parse_limit(raw) == expected


@pytest.mark.parametrize("raw", ["", "0", "off", "none", "abc/def", "-5/60", "10/0", None])
def test_parse_limit_disabled_or_broken(raw: str | None) -> None:
    """Кривая переменная окружения не должна ронять приложение."""
    assert parse_limit(raw).enabled is False


@pytest.mark.parametrize(
    ("method", "path", "expected"),
    [
        ("POST", "/api/v1/auth/telegram", "auth"),
        ("GET", "/api/v1/auth/telegram", "auth"),
        ("POST", "/api/v1/orders", "orders"),
        ("GET", "/api/v1/orders", None),
        ("GET", "/api/v1/orders/5", None),
        ("POST", "/api/v1/admin/uploads/photo", "uploads"),
        ("POST", "/api/v1/admin/products/1/photo", "uploads"),
        ("GET", "/uploads/abc.jpg", None),
        ("GET", "/api/v1/catalog", None),
        ("POST", "/api/v1/admin/products", None),
    ],
)
def test_scope_detection(method: str, path: str, expected: str | None) -> None:
    assert scope_for_request(method, path) == expected


# ---------------------------------------------------------------------------
# Поведение по HTTP
# ---------------------------------------------------------------------------


def test_auth_limit_returns_429_with_retry_after(rl_client: TestClient) -> None:
    url = f"{PREFIX}/auth/telegram"

    for attempt in range(3):
        assert rl_client.post(url).status_code == 200, f"запрос {attempt + 1} должен пройти"

    response = rl_client.post(url)

    assert response.status_code == 429
    body = response.json()
    assert body["error"]["code"] == "rate_limited"
    assert body["error"]["message"]
    assert "Retry-After" in response.headers
    retry_after = int(response.headers["Retry-After"])
    assert 1 <= retry_after <= 60


def test_limit_applies_per_telegram_id(rl_client: TestClient) -> None:
    url = f"{PREFIX}/auth/telegram"
    first = {"X-Telegram-Id": "111"}
    second = {"X-Telegram-Id": "222"}

    for _ in range(3):
        assert rl_client.post(url, headers=first).status_code == 200
    assert rl_client.post(url, headers=first).status_code == 429

    # Другой пользователь не должен страдать из-за соседа.
    assert rl_client.post(url, headers=second).status_code == 200


def test_orders_limit_only_for_post(rl_client: TestClient) -> None:
    url = f"{PREFIX}/orders"

    for _ in range(2):
        assert rl_client.post(url).status_code == 200
    assert rl_client.post(url).status_code == 429

    # Чтение списка заказов не лимитируется.
    for _ in range(5):
        assert rl_client.get(url).status_code == 200


def test_uploads_limited(rl_client: TestClient) -> None:
    url = f"{PREFIX}/admin/uploads/photo"

    for _ in range(2):
        assert rl_client.post(url).status_code == 200
    response = rl_client.post(url)

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"


def test_options_preflight_is_never_limited(rl_client: TestClient) -> None:
    """CORS-preflight обязан проходить, иначе браузер покажет «сетевую ошибку»."""
    headers = {
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "POST",
    }

    for _ in range(20):
        response = rl_client.options(f"{PREFIX}/auth/telegram", headers=headers)
        assert response.status_code != 429
        assert response.status_code < 400

    # И после preflight обычные запросы всё ещё доступны в полном объёме.
    assert rl_client.post(f"{PREFIX}/auth/telegram").status_code == 200


def test_options_not_limited_without_cors(bare_client: TestClient) -> None:
    """Сам лимитер обязан пропускать OPTIONS, даже когда CORSMiddleware не подключён."""
    url = f"{PREFIX}/auth/telegram"

    for _ in range(20):
        assert bare_client.options(url).status_code != 429

    # Лимит на POST при этом не израсходован.
    for _ in range(3):
        assert bare_client.post(url).status_code == 200
    assert bare_client.post(url).status_code == 429


def test_unlimited_paths_are_untouched(rl_client: TestClient) -> None:
    for _ in range(30):
        assert rl_client.get(f"{PREFIX}/catalog").status_code == 200


def test_limit_can_be_disabled_via_settings(
    rl_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "rate_limit_auth", "0")
    reset_rate_limits()

    for _ in range(25):
        assert rl_client.post(f"{PREFIX}/auth/telegram").status_code == 200


def test_limit_can_be_disabled_globally(
    rl_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ratelimit, "RATE_LIMIT_ENABLED", False)

    for _ in range(25):
        assert rl_client.post(f"{PREFIX}/auth/telegram").status_code == 200


def test_429_carries_cors_headers(rl_client: TestClient) -> None:
    """Ответ 429 должен доезжать до браузера, а не падать на CORS."""
    origin = "http://localhost:5173"
    url = f"{PREFIX}/auth/telegram"

    for _ in range(3):
        rl_client.post(url, headers={"Origin": origin})
    response = rl_client.post(url, headers={"Origin": origin})

    assert response.status_code == 429
    assert response.headers.get("access-control-allow-origin") == origin


# ---------------------------------------------------------------------------
# Внутреннее состояние
# ---------------------------------------------------------------------------


async def test_window_slides_and_frees_slots() -> None:
    """Через окно слот освобождается (время подставляем, а не ждём)."""
    store = ratelimit.SlidingWindowStore()
    limit = Limit(2, 10.0)

    assert await store.hit("k", limit, now=100.0) is None
    assert await store.hit("k", limit, now=100.5) is None

    blocked = await store.hit("k", limit, now=101.0)
    assert blocked is not None and blocked == pytest.approx(9.0)

    assert await store.hit("k", limit, now=111.0) is None


async def test_expired_keys_are_cleaned_up() -> None:
    """Память не должна расти: протухшие корзины удаляются."""
    store = ratelimit.SlidingWindowStore()
    limit = Limit(5, 1.0)

    for index in range(50):
        await store.hit(f"key-{index}", limit, now=1000.0)
    assert len(store) == 50

    # Проходит больше окна и больше интервала очистки.
    await store.hit("fresh", limit, now=1000.0 + ratelimit.CLEANUP_INTERVAL_SECONDS + 5)

    assert len(store) == 1


def test_proxy_headers_ignored_by_default(rl_client: TestClient) -> None:
    """С TRUST_PROXY_HEADERS=False подменённый X-Forwarded-For не обходит лимит."""
    url = f"{PREFIX}/auth/telegram"

    for index in range(3):
        assert rl_client.post(url, headers={"X-Forwarded-For": f"10.0.0.{index}"}).status_code == 200

    response = rl_client.post(url, headers={"X-Forwarded-For": "10.0.0.99"})
    assert response.status_code == 429


def test_proxy_headers_used_when_trusted(
    rl_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ratelimit, "TRUST_PROXY_HEADERS", True)
    url = f"{PREFIX}/auth/telegram"

    for _ in range(3):
        assert rl_client.post(url, headers={"X-Forwarded-For": "10.0.0.1, 10.0.0.2"}).status_code == 200
    assert rl_client.post(url, headers={"X-Forwarded-For": "10.0.0.1"}).status_code == 429

    # Другой клиент за тем же прокси не заблокирован.
    assert rl_client.post(url, headers={"X-Forwarded-For": "10.0.0.7"}).status_code == 200
