"""Витрина каталога для покупателя."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.models import Product, ProductCategory
from app.repositories.product_repo import ProductRepository

__all__ = ["get_catalog_product", "list_catalog"]


async def list_catalog(
    session: AsyncSession,
    *,
    category: ProductCategory | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Product], int]:
    """Активные товары. Товар с нулевым остатком остаётся видимым (`in_stock=false`).

    `category` фильтрует по категории; `None` — все категории (включая товары без неё).
    """
    return await ProductRepository(session).list_active(
        category=category, limit=limit, offset=offset
    )


async def get_catalog_product(session: AsyncSession, product_id: int) -> Product:
    """Карточка товара. Скрытый товар для покупателя не существует — 404."""
    product = await ProductRepository(session).get_active(product_id)
    if product is None:
        raise NotFoundError("Товар не найден или снят с продажи")
    return product
