"""Общие фикстуры тестов.

Два принципиальных решения:

1. **Авторизация не отключается.** `user_headers` и `admin_headers` содержат
   настоящий подписанный `initData`, собранный тем же алгоритмом HMAC, что и у
   Telegram. Поэтому каждый тест API проходит боевой путь проверки подписи,
   а не заглушку. Ослабить продовую авторизацию тестами невозможно.
2. **База — SQLite в памяти** на одном соединении (`StaticPool`), поэтому
   транзакции сервисов и проверки теста видят одни и те же данные.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import tempfile
import time
from collections.abc import AsyncIterator
from decimal import Decimal
from urllib.parse import urlencode

# ВАЖНО: переменные окружения выставляются ДО импорта приложения — конфигурация
# читается один раз при импорте `app.core.config`.
TEST_BOT_TOKEN = "123456789:TEST-TOKEN-FOR-PYTEST-ONLY-AAAAAAAAAAAA"
ADMIN_TELEGRAM_ID = 100100100
USER_TELEGRAM_ID = 200200200
OTHER_TELEGRAM_ID = 300300300
DELIVERY_PRICE = Decimal("300.00")

os.environ["ENVIRONMENT"] = "test"
os.environ["BOT_TOKEN"] = TEST_BOT_TOKEN
os.environ["BOT_USERNAME"] = "test_meat_bot"
os.environ["ADMIN_TELEGRAM_IDS"] = str(ADMIN_TELEGRAM_ID)
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["DELIVERY_PRICE"] = str(DELIVERY_PRICE)
os.environ["DEV_AUTH_ENABLED"] = "false"
os.environ["DEV_TELEGRAM_ID"] = "0"
os.environ["ALLOWED_ORIGINS"] = "http://localhost:5173"
os.environ["UPLOAD_DIR"] = tempfile.mkdtemp(prefix="meat-uploads-")
os.environ["MAX_UPLOAD_SIZE_MB"] = "5"
os.environ["LOG_LEVEL"] = "WARNING"
# Лимитер отключён: он проверяется отдельно в tests/test_ratelimit.py.
os.environ["RATE_LIMIT_AUTH"] = "off"
os.environ["RATE_LIMIT_ORDERS"] = "off"
os.environ["RATE_LIMIT_UPLOADS"] = "off"

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.core.db import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Product, User  # noqa: E402

# ---------------------------------------------------------------------------
# Подпись initData
# ---------------------------------------------------------------------------


def build_init_data(
    telegram_id: int,
    *,
    first_name: str = "Тест",
    last_name: str | None = None,
    username: str | None = None,
    auth_date: int | None = None,
    bot_token: str = TEST_BOT_TOKEN,
) -> str:
    """Собирает настоящий подписанный initData Telegram."""
    user: dict[str, object] = {"id": telegram_id, "first_name": first_name}
    if last_name:
        user["last_name"] = last_name
    if username:
        user["username"] = username

    pairs = [
        ("auth_date", str(auth_date if auth_date is not None else int(time.time()))),
        ("query_id", f"AA{telegram_id}"),
        ("user", json.dumps(user, ensure_ascii=False, separators=(",", ":"))),
    ]
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    signature = hmac.new(secret, data_check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode([*pairs, ("hash", signature)])


def auth_headers(telegram_id: int, **kwargs: object) -> dict[str, str]:
    return {"X-Telegram-Init-Data": build_init_data(telegram_id, **kwargs)}  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# База данных
# ---------------------------------------------------------------------------


@pytest.fixture
async def engine() -> AsyncIterator:
    """Отдельная in-memory база на каждый тест."""
    test_engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield test_engine
    await test_engine.dispose()


@pytest.fixture
async def session_factory(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


@pytest.fixture
async def session(session_factory) -> AsyncIterator[AsyncSession]:
    """Сессия для подготовки данных и проверок в тесте."""
    async with session_factory() as db_session:
        yield db_session


@pytest.fixture
async def client(session_factory, notifications) -> AsyncIterator[AsyncClient]:
    """HTTP-клиент поверх приложения с подменённой только базой данных.

    Авторизация, права и лимиты работают штатно.
    """

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        async with session_factory() as db_session:
            try:
                yield db_session
            except Exception:
                await db_session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Уведомления Telegram
# ---------------------------------------------------------------------------


class NotificationRecorder:
    """Перехватывает вызовы уведомлений вместо обращения к Telegram."""

    def __init__(self) -> None:
        self.new_orders: list[int] = []
        self.status_changes: list[tuple[int, str]] = []

    async def notify_new_order(self, order_id: int) -> None:
        self.new_orders.append(order_id)

    async def notify_order_status_changed(self, order_id: int, new_status) -> None:
        self.status_changes.append((order_id, getattr(new_status, "value", str(new_status))))


@pytest.fixture(autouse=True)
def notifications(monkeypatch: pytest.MonkeyPatch) -> NotificationRecorder:
    """Подменяет отправку в Telegram, но оставляет боевой путь вызова.

    Так проверяется реальная связка `order_service` -> `notification_service`:
    имена и сигнатуры функций должны совпадать, иначе тесты упадут.
    """
    from app.services import notification_service

    recorder = NotificationRecorder()
    monkeypatch.setattr(notification_service, "notify_new_order", recorder.notify_new_order)
    monkeypatch.setattr(
        notification_service,
        "notify_order_status_changed",
        recorder.notify_order_status_changed,
    )
    return recorder


# ---------------------------------------------------------------------------
# Заголовки авторизации
# ---------------------------------------------------------------------------


@pytest.fixture
def user_headers() -> dict[str, str]:
    """Обычный покупатель: подписанный initData, telegram_id вне списка админов."""
    return auth_headers(USER_TELEGRAM_ID, first_name="Иван", username="ivan")


@pytest.fixture
def other_user_headers() -> dict[str, str]:
    """Второй покупатель — для проверки доступа к чужим заказам."""
    return auth_headers(OTHER_TELEGRAM_ID, first_name="Пётр", username="petr")


@pytest.fixture
def admin_headers() -> dict[str, str]:
    """Администратор: telegram_id из ADMIN_TELEGRAM_IDS."""
    return auth_headers(ADMIN_TELEGRAM_ID, first_name="Админ", username="admin")


# ---------------------------------------------------------------------------
# Данные
# ---------------------------------------------------------------------------


@pytest.fixture
async def make_product(session: AsyncSession):
    """Фабрика товаров прямо в базе."""

    async def _make(
        name: str = "Говядина",
        price_per_kg: str = "890.00",
        stock_kg: str = "10.000",
        *,
        is_active: bool = True,
        description: str | None = "Свежая говядина для собак",
        photo_url: str | None = None,
    ) -> Product:
        product = Product(
            name=name,
            description=description,
            price_per_kg=Decimal(price_per_kg),
            stock_kg=Decimal(stock_kg),
            photo_url=photo_url,
            is_active=is_active,
        )
        session.add(product)
        await session.commit()
        await session.refresh(product)
        return product

    return _make


@pytest.fixture
async def make_user(session: AsyncSession):
    """Фабрика пользователей."""

    async def _make(telegram_id: int, *, is_admin: bool = False, name: str = "Тест") -> User:
        user = User(telegram_id=telegram_id, first_name=name, is_admin=is_admin)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user

    return _make


def order_payload(
    product_id: int,
    weight_kg: str = "2.0",
    *,
    delivery_type: str = "delivery",
    **overrides: object,
) -> dict[str, object]:
    """Готовое тело запроса на создание заказа."""
    payload: dict[str, object] = {
        "items": [{"product_id": product_id, "weight_kg": weight_kg}],
        "delivery_type": delivery_type,
        "customer_name": "Иван Петров",
        "phone": "+79991234567",
        "delivery_date": "2030-01-15",
        "delivery_time": "12:00-15:00",
        "comment": "Позвонить заранее",
    }
    if delivery_type == "delivery":
        payload["address"] = "г. Москва, ул. Ленина, д. 1, кв. 5"
    payload.update(overrides)
    return payload
