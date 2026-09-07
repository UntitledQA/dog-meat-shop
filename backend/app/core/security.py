"""Проверка подписи Telegram Mini App initData.

Алгоритм (официальная документация Telegram):

    data_check_string = "\\n".join(f"{k}={v}" for k, v in sorted(pairs) if k != "hash")
    secret_key        = HMAC_SHA256(key=b"WebAppData", msg=bot_token)
    calculated_hash   = HMAC_SHA256(key=secret_key, msg=data_check_string).hexdigest()

Подпись считается верной, только если `calculated_hash == hash` (сравнение постоянного времени)
и `auth_date` не старше TTL.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl

from app.core.errors import UnauthorizedError

_MAX_INIT_DATA_LENGTH = 8192


@dataclass(frozen=True)
class TelegramUserData:
    """Данные пользователя, извлечённые ТОЛЬКО из проверенного initData."""

    telegram_id: int
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    auth_date: int = 0
    is_dev: bool = False


def build_data_check_string(pairs: list[tuple[str, str]]) -> str:
    return "\n".join(f"{key}={value}" for key, value in sorted(pairs) if key != "hash")


def compute_init_data_hash(data_check_string: str, bot_token: str) -> str:
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    return hmac.new(
        secret_key, data_check_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def parse_and_verify_init_data(
    raw: str,
    bot_token: str,
    ttl_seconds: int = 86400,
) -> TelegramUserData:
    """Разбирает и проверяет initData. Бросает UnauthorizedError при любой проблеме."""
    if not raw or not raw.strip():
        raise UnauthorizedError("Отсутствуют данные авторизации Telegram")
    if len(raw) > _MAX_INIT_DATA_LENGTH:
        raise UnauthorizedError("Данные авторизации Telegram слишком длинные")
    if not bot_token:
        # Без токена проверить подпись невозможно — считаем запрос неавторизованным.
        raise UnauthorizedError("Сервер не настроен для авторизации Telegram")

    pairs = parse_qsl(raw, keep_blank_values=True, strict_parsing=False)
    if not pairs:
        raise UnauthorizedError("Некорректные данные авторизации Telegram")

    data = dict(pairs)
    received_hash = data.get("hash")
    if not received_hash:
        raise UnauthorizedError("Подпись Telegram отсутствует")

    expected_hash = compute_init_data_hash(build_data_check_string(pairs), bot_token)
    if not hmac.compare_digest(expected_hash, received_hash):
        raise UnauthorizedError("Неверная подпись данных Telegram")

    auth_date_raw = data.get("auth_date", "")
    try:
        auth_date = int(auth_date_raw)
    except (TypeError, ValueError):
        raise UnauthorizedError("Некорректное поле auth_date") from None

    if ttl_seconds > 0:
        age = time.time() - auth_date
        if age > ttl_seconds:
            raise UnauthorizedError("Сессия Telegram устарела, откройте приложение заново")
        if age < -300:
            # Значительное время из будущего — данные подделаны или часы рассинхронизированы.
            raise UnauthorizedError("Некорректное время авторизации Telegram")

    user_raw = data.get("user")
    if not user_raw:
        raise UnauthorizedError("В данных Telegram отсутствует пользователь")

    try:
        user = json.loads(user_raw)
    except json.JSONDecodeError:
        raise UnauthorizedError("Некорректные данные пользователя Telegram") from None

    if not isinstance(user, dict) or not isinstance(user.get("id"), int):
        raise UnauthorizedError("Некорректный идентификатор пользователя Telegram")

    return TelegramUserData(
        telegram_id=int(user["id"]),
        username=_clean(user.get("username"), 64),
        first_name=_clean(user.get("first_name"), 128),
        last_name=_clean(user.get("last_name"), 128),
        auth_date=auth_date,
    )


def _clean(value: object, max_length: int) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value[:max_length] or None
