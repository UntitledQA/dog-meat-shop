"""Доступ к данным товаров."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, or_, select

from app.core.db import supports_row_locking
from app.models import Product, ProductCategory
from app.repositories.base import BaseRepository

__all__ = ["ProductRepository"]


class ProductRepository(BaseRepository):
    """Чтение и запись каталога. Бизнес-правила — в services/."""

    # --- витрина -----------------------------------------------------------

    async def list_active(
        self, *, category: ProductCategory | None = None, limit: int = 20, offset: int = 0
    ) -> tuple[list[Product], int]:
        """Активные товары каталога. Товар с нулевым остатком тоже виден."""
        stmt = select(Product).where(Product.is_active.is_(True))
        if category is not None:
            stmt = stmt.where(Product.category == category)
        total = await self.count(stmt)
        rows = await self.session.scalars(
            stmt.order_by(Product.id.asc()).limit(limit).offset(offset)
        )
        return list(rows), total

    async def get_active(self, product_id: int) -> Product | None:
        return await self.session.scalar(
            select(Product).where(Product.id == product_id, Product.is_active.is_(True))
        )

    # --- админка -----------------------------------------------------------

    async def list_all(
        self,
        *,
        include_inactive: bool = False,
        search: str | None = None,
        category: ProductCategory | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Product], int]:
        stmt = select(Product)
        if not include_inactive:
            stmt = stmt.where(Product.is_active.is_(True))
        if category is not None:
            stmt = stmt.where(Product.category == category)

        needle = (search or "").strip()
        if needle:
            pattern = f"%{needle.lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(Product.name).like(pattern),
                    func.lower(func.coalesce(Product.description, "")).like(pattern),
                )
            )

        total = await self.count(stmt)
        rows = await self.session.scalars(
            stmt.order_by(Product.id.desc()).limit(limit).offset(offset)
        )
        return list(rows), total

    async def get(self, product_id: int, *, fresh: bool = False) -> Product | None:
        """Товар по id. `fresh=True` перечитывает строку из БД поверх кэша сессии."""
        stmt = select(Product).where(Product.id == product_id)
        if fresh:
            stmt = stmt.execution_options(populate_existing=True)
        return await self.session.scalar(stmt)

    async def create(self, **fields: Any) -> Product:
        product = Product(**fields)
        self.session.add(product)
        await self.session.flush()
        return product

    async def update(self, product: Product, values: dict[str, Any]) -> Product:
        for key, value in values.items():
            setattr(product, key, value)
        await self.session.flush()
        return product

    async def set_active(self, product: Product, is_active: bool) -> Product:
        product.is_active = is_active
        await self.session.flush()
        return product

    # --- остатки -----------------------------------------------------------

    async def lock_by_ids(self, product_ids: Sequence[int]) -> list[Product]:
        """Товары по списку id, отсортированные по id — защита от дедлоков.

        `SELECT ... FOR UPDATE` добавляется только там, где диалект это умеет
        (PostgreSQL). В тестах на SQLite блокировка строк отсутствует.
        """
        unique_ids = sorted(set(product_ids))
        if not unique_ids:
            return []

        stmt = select(Product).where(Product.id.in_(unique_ids)).order_by(Product.id.asc())
        if supports_row_locking(self.session):
            stmt = stmt.with_for_update()
        rows = await self.session.scalars(stmt)
        return list(rows)

    # --- фото --------------------------------------------------------------

    async def photo_url_usage_count(self, photo_url: str | None) -> int:
        """Сколько товаров ссылается на это изображение."""
        if not photo_url:
            return 0
        total = await self.session.scalar(
            select(func.count()).select_from(Product).where(Product.photo_url == photo_url)
        )
        return int(total or 0)
