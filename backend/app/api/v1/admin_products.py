"""Управление каталогом. Все роуты требуют прав администратора."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Path, Query, UploadFile, status

from app.api.deps import AdminUser, DbSession
from app.schemas.common import DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT, Page
from app.schemas.product import ProductCreate, ProductOut, ProductPhotoOut, ProductUpdate
from app.services import product_service, upload_service

router = APIRouter(prefix="/admin", tags=["Админ: товары"])

LimitQuery = Annotated[int, Query(ge=1, le=MAX_PAGE_LIMIT, description="Размер страницы")]
OffsetQuery = Annotated[int, Query(ge=0, description="Смещение от начала списка")]
ProductPath = Annotated[int, Path(ge=1, description="Идентификатор товара")]
PhotoFile = Annotated[UploadFile, File(description="Изображение JPEG, PNG или WebP")]


@router.get(
    "/products",
    response_model=Page[ProductOut],
    summary="Список товаров",
    description="Поиск по названию и описанию, с возможностью показать скрытые товары.",
)
async def list_products(
    session: DbSession,
    _admin: AdminUser,
    include_inactive: Annotated[bool, Query(description="Показывать скрытые товары")] = False,
    search: Annotated[str | None, Query(max_length=255, description="Поиск по тексту")] = None,
    limit: LimitQuery = DEFAULT_PAGE_LIMIT,
    offset: OffsetQuery = 0,
) -> Page[ProductOut]:
    products, total = await product_service.list_products(
        session,
        include_inactive=include_inactive,
        search=search,
        limit=limit,
        offset=offset,
    )
    return Page[ProductOut](items=products, total=total, limit=limit, offset=offset)


@router.post(
    "/products",
    response_model=ProductOut,
    status_code=status.HTTP_201_CREATED,
    summary="Создать товар",
)
async def create_product(
    session: DbSession,
    _admin: AdminUser,
    payload: ProductCreate,
) -> ProductOut:
    product = await product_service.create_product(session, payload)
    return ProductOut.model_validate(product)


@router.patch(
    "/products/{product_id}",
    response_model=ProductOut,
    summary="Изменить товар",
    description="Частичное обновление: изменяются только переданные поля.",
)
async def update_product(
    session: DbSession,
    _admin: AdminUser,
    product_id: ProductPath,
    payload: ProductUpdate,
) -> ProductOut:
    product = await product_service.update_product(session, product_id, payload)
    return ProductOut.model_validate(product)


@router.post(
    "/products/{product_id}/archive",
    response_model=ProductOut,
    summary="Скрыть товар",
    description="Товар исчезает из каталога, но остаётся в истории заказов.",
)
async def archive_product(
    session: DbSession,
    _admin: AdminUser,
    product_id: ProductPath,
) -> ProductOut:
    product = await product_service.archive_product(session, product_id)
    return ProductOut.model_validate(product)


@router.post(
    "/products/{product_id}/restore",
    response_model=ProductOut,
    summary="Вернуть товар в каталог",
)
async def restore_product(
    session: DbSession,
    _admin: AdminUser,
    product_id: ProductPath,
) -> ProductOut:
    product = await product_service.restore_product(session, product_id)
    return ProductOut.model_validate(product)


@router.post(
    "/products/{product_id}/photo",
    response_model=ProductOut,
    summary="Загрузить фото товара",
    description=(
        "Тип файла проверяется по сигнатуре байтов. Прежнее изображение удаляется, "
        "если на него не ссылается ни один другой товар."
    ),
)
async def upload_product_photo(
    session: DbSession,
    _admin: AdminUser,
    product_id: ProductPath,
    file: PhotoFile,
) -> ProductOut:
    product = await product_service.set_product_photo(session, product_id, file)
    return ProductOut.model_validate(product)


@router.post(
    "/uploads/photo",
    response_model=ProductPhotoOut,
    status_code=status.HTTP_201_CREATED,
    summary="Загрузить изображение",
    description="Сохраняет файл и возвращает `photo_url` для последующего создания товара.",
)
async def upload_photo(_admin: AdminUser, file: PhotoFile) -> ProductPhotoOut:
    photo_url = await upload_service.save_image(file)
    return ProductPhotoOut(photo_url=photo_url)
