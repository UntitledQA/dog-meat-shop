"""Ограничение частоты запросов (in-memory, без внешних зависимостей).

Реализация — скользящее окно (sliding window) на `collections.deque` с отметками времени
каждого запроса и `asyncio.Lock` для защиты общего состояния. По сравнению с фиксированным
окном скользящее не позволяет отправить 2×N запросов на стыке двух окон.

Подключение (делает `app/main.py`)::

    app.add_middleware(RateLimitMiddleware)

Лимиты берутся из `settings` в формате ``"N/секунды"`` и перечитываются на каждом запросе,
поэтому в тестах достаточно подменить значение (`monkeypatch.setattr(settings, ...)`) или
выставить `RATE_LIMIT_ENABLED = False`.

ВАЖНО: это защита от случайного «залипания» кнопки и грубого перебора в рамках одного
процесса. Она не переживает рестарт, не синхронизируется между воркерами и не заменяет
ограничения на уровне обратного прокси (nginx `limit_req`) или Cloudflare.
"""

from __future__ import annotations

import asyncio
import json
import math
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Optional
from urllib.parse import parse_qsl

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.core.config import settings
from app.core.errors import error_response
from app.core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Настройки модуля
# ---------------------------------------------------------------------------

#: Глобальный выключатель. Тесты, которым лимит мешает, ставят False.
RATE_LIMIT_ENABLED = True

#: Доверять ли заголовкам `X-Forwarded-For` / `X-Real-IP` при определении IP клиента.
#:
#: РИСК: эти заголовки полностью контролируются клиентом. Если приложение доступно
#: напрямую (без обратного прокси), включённое доверие позволяет обойти любой лимит,
#: просто меняя `X-Forwarded-For` в каждом запросе, — и одновременно позволяет
#: «подставить» чужой IP, заблокировав его для настоящего владельца.
#: Поэтому по умолчанию ВЫКЛЮЧЕНО. Включать только когда приложение гарантированно
#: стоит за доверенным прокси (nginx/Traefik/Cloudflare), который ПЕРЕЗАПИСЫВАЕТ,
#: а не дополняет, эти заголовки: `proxy_set_header X-Forwarded-For $remote_addr;`
TRUST_PROXY_HEADERS = False

#: Максимум одновременно отслеживаемых ключей. Защита от роста памяти при переборе
#: идентификаторов: при превышении вычищаются самые «старые» корзины.
MAX_TRACKED_KEYS = 20_000

#: Как часто (в секундах) проходить по всем корзинам и удалять протухшие.
CLEANUP_INTERVAL_SECONDS = 60.0

#: Ограничение на разбор `X-Telegram-Init-Data` при вычислении ключа (см. security.py).
_MAX_INIT_DATA_LENGTH = 8192

_DISABLED_VALUES = {"", "0", "off", "none", "false", "disabled"}


# ---------------------------------------------------------------------------
# Лимиты
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Limit:
    """Не более `max_requests` запросов за `window_seconds` секунд."""

    max_requests: int
    window_seconds: float

    @property
    def enabled(self) -> bool:
        return self.max_requests > 0 and self.window_seconds > 0


NO_LIMIT = Limit(0, 0.0)


def parse_limit(raw: str | None) -> Limit:
    """Разбирает строку вида ``"30/60"`` (30 запросов в 60 секунд).

    Пустое значение, ``"0"``, ``"off"`` и любой мусор означают «без лимита» —
    неправильная переменная окружения не должна ронять приложение.
    """
    value = (raw or "").strip().lower()
    if value in _DISABLED_VALUES:
        return NO_LIMIT

    count_raw, _, window_raw = value.partition("/")
    try:
        count = int(count_raw.strip())
        window = float(window_raw.strip()) if window_raw.strip() else 60.0
    except ValueError:
        logger.warning("rate_limit_spec_invalid", value=value)
        return NO_LIMIT

    if count <= 0 or window <= 0:
        return NO_LIMIT
    return Limit(count, window)


#: Кэш разбора: ключ — исходная строка из настроек, поэтому подмена настройки
#: в тесте немедленно даёт новый лимит.
_limit_cache: dict[str, Limit] = {}


def limit_for_scope(scope: str) -> Limit:
    """Актуальный лимит для группы путей (`auth` / `orders` / `uploads`)."""
    if not RATE_LIMIT_ENABLED:
        return NO_LIMIT
    raw = getattr(settings, f"rate_limit_{scope}", "") or ""
    cached = _limit_cache.get(raw)
    if cached is None:
        cached = parse_limit(raw)
        _limit_cache[raw] = cached
    return cached


