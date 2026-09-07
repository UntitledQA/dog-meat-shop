"""Проверка авторизации Telegram Mini App.

Основная часть тестов работает напрямую с `app.core.security` и не зависит ни от базы,
ни от `conftest.py`: подпись `initData` считается настоящим алгоритмом Telegram
(HMAC-SHA256 с ключом `HMAC_SHA256(b"WebAppData", bot_token)`).

HTTP-часть поднимает минимальное приложение поверх реальной зависимости
`app.api.deps.get_telegram_data`, чтобы проверить формат ответа 401 без обращения к БД.
Тесты «настоящего» приложения используют фикстуры из `tests/conftest.py`
(`client`, `session`, `user_headers`, `admin_headers`) и пропускаются, если `app/main.py`
ещё не написан.
"""

from __future__ import annotations

import hashlib
import hmac
import importlib.util
import inspect
import json
import time
from urllib.parse import parse_qsl, urlencode

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_telegram_data
from app.core.config import settings
from app.core.errors import UnauthorizedError, register_exception_handlers
from app.core.security import (
    TelegramUserData,
    build_data_check_string,
    compute_init_data_hash,
    parse_and_verify_init_data,
)

TEST_BOT_TOKEN = "123456789:AAHtesttokenfortestsonly_0123456789abcdef"
OTHER_BOT_TOKEN = "987654321:BBHanothertokenvalue_0123456789abcdefgh"
TEST_TELEGRAM_ID = 555000111
TTL = 86400

APP_MAIN_AVAILABLE = importlib.util.find_spec("app.main") is not None
requires_app = pytest.mark.skipif(
    not APP_MAIN_AVAILABLE,
    reason="app/main.py ещё не создан (пишет другой агент)",
)


# ---------------------------------------------------------------------------
# Генерация настоящего initData
# ---------------------------------------------------------------------------


def sign(payload: dict[str, str], bot_token: str) -> str:
    """Официальный алгоритм Telegram (продублирован намеренно: тест не должен
    доверять реализации, которую проверяет)."""
    data_check_string = "\n".join(
        f"{key}={value}" for key, value in sorted(payload.items()) if key != "hash"
    )
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    return hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()


def build_init_data(
    bot_token: str = TEST_BOT_TOKEN,
    *,
    telegram_id: int = TEST_TELEGRAM_ID,
    auth_date: int | None = None,
    user_json: str | None = None,
    drop_user: bool = False,
    drop_hash: bool = False,
    hash_override: str | None = None,
    **user_fields: object,
) -> str:
    """Собирает валидный (или намеренно испорченный) initData."""
    user = {
        "id": telegram_id,
        "first_name": "Иван",
        "last_name": "Петров",
        "username": "ivan_test",
        "language_code": "ru",
        "allows_write_to_pm": True,
    }
    user.update(user_fields)

    payload: dict[str, str] = {
        "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        "auth_date": str(int(auth_date if auth_date is not None else time.time())),
        "chat_type": "private",
        "chat_instance": "-1234567890123456789",
    }
    if not drop_user:
        payload["user"] = (
            user_json
            if user_json is not None
            else json.dumps(user, ensure_ascii=False, separators=(",", ":"))
        )

    if not drop_hash:
        payload["hash"] = hash_override or sign(payload, bot_token)

    return urlencode(payload)


def tamper(raw: str, field: str, value: str) -> str:
    """Меняет одно поле, сохраняя старый `hash` (имитация подмены на клиенте)."""
    pairs = dict(parse_qsl(raw, keep_blank_values=True))
    pairs[field] = value
    return urlencode(pairs)


# ---------------------------------------------------------------------------
# Валидные данные
# ---------------------------------------------------------------------------


def test_valid_init_data_accepted() -> None:
    raw = build_init_data()
    data = parse_and_verify_init_data(raw, TEST_BOT_TOKEN, TTL)

    assert isinstance(data, TelegramUserData)
    assert data.telegram_id == TEST_TELEGRAM_ID
    assert data.username == "ivan_test"
    assert data.first_name == "Иван"
    assert data.last_name == "Петров"
    assert data.is_dev is False
    assert data.auth_date > 0


def test_valid_init_data_without_optional_fields() -> None:
    raw = build_init_data(username=None, last_name=None)
    data = parse_and_verify_init_data(raw, TEST_BOT_TOKEN, TTL)

    assert data.telegram_id == TEST_TELEGRAM_ID
    assert data.username is None
    assert data.last_name is None


