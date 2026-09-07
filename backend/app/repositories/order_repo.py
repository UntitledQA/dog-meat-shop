"""Доступ к данным заказов."""

from __future__ import annotations

from sqlalchemy import select

from app.core.db import supports_row_locking
from app.models import Order, OrderStatus
from app.repositories.base import BaseRepository

__all__ = ["OrderRepository"]


class OrderRepository(BaseRepository):
    """Чтение и запись заказов. Проверки прав и статусов — в services/."""

    async def create(self, order: Order) -> Order:
        """Добавляет заказ и делает flush, чтобы получить `order.id`."""
        self.session.add(order)
        await self.session.flush()
        return order

    async def get(self, order_id: int, *, fresh: bool = False) -> Order | None:
        """Заказ по id. `fresh=True` перечитывает данные и связи из БД."""
        stmt = select(Order).where(Order.id == order_id)
        if fresh:
            stmt = stmt.execution_options(populate_existing=True)
        return await self.session.scalar(stmt)

    async def get_for_user(self, order_id: int, user_id: int) -> Order | None:
        return await self.session.scalar(
            select(Order).where(Order.id == order_id, Order.user_id == user_id)
        )

    async def list_for_user(
        self, user_id: int, *, limit: int = 20, offset: int = 0
    ) -> tuple[list[Order], int]:
        stmt = select(Order).where(Order.user_id == user_id)
        total = await self.count(stmt)
        rows = await self.session.scalars(
            stmt.order_by(Order.created_at.desc(), Order.id.desc()).limit(limit).offset(offset)
        )
        return list(rows), total

    async def list_admin(
        self,
        *,
        status: OrderStatus | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Order], int]:
        stmt = select(Order)
        if status is not None:
            stmt = stmt.where(Order.status == status)
        total = await self.count(stmt)
        rows = await self.session.scalars(
            stmt.order_by(Order.created_at.desc(), Order.id.desc()).limit(limit).offset(offset)
        )
        return list(rows), total

    async def lock_order(self, order_id: int) -> Order | None:
        """Блокирует строку заказа на время транзакции (там, где это умеет БД)."""
        stmt = (
            select(Order).where(Order.id == order_id).execution_options(populate_existing=True)
        )
        if supports_row_locking(self.session):
            stmt = stmt.with_for_update(of=Order)
        return await self.session.scalar(stmt)
