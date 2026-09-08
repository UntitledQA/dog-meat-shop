"""Точка входа HTTP-приложения.

Бот здесь не запускается: у него собственный процесс/воркер, чтобы падение
опроса Telegram не роняло API.
"""

from __future__ import annotations

import asyncio
import hmac
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.errors import (
    BadRequestError,
    ForbiddenError,
    NotFoundError,
    register_exception_handlers,
)
from app.core.logging import configure_logging, get_logger
from app.core.ratelimit import RateLimitMiddleware

configure_logging()
logger = get_logger(__name__)

#: Каталог загрузок должен существовать до монтирования StaticFiles.
settings.upload_path.mkdir(parents=True, exist_ok=True)

OPENAPI_TAGS = [
    {"name": "Авторизация", "description": "Вход через Telegram Mini App"},
    {"name": "Профиль", "description": "Текущий пользователь и настройки магазина"},
    {"name": "Каталог", "description": "Витрина товаров"},
    {"name": "Заказы", "description": "Оформление и просмотр заказов покупателя"},
    {"name": "Админ: товары", "description": "Управление каталогом и изображениями"},
    {"name": "Админ: заказы", "description": "Обработка заказов и смена статусов"},
    {"name": "Служебные", "description": "Проверка работоспособности сервиса"},
]

DESCRIPTION = """
API магазина мяса для собак внутри Telegram Mini App.

* Авторизация — заголовок `X-Telegram-Init-Data` с подписанным initData.
* Все денежные суммы и вес передаются **строками** (`"890.00"`, `"12.500"`),
  чтобы JavaScript не терял точность.
* Ошибки приходят единым форматом: `{"error": {"code", "message", "details"}}`.
"""


#: Как часто пробовать дослать уведомления, которые не ушли с первого раза.
NOTIFICATION_RETRY_INTERVAL_SECONDS = 60.0


async def _notification_retry_loop() -> None:
    """Периодически дожимает очередь недоставленных уведомлений.

    Без этого цикла `retry_failed()` не вызывался бы никем и сообщения,
    не ушедшие из-за временной ошибки Telegram, лежали бы в очереди вечно.
    """
    from app.services.notification_service import retry_failed

    while True:
        try:
            await asyncio.sleep(NOTIFICATION_RETRY_INTERVAL_SECONDS)
            delivered = await retry_failed()
            if delivered:
                logger.info("notification_retry_delivered", count=delivered)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover - фоновая задача не должна падать
            logger.warning("notification_retry_loop_error", error=type(exc).__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings.upload_path.mkdir(parents=True, exist_ok=True)
    logger.info(
        "api_started",
        environment=settings.environment,
        upload_dir=str(settings.upload_path),
        cors_origins=settings.cors_origins,
    )

    retry_task: asyncio.Task | None = None
    if settings.bot_token:
        retry_task = asyncio.create_task(_notification_retry_loop())

    yield

    if retry_task is not None:
        retry_task.cancel()
        with suppress(asyncio.CancelledError):
            await retry_task

    # API-процесс тоже создаёт инстанс бота — для уведомлений о заказах.
    # Его HTTP-сессию нужно закрыть, иначе aiohttp ругается на незакрытый connector.
    from app.bot.bot import shutdown as shutdown_bot

    await shutdown_bot()
    logger.info("api_stopped")


app = FastAPI(
    title="Мясо для собак API",
    version="1.0.0",
    description=DESCRIPTION,
    openapi_tags=OPENAPI_TAGS,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url=None,
    openapi_url="/openapi.json",
)

# Порядок важен: CORS добавляется последним, поэтому оказывается снаружи и
# проставляет заголовки даже на ответ 429 от лимитера.
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=[
        "Content-Type",
        "Accept",
        "X-Telegram-Init-Data",
        "X-Dev-Telegram-Id",
    ],
    expose_headers=["Retry-After"],
    max_age=600,
)

register_exception_handlers(app)

app.include_router(api_router, prefix=settings.api_prefix)

app.mount(
    "/uploads",
    StaticFiles(directory=str(settings.upload_path), check_dir=False),
    name="uploads",
)


@app.get(
    "/health",
    tags=["Служебные"],
    summary="Проверка работоспособности",
    include_in_schema=True,
)
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(settings.webhook_path, include_in_schema=False)
async def telegram_webhook(request: Request) -> Response:
    """Приём обновлений Telegram в режиме `BOT_MODE=webhook`.

    В режиме polling эндпоинт отвечает 404: `bot_main.py` регистрирует адрес
    webhook в Telegram, и без принимающей стороны бот молча переставал бы
    работать.

    Подлинность запроса подтверждается заголовком `X-Telegram-Bot-Api-Secret-Token`
    — его значение задаётся в `WEBHOOK_SECRET` и передаётся Telegram при
    установке webhook. Без секрета адрес может дёрнуть кто угодно, поэтому в
    production он обязателен.
    """
    from aiogram.types import Update

    from app.bot.bot import get_bot, get_dispatcher

    if settings.bot_mode.strip().lower() != "webhook":
        raise NotFoundError("Webhook выключен: BOT_MODE не равен webhook")

    if settings.webhook_secret:
        provided = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if not hmac.compare_digest(provided, settings.webhook_secret):
            logger.warning("webhook_bad_secret")
            raise ForbiddenError("Неверный секрет webhook")
    elif settings.is_production:
        logger.error("webhook_secret_missing")
        raise ForbiddenError("WEBHOOK_SECRET обязателен в production")

    bot = get_bot()
    if bot is None:
        raise NotFoundError("Бот не настроен: не задан BOT_TOKEN")

    try:
        payload = await request.json()
    except ValueError:
        raise BadRequestError("Тело запроса не является JSON") from None

    update = Update.model_validate(payload, context={"bot": bot})
    # Telegram повторяет доставку при ошибке, поэтому обрабатываем и отвечаем 200.
    await get_dispatcher().feed_update(bot, update)
    return Response(status_code=status.HTTP_200_OK)
