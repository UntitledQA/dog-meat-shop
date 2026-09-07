"""Разграничение прав: обычный пользователь не должен попадать в админку.

Проверки идут списком по ВСЕМ административным эндпоинтам из `docs/CONTRACTS.md` §7 —
чтобы забытый `AdminUser` в новом роуте сразу ломал тест, а не приезжал в продакшен.

Тесты dev-авторизации не зависят от `conftest.py`: они поднимают минимальное приложение
поверх реальной зависимости `app.api.deps.get_telegram_data`.
"""

from __future__ import annotations

import importlib.util
import inspect

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_telegram_data
from app.core.config import settings
from app.core.errors import register_exception_handlers

APP_MAIN_AVAILABLE = importlib.util.find_spec("app.main") is not None
requires_app = pytest.mark.skipif(
    not APP_MAIN_AVAILABLE,
    reason="app/main.py ещё не создан (пишет другой агент)",
)

PREFIX = "/api/v1"

#: (метод, путь, тело/файлы) — полный список административных эндпоинтов.
ADMIN_ENDPOINTS: list[tuple[str, str, dict]] = [
    ("get", f"{PREFIX}/admin/products", {}),
    ("get", f"{PREFIX}/admin/products?include_inactive=true&search=мясо", {}),
    (
        "post",
        f"{PREFIX}/admin/products",
        {"json": {"name": "Говядина", "price_per_kg": "890.00", "stock_kg": "10.000"}},
    ),
    ("patch", f"{PREFIX}/admin/products/1", {"json": {"price_per_kg": "1.00"}}),
    ("post", f"{PREFIX}/admin/products/1/archive", {}),
    ("post", f"{PREFIX}/admin/products/1/restore", {}),
    (
        "post",
        f"{PREFIX}/admin/products/1/photo",
        {"files": {"file": ("photo.jpg", b"\xff\xd8\xff\xe0stub", "image/jpeg")}},
    ),
    (
        "post",
        f"{PREFIX}/admin/uploads/photo",
        {"files": {"file": ("photo.jpg", b"\xff\xd8\xff\xe0stub", "image/jpeg")}},
    ),
    ("get", f"{PREFIX}/admin/orders", {}),
    ("get", f"{PREFIX}/admin/orders?status=new", {}),
    ("get", f"{PREFIX}/admin/orders/1", {}),
    ("patch", f"{PREFIX}/admin/orders/1/status", {"json": {"status": "confirmed"}}),
]

READ_ONLY_ADMIN_ENDPOINTS = [
    f"{PREFIX}/admin/products",
    f"{PREFIX}/admin/orders",
]


async def _request(client, method: str, url: str, **kwargs):
    """Совместимо и с sync TestClient, и с httpx.AsyncClient."""
    result = getattr(client, method)(url, **kwargs)
    if inspect.isawaitable(result):
        return await result
    return result


def _ids(endpoints: list[tuple[str, str, dict]]) -> list[str]:
    return [f"{method.upper()} {path}" for method, path, _ in endpoints]


# ---------------------------------------------------------------------------
# Обычный пользователь -> 403 на каждом административном эндпоинте
# ---------------------------------------------------------------------------


@requires_app
@pytest.mark.parametrize(
    ("method", "path", "payload"), ADMIN_ENDPOINTS, ids=_ids(ADMIN_ENDPOINTS)
)
async def test_regular_user_forbidden_on_admin_endpoints(
    client, user_headers, method: str, path: str, payload: dict
) -> None:
    response = await _request(client, method, path, headers=user_headers, **payload)

    assert response.status_code == 403, (
        f"{method.upper()} {path} доступен обычному пользователю "
        f"(получен {response.status_code})"
    )
    assert response.json()["error"]["code"] == "forbidden"


@requires_app
@pytest.mark.parametrize(
    ("method", "path", "payload"), ADMIN_ENDPOINTS, ids=_ids(ADMIN_ENDPOINTS)
)
async def test_anonymous_unauthorized_on_admin_endpoints(
    client, method: str, path: str, payload: dict
) -> None:
    """Без заголовка авторизации — 401, а не 403 и не 500."""
    response = await _request(client, method, path, **payload)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


# ---------------------------------------------------------------------------
# Администратор
# ---------------------------------------------------------------------------


@requires_app
@pytest.mark.parametrize("path", READ_ONLY_ADMIN_ENDPOINTS)
async def test_admin_can_read_admin_lists(client, admin_headers, path: str) -> None:
    response = await _request(client, "get", path, headers=admin_headers)

    assert response.status_code == 200
    body = response.json()
    assert set(body) >= {"items", "total", "limit", "offset"}


