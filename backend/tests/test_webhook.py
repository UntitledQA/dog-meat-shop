"""Приём обновлений Telegram по webhook.

`bot_main.py` умеет регистрировать webhook в Telegram, поэтому принимающая
сторона обязана существовать — иначе в режиме `BOT_MODE=webhook` бот молча
перестаёт отвечать.
"""

from __future__ import annotations

import pytest

from app.core.config import settings

WEBHOOK_PATH = settings.webhook_path

UPDATE = {
    "update_id": 1,
    "message": {
        "message_id": 1,
        "date": 1700000000,
        "chat": {"id": 555, "type": "private"},
        "from": {"id": 555, "is_bot": False, "first_name": "Иван"},
        "text": "/help",
    },
}


@pytest.fixture
def webhook_mode(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "bot_mode", "webhook")
    monkeypatch.setattr(settings, "webhook_secret", "s3cret-token")
    return settings


async def test_webhook_disabled_in_polling_mode(client, monkeypatch) -> None:
    monkeypatch.setattr(settings, "bot_mode", "polling")

    response = await client.post(WEBHOOK_PATH, json=UPDATE)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_webhook_rejects_wrong_secret(client, webhook_mode) -> None:
    response = await client.post(
        WEBHOOK_PATH,
        json=UPDATE,
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_webhook_rejects_missing_secret(client, webhook_mode) -> None:
    response = await client.post(WEBHOOK_PATH, json=UPDATE)

    assert response.status_code == 403


async def test_webhook_accepts_valid_update(client, webhook_mode) -> None:
    response = await client.post(
        WEBHOOK_PATH,
        json=UPDATE,
        headers={"X-Telegram-Bot-Api-Secret-Token": "s3cret-token"},
    )

    assert response.status_code == 200


async def test_webhook_rejects_broken_json(client, webhook_mode) -> None:
    response = await client.post(
        WEBHOOK_PATH,
        content=b"not json",
        headers={
            "X-Telegram-Bot-Api-Secret-Token": "s3cret-token",
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "bad_request"


async def test_webhook_requires_secret_in_production(client, monkeypatch) -> None:
    """Без WEBHOOK_SECRET в production адрес мог бы дёрнуть кто угодно."""
    monkeypatch.setattr(settings, "bot_mode", "webhook")
    monkeypatch.setattr(settings, "webhook_secret", "")
    monkeypatch.setattr(settings, "environment", "production")

    response = await client.post(WEBHOOK_PATH, json=UPDATE)

    assert response.status_code == 403
