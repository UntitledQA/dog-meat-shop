"""Подключение к базе данных и сессии SQLAlchemy 2 (async)."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    """Базовый класс для всех ORM-моделей."""


def _engine_kwargs(url: str) -> dict:
    if url.startswith("sqlite"):
        # SQLite используется только в тестах: пул на одном соединении.
        return {"echo": False, "future": True}
    return {
        "echo": False,
        "future": True,
        "pool_pre_ping": True,
        "pool_size": 10,
        "max_overflow": 20,
    }


engine: AsyncEngine = create_async_engine(settings.database_url, **_engine_kwargs(settings.database_url))

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


def supports_row_locking(session: AsyncSession) -> bool:
    """`SELECT ... FOR UPDATE` есть в PostgreSQL, но не в SQLite (используется в тестах)."""
    dialect_name: str | None = None
    bind = session.bind
    if bind is not None:
        dialect = getattr(bind, "dialect", None)
        dialect_name = getattr(dialect, "name", None)
    if not dialect_name:
        dialect_name = settings.database_url.split(":", 1)[0].split("+", 1)[0]
    return dialect_name not in {"sqlite"}


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI-зависимость: сессия на время запроса."""
    async with SessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
