"""Управление каталогом из админки."""

from __future__ import annotations

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.models import Product, ProductCategory
from app.repositories.product_repo import ProductRepository
from app.schemas.product import ProductCreate, ProductUpdate
from app.services.upload_service import remove_photo_if_unused, save_image

__all__ = [
    "archive_product",
    "create_product",
    "get_product",
    "list_products",
    "restore_product",
    "set_product_photo",
    "update_product",
]

logger = get_logger(__name__)


async def list_products(
    session: AsyncSession,
    *,
    include_inactive: bool = False,
    search: str | None = None,
    category: ProductCategory | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Product], int]:
    return await ProductRepository(session).list_all(
        include_inactive=include_inactive,
        search=search,
        category=category,
        limit=limit,
        offset=offset,
    )


async def get_product(session: AsyncSession, product_id: int) -> Product:
    product = await ProductRepository(session).get(product_id)
    if product is None:
        raise NotFoundError("Товар не найден")
    return product


async def create_product(session: AsyncSession, payload: ProductCreate) -> Product:
    products = ProductRepository(session)
    try:
        product = await products.create(
            name=payload.name,
            description=payload.description,
            category=payload.category,
            price_per_kg=payload.price_per_kg,
            stock_kg=payload.stock_kg,
            photo_url=payload.photo_url,
            is_active=payload.is_active,
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise

    # created_at/updated_at приходят из server_default — забираем их из БД.
    await session.refresh(product)
    logger.info("product_created", product_id=product.id, name=product.name)
    return product


async def update_product(
    session: AsyncSession, product_id: int, payload: ProductUpdate
) -> Product:
    """Частичное обновление. Заменённое фото удаляется, если больше не используется."""
    products = ProductRepository(session)
    product = await products.get(product_id)
    if product is None:
        raise NotFoundError("Товар не найден")

    values = payload.model_dump(exclude_unset=True)
    if not values:
        return product

    old_photo = product.photo_url
    photo_changed = "photo_url" in values and values["photo_url"] != old_photo

    try:
        await products.update(product, values)
        await session.commit()
    except Exception:
        await session.rollback()
        raise

    await session.refresh(product)

    if photo_changed:
        await remove_photo_if_unused(products, old_photo)

    logger.info("product_updated", product_id=product.id, fields=sorted(values))
    return product


async def _switch_active(session: AsyncSession, product_id: int, is_active: bool) -> Product:
    products = ProductRepository(session)
    product = await products.get(product_id)
    if product is None:
        raise NotFoundError("Товар не найден")

    if product.is_active == is_active:
        return product

    try:
        await products.set_active(product, is_active)
        await session.commit()
    except Exception:
        await session.rollback()
        raise

    await session.refresh(product)
    logger.info("product_active_changed", product_id=product.id, is_active=is_active)
    return product


async def archive_product(session: AsyncSession, product_id: int) -> Product:
    """Скрывает товар из каталога. Историю заказов это не меняет."""
    return await _switch_active(session, product_id, False)


async def restore_product(session: AsyncSession, product_id: int) -> Product:
    """Возвращает товар в каталог."""
    return await _switch_active(session, product_id, True)


async def set_product_photo(
    session: AsyncSession, product_id: int, file: UploadFile
) -> Product:
    """Загружает изображение и привязывает его к товару."""
    products = ProductRepository(session)
    product = await products.get(product_id)
    if product is None:
        raise NotFoundError("Товар не найден")

    old_photo = product.photo_url
    new_photo = await save_image(file)

    try:
        await products.update(product, {"photo_url": new_photo})
        await session.commit()
    except Exception:
        await session.rollback()
        # Новый файл уже на диске, но в БД не попал — подчищаем за собой.
        await remove_photo_if_unused(products, new_photo)
        raise

    await session.refresh(product)

    if old_photo and old_photo != new_photo:
        await remove_photo_if_unused(products, old_photo)

    logger.info("product_photo_set", product_id=product.id)
    return product