@requires_app
async def test_admin_can_create_product(client, admin_headers) -> None:
    response = await _request(
        client,
        "post",
        f"{PREFIX}/admin/products",
        headers=admin_headers,
        json={"name": "Тестовая говядина", "price_per_kg": "890.00", "stock_kg": "10.000"},
    )

    assert response.status_code == 201
    assert response.json()["name"] == "Тестовая говядина"


@requires_app
@pytest.mark.parametrize(
    ("method", "path", "payload"), ADMIN_ENDPOINTS, ids=_ids(ADMIN_ENDPOINTS)
)
async def test_admin_is_never_forbidden(
    client, admin_headers, method: str, path: str, payload: dict
) -> None:
    """Админ может получить 404/409/422, но никогда 401 или 403."""
    response = await _request(client, method, path, headers=admin_headers, **payload)

    assert response.status_code not in (401, 403), (
        f"{method.upper()} {path} закрыт для администратора ({response.status_code})"
    )


@requires_app
async def test_admin_status_is_taken_from_settings(client, admin_headers) -> None:
    response = await _request(client, "post", f"{PREFIX}/auth/telegram", headers=admin_headers)

    assert response.status_code == 200
    assert response.json()["is_admin"] is True


# ---------------------------------------------------------------------------
# Чужие заказы (IDOR)
# ---------------------------------------------------------------------------


@requires_app
async def test_foreign_order_is_not_readable(client, user_headers) -> None:
    """Заказ другого пользователя не должен отдаваться обычному покупателю.

    Допустим и 403 (по контракту), и 404 (не раскрываем существование заказа),
    но не 200.
    """
    response = await _request(client, "get", f"{PREFIX}/orders/999999", headers=user_headers)

    assert response.status_code in (403, 404)
    assert response.json()["error"]["code"] in {"forbidden", "not_found"}


# ---------------------------------------------------------------------------
# Dev-авторизация (без conftest и без БД)
# ---------------------------------------------------------------------------


def _dev_app() -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/whoami")
    async def whoami(data=Depends(get_telegram_data)) -> dict:
        return {"telegram_id": data.telegram_id, "is_dev": data.is_dev}

    return TestClient(app, raise_server_exceptions=False)


def test_dev_auth_disabled_by_default() -> None:
    """Значение по умолчанию — выключено."""
    assert settings.dev_auth_enabled is False
    assert settings.dev_auth_allowed is False


def test_dev_auth_header_rejected_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "dev_auth_enabled", False)
    monkeypatch.setattr(settings, "environment", "development")

    response = _dev_app().get("/whoami", headers={"X-Dev-Telegram-Id": "777"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_dev_auth_forbidden_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    """Даже с DEV_AUTH_ENABLED=true в production dev-вход невозможен."""
    monkeypatch.setattr(settings, "dev_auth_enabled", True)
    monkeypatch.setattr(settings, "environment", "production")

    assert settings.is_production is True
    assert settings.dev_auth_allowed is False

    response = _dev_app().get("/whoami", headers={"X-Dev-Telegram-Id": "777"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


@pytest.mark.parametrize("environment", ["production", "PRODUCTION", "prod"])
def test_production_aliases_block_dev_auth(
    monkeypatch: pytest.MonkeyPatch, environment: str
) -> None:
    monkeypatch.setattr(settings, "dev_auth_enabled", True)
    monkeypatch.setattr(settings, "environment", environment)

    assert settings.dev_auth_allowed is False


def test_dev_auth_works_only_in_development(monkeypatch: pytest.MonkeyPatch) -> None:
    """Обратная проверка: включённый dev-режим вне production действительно работает."""
    monkeypatch.setattr(settings, "dev_auth_enabled", True)
    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(settings, "dev_telegram_id", 0)

    assert settings.dev_auth_allowed is True

    response = _dev_app().get("/whoami", headers={"X-Dev-Telegram-Id": "777"})

    assert response.status_code == 200
    assert response.json() == {"telegram_id": 777, "is_dev": True}


def test_dev_auth_requires_configured_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """Без заголовка и без DEV_TELEGRAM_ID вход не выдаётся молча."""
    monkeypatch.setattr(settings, "dev_auth_enabled", True)
    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(settings, "dev_telegram_id", 0)

    response = _dev_app().get("/whoami")

    assert response.status_code == 401


def test_dev_auth_rejects_non_numeric_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "dev_auth_enabled", True)
    monkeypatch.setattr(settings, "environment", "development")

    response = _dev_app().get("/whoami", headers={"X-Dev-Telegram-Id": "'; DROP TABLE users; --"})

    assert response.status_code == 401


def test_admin_ids_parsed_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Права администратора берутся из переменной окружения, а не из тела запроса."""
    monkeypatch.setattr(settings, "admin_telegram_ids", "111, 222;333, мусор,")

    assert settings.admin_ids == {111, 222, 333}


def test_empty_admin_ids_means_no_admins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "admin_telegram_ids", "")

    assert settings.admin_ids == set()
