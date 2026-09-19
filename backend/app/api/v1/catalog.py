"""Каталог для покупателя."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Query

from app.api.deps import CurrentUser, DbSession
from app.models import ProductCategory
from app.schemas.common import DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT, Page
from app.schemas.product import ProductOut
from app.services import catalog_service

router = APIRouter(prefix="/catalog", tags=["Каталог"])

LimitQuery = Annotated[int, Query(ge=1, le=MAX_PAGE_LIMIT, description="Размер страницы")]
OffsetQuery = Annotated[int, Query(ge=0, description="Смещение от начала списка")]
CategoryQuery = Annotated[
    ProductCategory | None, Query(description="Фильтр по категории товара")
]
ProductPath = Annotated[int, Path(ge=1, description="Идентификатор товара")]


@router.get(
    "",
    response_model=Page[ProductOut],
    summary="Список товаров",
    description=(
        "Только товары в продаже. Товар с нулевым остатком виден, но `in_stock=false`. "
        "Необязательный `category` фильтрует по категории."
    ),
)
async def list_catalog(
    session: DbSession,
    _user: CurrentUser,
    category: CategoryQuery = None,
    limit: LimitQuery = DEFAULT_PAGE_LIMIT,
    offset: OffsetQuery = 0,
) -> Page[ProductOut]:
    products, total = await catalog_service.list_catalog(
        session, category=category, limit=limit, offset=offset
    )
    return Page[ProductOut](
        items=[ProductOut.model_validate(p) for p in products],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{product_id}",
    response_model=ProductOut,
    summary="Карточка товара",
    description="Снятый с продажи товар для покупателя недоступен — 404.",
)
async def get_catalog_product(
    session: DbSession,
    _user: CurrentUser,
    product_id: ProductPath,
) -> ProductOut:
    product = await catalog_service.get_catalog_product(session, product_id)
    return ProductOut.model_validate(product)
