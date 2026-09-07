"""Заказы покупателя."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Query, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.common import DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT, Page
from app.schemas.order import OrderCreate, OrderOut
from app.services import order_service

router = APIRouter(prefix="/orders", tags=["Заказы"])

LimitQuery = Annotated[int, Query(ge=1, le=MAX_PAGE_LIMIT, description="Размер страницы")]
OffsetQuery = Annotated[int, Query(ge=0, description="Смещение от начала списка")]
OrderPath = Annotated[int, Path(ge=1, description="Идентификатор заказа")]


@router.post(
    "",
    response_model=OrderOut,
    status_code=status.HTTP_201_CREATED,
    summary="Оформить заказ",
    description=(
        "Суммы считает бэкенд по ценам из БД: содержимое корзины на фронте не является "
        "источником истины. Остатки списываются в той же транзакции."
    ),
)
async def create_order(
    session: DbSession,
    user: CurrentUser,
    payload: OrderCreate,
) -> OrderOut:
    order = await order_service.create_order(session, user, payload)
    return OrderOut.model_validate(order)


@router.get(
    "",
    response_model=Page[OrderOut],
    summary="Мои заказы",
    description="Заказы текущего пользователя, новые сверху.",
)
async def list_orders(
    session: DbSession,
    user: CurrentUser,
    limit: LimitQuery = DEFAULT_PAGE_LIMIT,
    offset: OffsetQuery = 0,
) -> Page[OrderOut]:
    orders, total = await order_service.list_user_orders(
        session, user, limit=limit, offset=offset
    )
    return Page[OrderOut](items=orders, total=total, limit=limit, offset=offset)


@router.get(
    "/{order_id}",
    response_model=OrderOut,
    summary="Заказ",
    description="Чужой заказ недоступен: сервер отвечает 403 `forbidden`.",
)
async def get_order(
    session: DbSession,
    user: CurrentUser,
    order_id: OrderPath,
) -> OrderOut:
    order = await order_service.get_order_for_user(session, order_id, user)
    return OrderOut.model_validate(order)
