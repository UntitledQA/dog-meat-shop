"""Базовый репозиторий.

Слой репозиториев — это только доступ к данным: никаких проверок остатка,
расчёта сумм и прочей бизнес-логики. Всё это живёт в services/.
"""

from __future__ import annotations

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["BaseRepository"]


class BaseRepository:
    """Хранит сессию и общие помощники запросов."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def count(self, stmt: Select) -> int:
        """Количество строк для запроса `stmt` без учёта limit/offset."""
        subquery = stmt.order_by(None).limit(None).offset(None).subquery()
        total = await self.session.scalar(select(func.count()).select_from(subquery))
        return int(total or 0)