# ---------------------------------------------------------------------------
# Хранилище счётчиков
# ---------------------------------------------------------------------------


@dataclass
class _Bucket:
    window: float
    hits: deque = field(default_factory=deque)

    def expires_at(self) -> float:
        """Момент, после которого корзина заведомо пуста и её можно удалить."""
        return (self.hits[-1] + self.window) if self.hits else 0.0


class SlidingWindowStore:
    """Потокобезопасное (в рамках одного event loop) хранилище скользящих окон."""

    def __init__(self) -> None:
        self._buckets: dict[str, _Bucket] = {}
        self._lock: Optional[asyncio.Lock] = None
        self._lock_loop: object = None
        self._last_cleanup: float = 0.0

    def _get_lock(self) -> asyncio.Lock:
        # Лок создаётся лениво и пересоздаётся при смене event loop:
        # TestClient поднимает свой цикл на каждый запрос, а lock из чужого цикла
        # приводит к RuntimeError.
        loop = asyncio.get_running_loop()
        if self._lock is None or self._lock_loop is not loop:
            self._lock = asyncio.Lock()
            self._lock_loop = loop
        return self._lock

    async def hit(self, key: str, limit: Limit, now: float | None = None) -> float | None:
        """Регистрирует запрос.

        Возвращает `None`, если запрос разрешён, иначе — сколько секунд ждать
        до освобождения слота.
        """
        if not limit.enabled:
            return None

        moment = time.monotonic() if now is None else now
        async with self._get_lock():
            self._maybe_cleanup(moment)

            bucket = self._buckets.get(key)
            if bucket is None or bucket.window != limit.window_seconds:
                bucket = _Bucket(window=limit.window_seconds)
                self._buckets[key] = bucket

            horizon = moment - limit.window_seconds
            hits = bucket.hits
            while hits and hits[0] <= horizon:
                hits.popleft()

            if len(hits) >= limit.max_requests:
                return max(hits[0] + limit.window_seconds - moment, 0.0)

            hits.append(moment)
            return None

    def _maybe_cleanup(self, now: float) -> None:
        """Периодически удаляет протухшие корзины, чтобы память не росла бесконечно."""
        too_many = len(self._buckets) > MAX_TRACKED_KEYS
        if not too_many and now - self._last_cleanup < CLEANUP_INTERVAL_SECONDS:
            return
        self._last_cleanup = now

        stale = [key for key, bucket in self._buckets.items() if bucket.expires_at() <= now]
        for key in stale:
            del self._buckets[key]

        if len(self._buckets) > MAX_TRACKED_KEYS:
            # Аварийный сброс самых «старых» ключей: кто-то перебирает идентификаторы.
            overflow = len(self._buckets) - MAX_TRACKED_KEYS
            oldest = sorted(self._buckets, key=lambda k: self._buckets[k].expires_at())[:overflow]
            for key in oldest:
                del self._buckets[key]
            logger.warning("rate_limit_store_overflow", dropped=len(oldest), kept=len(self._buckets))

    def reset(self) -> None:
        """Полная очистка (используется в тестах)."""
        self._buckets.clear()
        self._last_cleanup = 0.0

    def __len__(self) -> int:  # pragma: no cover - вспомогательное
        return len(self._buckets)


#: Общее хранилище процесса.
store = SlidingWindowStore()


def reset_rate_limits() -> None:
    """Сбрасывает счётчики и кэш лимитов. Вызывать между тестами."""
    store.reset()
    _limit_cache.clear()


# ---------------------------------------------------------------------------
# Определение группы путей и ключа клиента
# ---------------------------------------------------------------------------

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_WRITE_METHODS = {"POST", "PUT", "PATCH"}


def scope_for_request(method: str, path: str) -> str | None:
    """Возвращает имя лимита для запроса или `None`, если путь не лимитируется."""
    if "/auth" in path:
        return "auth"

    if "/photo" in path or "/uploads" in path:
        # Только запись: GET /uploads/<файл> — это раздача картинок каталога,
        # лимитировать её значит ломать витрину при загрузке списка товаров.
        return "uploads" if method in _WRITE_METHODS else None

    if method == "POST" and (path.endswith("/orders") or path.endswith("/orders/")):
        return "orders"

    return None