def test_hash_matches_reference_algorithm() -> None:
    """Реализация в `security.py` должна совпадать с независимой реализацией теста."""
    raw = build_init_data()
    pairs = parse_qsl(raw, keep_blank_values=True)
    received = dict(pairs)["hash"]

    assert compute_init_data_hash(build_data_check_string(pairs), TEST_BOT_TOKEN) == received


# ---------------------------------------------------------------------------
# Подпись
# ---------------------------------------------------------------------------


def test_invalid_signature_rejected() -> None:
    raw = build_init_data(hash_override="0" * 64)

    with pytest.raises(UnauthorizedError) as exc:
        parse_and_verify_init_data(raw, TEST_BOT_TOKEN, TTL)
    assert exc.value.code == "unauthorized"
    assert exc.value.status_code == 401


def test_init_data_signed_by_another_bot_rejected() -> None:
    """Подпись чужим токеном не должна открывать доступ к нашему магазину."""
    raw = build_init_data(OTHER_BOT_TOKEN)

    with pytest.raises(UnauthorizedError):
        parse_and_verify_init_data(raw, TEST_BOT_TOKEN, TTL)


def test_tampered_user_id_rejected() -> None:
    """Классическая атака: подменить user.id на чужой, оставив старый hash."""
    raw = build_init_data()
    victim = json.dumps(
        {"id": 999999999, "first_name": "Админ", "username": "admin"},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    forged = tamper(raw, "user", victim)

    with pytest.raises(UnauthorizedError):
        parse_and_verify_init_data(forged, TEST_BOT_TOKEN, TTL)


def test_tampered_auth_date_rejected() -> None:
    raw = build_init_data(auth_date=int(time.time()) - 10 * TTL)
    forged = tamper(raw, "auth_date", str(int(time.time())))

    with pytest.raises(UnauthorizedError):
        parse_and_verify_init_data(forged, TEST_BOT_TOKEN, TTL)


def test_added_field_rejected() -> None:
    """Любое лишнее поле меняет data_check_string и ломает подпись."""
    raw = build_init_data()
    forged = tamper(raw, "is_admin", "true")

    with pytest.raises(UnauthorizedError):
        parse_and_verify_init_data(forged, TEST_BOT_TOKEN, TTL)


def test_missing_hash_rejected() -> None:
    raw = build_init_data(drop_hash=True)

    with pytest.raises(UnauthorizedError):
        parse_and_verify_init_data(raw, TEST_BOT_TOKEN, TTL)


# ---------------------------------------------------------------------------
# Время жизни
# ---------------------------------------------------------------------------


def test_expired_auth_date_rejected() -> None:
    raw = build_init_data(auth_date=int(time.time()) - TTL - 60)

    with pytest.raises(UnauthorizedError):
        parse_and_verify_init_data(raw, TEST_BOT_TOKEN, TTL)


def test_auth_date_from_far_future_rejected() -> None:
    raw = build_init_data(auth_date=int(time.time()) + 3600)

    with pytest.raises(UnauthorizedError):
        parse_and_verify_init_data(raw, TEST_BOT_TOKEN, TTL)


def test_fresh_auth_date_accepted_at_boundary() -> None:
    raw = build_init_data(auth_date=int(time.time()) - TTL + 60)
    assert parse_and_verify_init_data(raw, TEST_BOT_TOKEN, TTL).telegram_id == TEST_TELEGRAM_ID


def test_non_numeric_auth_date_rejected() -> None:
    """Подпись пересчитана честно — отказ должен быть именно из-за auth_date."""
    payload = dict(parse_qsl(build_init_data(), keep_blank_values=True))
    payload["auth_date"] = "вчера"
    payload["hash"] = sign(payload, TEST_BOT_TOKEN)

    with pytest.raises(UnauthorizedError):
        parse_and_verify_init_data(urlencode(payload), TEST_BOT_TOKEN, TTL)


# ---------------------------------------------------------------------------
# Пустые и битые данные
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("raw", ["", "   ", "\n"])
def test_empty_init_data_rejected(raw: str) -> None:
    with pytest.raises(UnauthorizedError):
        parse_and_verify_init_data(raw, TEST_BOT_TOKEN, TTL)


def test_garbage_init_data_rejected() -> None:
    with pytest.raises(UnauthorizedError):
        parse_and_verify_init_data("не-очень-похоже-на-initdata", TEST_BOT_TOKEN, TTL)


def test_broken_user_json_rejected() -> None:
    """Подпись верна, но JSON пользователя повреждён — доступа быть не должно."""
    raw = build_init_data(user_json='{"id": 5550, "first_name": "Иван"')  # нет закрывающей скобки

    with pytest.raises(UnauthorizedError):
        parse_and_verify_init_data(raw, TEST_BOT_TOKEN, TTL)


def test_user_json_without_id_rejected() -> None:
    raw = build_init_data(user_json='{"first_name":"Иван"}')

    with pytest.raises(UnauthorizedError):
        parse_and_verify_init_data(raw, TEST_BOT_TOKEN, TTL)


def test_user_id_as_string_rejected() -> None:
    """`"id": "123"` — попытка проскочить проверку типа."""
    raw = build_init_data(user_json='{"id":"123","first_name":"Иван"}')

    with pytest.raises(UnauthorizedError):
        parse_and_verify_init_data(raw, TEST_BOT_TOKEN, TTL)


def test_missing_user_rejected() -> None:
    raw = build_init_data(drop_user=True)

    with pytest.raises(UnauthorizedError):
        parse_and_verify_init_data(raw, TEST_BOT_TOKEN, TTL)


def test_empty_bot_token_rejected() -> None:
    """Без токена подпись проверить нечем — считаем запрос неавторизованным."""
    raw = build_init_data()

    with pytest.raises(UnauthorizedError):
        parse_and_verify_init_data(raw, "", TTL)


def test_oversized_init_data_rejected() -> None:
    raw = build_init_data(first_name="Я" * 20000)

    with pytest.raises(UnauthorizedError):
        parse_and_verify_init_data(raw, TEST_BOT_TOKEN, TTL)


# ---------------------------------------------------------------------------
# HTTP: единый формат ошибки 401 (без базы данных)
# ---------------------------------------------------------------------------


@pytest.fixture()
def deps_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Минимальное приложение поверх реальной зависимости `get_telegram_data`."""
    monkeypatch.setattr(settings, "bot_token", TEST_BOT_TOKEN)
    monkeypatch.setattr(settings, "dev_auth_enabled", False)
    monkeypatch.setattr(settings, "init_data_ttl_seconds", TTL)

    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/api/v1/protected")
    async def protected(data=Depends(get_telegram_data)) -> dict:
        return {"telegram_id": data.telegram_id}

    return TestClient(app, raise_server_exceptions=False)


def test_request_without_header_returns_401_in_unified_format(deps_client: TestClient) -> None:
    response = deps_client.get("/api/v1/protected")

    assert response.status_code == 401
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == "unauthorized"
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]
    assert body["error"]["details"] == {}


def test_request_with_invalid_signature_returns_401(deps_client: TestClient) -> None:
    response = deps_client.get(
        "/api/v1/protected",
        headers={"X-Telegram-Init-Data": build_init_data(hash_override="f" * 64)},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_request_with_valid_init_data_passes(deps_client: TestClient) -> None:
    response = deps_client.get(
        "/api/v1/protected",
        headers={"X-Telegram-Init-Data": build_init_data()},
    )

    assert response.status_code == 200
    assert response.json() == {"telegram_id": TEST_TELEGRAM_ID}


def test_user_id_from_body_is_ignored(deps_client: TestClient) -> None:
    """Идентификатор берётся только из подписанных данных, а не из query/body."""
    response = deps_client.get(
        "/api/v1/protected?user_id=999999999",
        headers={"X-Telegram-Init-Data": build_init_data()},
    )

    assert response.status_code == 200
    assert response.json()["telegram_id"] == TEST_TELEGRAM_ID


# ---------------------------------------------------------------------------
# Настоящее приложение (фикстуры из conftest.py)
# ---------------------------------------------------------------------------


async def _request(client, method: str, url: str, **kwargs):
    """Совместимо и с sync TestClient, и с httpx.AsyncClient."""
    result = getattr(client, method)(url, **kwargs)
    if inspect.isawaitable(result):
        return await result
    return result


@requires_app
async def test_api_without_header_returns_401(client) -> None:
    response = await _request(client, "get", "/api/v1/me")

    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "unauthorized"
    assert "details" in body["error"]


@requires_app
async def test_api_with_user_headers_returns_profile(client, user_headers) -> None:
    response = await _request(client, "post", "/api/v1/auth/telegram", headers=user_headers)

    assert response.status_code == 200
    body = response.json()
    assert "telegram_id" in body
    assert body["is_admin"] is False


@requires_app
async def test_api_with_admin_headers_marks_admin(client, admin_headers) -> None:
    response = await _request(client, "post", "/api/v1/auth/telegram", headers=admin_headers)

    assert response.status_code == 200
    assert response.json()["is_admin"] is True
