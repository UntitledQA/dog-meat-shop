"""Заказы в админке. Все роуты требуют прав администратора."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Query

from app.api.deps import AdminUser, DbSession
from app.models import OrderStatus
from app.schemas.common import DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT, Page
from app.schemas.order import AdminOrderOut, OrderStatusUpdate
from app.services import order_service

router = APIRouter(prefix="/admin", tags=["Админ: заказы"])

LimitQuery = Annotated[int, Query(ge=1, le=MAX_PAGE_LIMIT, description="Размер страницы")]
OffsetQuery = Annotated[int, Query(ge=0, description="Смещение от начала списка")]
OrderPath = Annotated[int, Path(ge=1, description="Идентификатор заказа")]


@router.get(
    "/orders",
    response_model=Page[AdminOrderOut],
    summary="Список заказов",
    description="Новые заказы сверху, с фильтром по статусу.",
)
async def list_orders(
    session: DbSession,
    _admin: AdminUser,
    order_status: Annotated[
        OrderStatus | None, Query(alias="status", description="Фильтр по статусу")
    ] = None,
    limit: LimitQuery = DEFAULT_PAGE_LIMIT,
    offset: OffsetQuery = 0,
) -> Page[AdminOrderOut]:
    orders, total = await order_service.list_admin_orders(
        session, status=order_status, limit=limit, offset=offset
    )
    return Page[AdminOrderOut](
        items=[AdminOrderOut.model_validate(o) for o in orders],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/orders/{order_id}",
    response_model=AdminOrderOut,
    summary="Карточка заказа",
)
async def get_order(
    session: DbSession,
    _admin: AdminUser,
    order_id: OrderPath,
) -> AdminOrderOut:
    order = await order_service.get_order_for_admin(session, order_id)
    return AdminOrderOut.model_validate(order)


@router.patch(
    "/orders/{order_id}/status",
    response_model=AdminOrderOut,
    summary="Сменить статус заказа",
    description=(
        "Заказ создаётся сразу в статусе confirmed. Переходы: "
        "самовывоз — confirmed → completed; доставка — confirmed → delivering → "
        "completed (можно и сразу в completed). Статус delivering недоступен "
        "заказам с самовывозом. Отмена возможна из любого статуса, кроме "
        "completed и cancelled: остатки возвращаются ровно один раз. "
        "Установка текущего статуса — no-op."
    ),
)
async def update_order_status(
    session: DbSession,
    _admin: AdminUser,
    order_id: OrderPath,
    payload: OrderStatusUpdate,
) -> AdminOrderOut:
    order = await order_service.update_status(session, order_id, payload.status)
    return AdminOrderOut.model_validate(order)