def _telegram_id_from_headers(request: Request) -> int | None:
    """Достаёт telegram_id из заголовков БЕЗ проверки подписи.

    Это допустимо только как ключ корзины счётчиков: значение НИКОГДА не считается
    подтверждённой личностью (авторизация — исключительно `app/api/deps.py`).
    Подделка заголовка даёт злоумышленнику лишь собственную «свежую» корзину, что не
    страшнее смены IP; полноценная защита от такого перебора — лимиты на прокси.
    """
    for header in ("X-Telegram-Id", "X-Dev-Telegram-Id"):
        raw = request.headers.get(header)
        if raw:
            candidate = raw.strip()
            if candidate.lstrip("-").isdigit() and len(candidate) <= 24:
                return int(candidate)

    init_data = request.headers.get("X-Telegram-Init-Data")
    if not init_data or len(init_data) > _MAX_INIT_DATA_LENGTH:
        return None
    try:
        user_raw = dict(parse_qsl(init_data, keep_blank_values=True)).get("user")
        if not user_raw:
            return None
        user = json.loads(user_raw)
    except (ValueError, UnicodeDecodeError):
        return None
    if isinstance(user, dict) and isinstance(user.get("id"), int):
        return int(user["id"])
    return None


def client_ip(request: Request) -> str:
    """IP клиента. `X-Forwarded-For` учитывается только при `TRUST_PROXY_HEADERS`."""
    if TRUST_PROXY_HEADERS:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # Первый адрес в цепочке — исходный клиент (его дописывает прокси).
            first = forwarded.split(",")[0].strip()
            if first:
                return first[:64]
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()[:64]
    return request.client.host if request.client else "unknown"


def rate_limit_key(request: Request, scope: str) -> str:
    telegram_id = _telegram_id_from_headers(request)
    identity = f"tg:{telegram_id}" if telegram_id is not None else f"ip:{client_ip(request)}"
    return f"{scope}|{identity}"


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

_MESSAGES = {
    "auth": "Слишком много попыток входа. Подождите немного и попробуйте снова.",
    "orders": "Слишком много заказов подряд. Подождите немного и попробуйте снова.",
    "uploads": "Слишком много загрузок подряд. Подождите немного и попробуйте снова.",
}
_DEFAULT_MESSAGE = "Слишком много запросов, попробуйте позже"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Ограничивает частоту обращений к чувствительным путям.

    Подключается без аргументов: `app.add_middleware(RateLimitMiddleware)`.
    """

    def __init__(self, app: ASGIApp, dispatch: Callable | None = None) -> None:
        super().__init__(app, dispatch)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # CORS-preflight не несёт полезной нагрузки и не должен блокироваться,
        # иначе браузер получит 429 без CORS-заголовков и покажет «сетевую ошибку».
        if request.method == "OPTIONS":
            return await call_next(request)

        try:
            retry_after = await self._check(request)
        except Exception as exc:  # pragma: no cover - защитная ветка
            # Сбой самого лимитера не должен ломать API: fail-open + запись в лог.
            logger.error("rate_limit_failed", error=type(exc).__name__, path=request.url.path)
            retry_after = None

        if retry_after is not None:
            return self._too_many_requests(request, retry_after)

        return await call_next(request)

    async def _check(self, request: Request) -> float | None:
        scope = scope_for_request(request.method, request.url.path)
        if scope is None:
            return None

        limit = limit_for_scope(scope)
        if not limit.enabled:
            return None

        return await store.hit(rate_limit_key(request, scope), limit)

    @staticmethod
    def _too_many_requests(request: Request, retry_after_seconds: float) -> Response:
        retry_after = max(1, math.ceil(retry_after_seconds))
        scope = scope_for_request(request.method, request.url.path) or ""
        logger.warning(
            "rate_limited",
            path=request.url.path,
            method=request.method,
            scope=scope,
            retry_after=retry_after,
        )
        response = error_response(
            429,
            "rate_limited",
            _MESSAGES.get(scope, _DEFAULT_MESSAGE),
            {"retry_after": retry_after},
        )
        response.headers["Retry-After"] = str(retry_after)
        return response


__all__ = [
    "Limit",
    "RATE_LIMIT_ENABLED",
    "RateLimitMiddleware",
    "SlidingWindowStore",
    "TRUST_PROXY_HEADERS",
    "client_ip",
    "limit_for_scope",
    "parse_limit",
    "rate_limit_key",
    "reset_rate_limits",
    "scope_for_request",
    "store",
]
