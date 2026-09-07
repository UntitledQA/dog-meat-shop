"""Точка входа HTTP-приложения.

Бот здесь не запускается: у него собственный процесс/воркер, чтобы падение
опроса Telegram не роняло API.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.errors import register_exception_handlers
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


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings.upload_path.mkdir(parents=True, exist_ok=True)
    logger.info(
        "api_started",
        environment=settings.environment,
        upload_dir=str(settings.upload_path),
        cors_origins=settings.cors_origins,
    )
    yield
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
