"""Бизнес-логика заказов: создание, чтение, статусы, отмена.

Здесь живёт самое важное правило проекта: **корзина фронта не является
источником истины**. Цены, названия и остатки читаются из БД внутри той же
транзакции, в которой списывается остаток.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import (
    ForbiddenError,
    InsufficientStockError,
    InvalidStatusTransitionError,
    NotFoundError,
    ProductUnavailableError,
)
from app.core.logging import get_logger
from app.core.money import line_total, round_money, round_weight
from app.models import (
    DeliveryType,
    Order,
    OrderItem,
    OrderStatus,
    Product,
    User,
    can_transition,
    is_allowed_for_delivery_type,
    status_label,
)
from app.repositories.order_repo import OrderRepository
from app.repositories.product_repo import ProductRepository
from app.schemas.order import OrderCreate

__all__ = [
    "cancel_order",
    "create_order",
    "get_order_for_admin",
    "get_order_for_user",
    "list_admin_orders",
    "list_user_orders",
    "update_status",
]

logger = get_logger(__name__)

ZERO_MONEY = Decimal("0.00")


# --------------------------------------------------------------------------
# уведомления
# --------------------------------------------------------------------------


async def _notify_new_order(order: Order) -> None:
    """Уведомление о новом заказе.

    Сбой отправки не должен откатывать уже созданный заказ, поэтому исключения
    гасятся и логируются. Сам `notification_service` тоже не бросает наружу —
    это второй рубеж защиты.
    """
    if not settings.bot_token:
        return
    try:
        from app.services.notification_service import notify_new_order

        await notify_new_order(order.id)
    except Exception as exc:  # pragma: no cover - канал доставки ненадёжен
        logger.warning(
            "notification_failed", event="new_order", order_id=order.id, error=str(exc)
        )


async def _notify_status_changed(order: Order) -> None:
    """Уведомление о смене статуса. Ошибки не влияют на результат операции."""
    if not settings.bot_token:
        return
    try:
        from app.services.notification_service import notify_order_status_changed

        await notify_order_status_changed(order.id, order.status)
    except Exception as exc:  # pragma: no cover - канал доставки ненадёжен
        logger.warning(
            "notification_failed",
            event="status_changed",
            order_id=order.id,
            error=str(exc),
        )


# --------------------------------------------------------------------------
# создание
# --------------------------------------------------------------------------


def _delivery_price(delivery_type: DeliveryType) -> Decimal:
    if delivery_type == DeliveryType.DELIVERY:
        return round_money(settings.delivery_price)
    return ZERO_MONEY


def _stock_problem(product: Product, requested: Decimal) -> dict[str, str | int]:
    return {
        "product_id": product.id,
        "product_name": product.name,
        "requested_kg": f"{round_weight(requested):.3f}",
        "available_kg": f"{round_weight(product.stock_kg):.3f}",
    }


async def create_order(session: AsyncSession, user: User, payload: OrderCreate) -> Order:
    """Создаёт заказ в одной транзакции со списанием остатков.

    Порядок действий важен:
      1. товары выбираются `WHERE id IN (...) ORDER BY id` — единый порядок
         блокировки во всех операциях защищает от дедлоков;
      2. `FOR UPDATE` добавляется только там, где диалект это поддерживает;
      3. проверяются активность и остаток — собираются ВСЕ проблемные позиции;
      4. суммы считаются по ценам из БД;
      5. остатки списываются, заказ вставляется, `flush()` даёт id,
         из него собирается `order_number`, и только потом `commit()`.
    """
    products_repo = ProductRepository(session)
    orders_repo = OrderRepository(session)

    requested: dict[int, Decimal] = {
        item.product_id: round_weight(item.weight_kg) for item in payload.items
    }
    product_ids = sorted(requested)
    created_at = datetime.now(timezone.utc)

    try:
        products = await products_repo.lock_by_ids(product_ids)
        by_id = {product.id: product for product in products}

        missing = [pid for pid in product_ids if pid not in by_id]
        if missing:
            raise NotFoundError(
                "Товар из корзины больше не существует",
                details={"product_ids": missing},
            )

        unavailable = [by_id[pid] for pid in product_ids if not by_id[pid].is_active]
        if unavailable:
            names = ", ".join(f"«{p.name}»" for p in unavailable)
            raise ProductUnavailableError(
                f"Товар снят с продажи: {names}",
                details={
                    "items": [
                        {"product_id": p.id, "product_name": p.name} for p in unavailable
                    ]
                },
            )

        problems = [
            _stock_problem(by_id[pid], requested[pid])
            for pid in product_ids
            if requested[pid] > round_weight(by_id[pid].stock_kg)
        ]
        if problems:
            names = ", ".join(f"«{item['product_name']}»" for item in problems)
            raise InsufficientStockError(
                f"Недостаточно товара: {names}",
                details={"items": problems},
            )

        items: list[OrderItem] = []
        subtotal = ZERO_MONEY
        for product_id in product_ids:
            product = by_id[product_id]
            weight = requested[product_id]
            price = round_money(product.price_per_kg)
            total_for_line = line_total(weight, price)
            subtotal += total_for_line

            # Списание остатка идёт по данным из БД, а не из запроса.
            product.stock_kg = round_weight(product.stock_kg - weight)

            items.append(
                OrderItem(
                    product_id=product.id,
                    product_name=product.name,
                    weight_kg=weight,
                    price_per_kg=price,
                    line_total=total_for_line,
                )
            )

        subtotal = round_money(subtotal)
        delivery_price = _delivery_price(payload.delivery_type)
        total = round_money(subtotal + delivery_price)

        order = Order(
            order_number="",
            user_id=user.id,
            # Отдельного «нового» статуса нет: оформленный заказ сразу подтверждён.
            status=OrderStatus.CONFIRMED,
            delivery_type=payload.delivery_type,
            customer_name=payload.customer_name,
            phone=payload.phone,
            address=(payload.address or None),
            # Пустая строка от формы — это «не заполнено», а не значение.
            # Координаты через `or None` гонять нельзя: Decimal("0") — валидный ноль.
            address_city=(payload.address_city or None),
            address_street=(payload.address_street or None),
            address_house=(payload.address_house or None),
            address_postal_code=(payload.address_postal_code or None),
            address_lat=payload.address_lat,
            address_lon=payload.address_lon,
            delivery_date=payload.delivery_date,
            comment=payload.comment,
            subtotal=subtotal,
            delivery_price=delivery_price,
            total=total,
            items=items,
            created_at=created_at,
            updated_at=created_at,
        )
        await orders_repo.create(order)

        # Номер строится из уже выданного id — уникален без отдельного счётчика.
        order.order_number = f"ORD-{created_at:%Y%m%d}-{order.id:05d}"

        # Телефон покупателя запоминаем в профиле для следующего заказа.
        if user.phone != payload.phone:
            user.phone = payload.phone

        await session.flush()
        await session.commit()
    except Exception:
        await session.rollback()
        raise

    fresh = await orders_repo.get(order.id, fresh=True)
    order = fresh if fresh is not None else order

    logger.info(
        "order_created",
        order_id=order.id,
        order_number=order.order_number,
        user_id=user.id,
        total=str(order.total),
        items=len(order.items),
    )
    await _notify_new_order(order)
    return order


# --------------------------------------------------------------------------
# чтение
# --------------------------------------------------------------------------


async def list_user_orders(
    session: AsyncSession, user: User, *, limit: int = 20, offset: int = 0
) -> tuple[list[Order], int]:
    return await OrderRepository(session).list_for_user(user.id, limit=limit, offset=offset)


async def get_order_for_user(session: AsyncSession, order_id: int, user: User) -> Order:
    """Заказ покупателя.

    Чужой заказ — это 403 (`forbidden`), а не 404: так требует контракт.
    Проверка выполняется на бэкенде, UI на неё не влияет.
    """
    order = await OrderRepository(session).get(order_id)
    if order is None:
        raise NotFoundError("Заказ не найден")
    if order.user_id != user.id:
        raise ForbiddenError("Этот заказ принадлежит другому пользователю")
    return order


async def list_admin_orders(
    session: AsyncSession,
    *,
    status: OrderStatus | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Order], int]:
    return await OrderRepository(session).list_admin(status=status, limit=limit, offset=offset)


async def get_order_for_admin(session: AsyncSession, order_id: int) -> Order:
    order = await OrderRepository(session).get(order_id)
    if order is None:
        raise NotFoundError("Заказ не найден")
    return order


# --------------------------------------------------------------------------
# статусы и отмена
# --------------------------------------------------------------------------


async def _restore_stock(session: AsyncSession, order: Order) -> None:
    """Возвращает остатки по позициям заказа. Вызывается ровно один раз."""
    products_repo = ProductRepository(session)
    product_ids = sorted({item.product_id for item in order.items if item.product_id})
    if not product_ids:
        return

    products = {p.id: p for p in await products_repo.lock_by_ids(product_ids)}
    for item in order.items:
        product = products.get(item.product_id) if item.product_id else None
        if product is None:
            # Товар удалён из каталога — возвращать остаток некуда.
            continue
        product.stock_kg = round_weight(product.stock_kg + item.weight_kg)


async def _cancel_locked(session: AsyncSession, order: Order) -> Order:
    """Отмена уже заблокированного заказа. Идемпотентна по двум признакам."""
    if order.status == OrderStatus.CANCELLED or order.stock_restored_at is not None:
        # Повторная отмена: остаток возвращать нельзя ни при каких условиях.
        logger.info("order_cancel_skipped", order_id=order.id, status=order.status.value)
        return order

    if not can_transition(order.status, OrderStatus.CANCELLED):
        raise InvalidStatusTransitionError(
            f"Заказ в статусе «{status_label(order.status)}» отменить нельзя"
        )

    try:
        await _restore_stock(session, order)
        order.status = OrderStatus.CANCELLED
        order.stock_restored_at = datetime.now(timezone.utc)
        await session.flush()
        await session.commit()
    except Exception:
        await session.rollback()
        raise

    refreshed = await OrderRepository(session).get(order.id, fresh=True)
    order = refreshed if refreshed is not None else order

    logger.info("order_cancelled", order_id=order.id, order_number=order.order_number)
    await _notify_status_changed(order)
    return order


async def cancel_order(session: AsyncSession, order_id: int) -> Order:
    """Отменяет заказ и возвращает остатки — ровно один раз."""
    orders_repo = OrderRepository(session)
    order = await orders_repo.lock_order(order_id)
    if order is None:
        raise NotFoundError("Заказ не найден")
    return await _cancel_locked(session, order)


async def update_status(session: AsyncSession, order_id: int, new_status: OrderStatus) -> Order:
    """Меняет статус заказа в транзакции с блокировкой строки.

    Установка текущего статуса — no-op: данные не меняются, уведомление
    не отправляется. Переход в `cancelled` идёт через общий код отмены.
    """
    orders_repo = OrderRepository(session)
    order = await orders_repo.lock_order(order_id)
    if order is None:
        raise NotFoundError("Заказ не найден")

    if order.status == new_status:
        logger.info("order_status_noop", order_id=order.id, status=new_status.value)
        return order

    if new_status == OrderStatus.CANCELLED:
        return await _cancel_locked(session, order)

    if not can_transition(order.status, new_status):
        raise InvalidStatusTransitionError(
            f"Нельзя перевести заказ из статуса «{status_label(order.status)}» "
            f"в «{status_label(new_status)}»"
        )

    # «Доставляется» бессмысленно для самовывоза: забирают сами, везти некому.
    # Проверяем на бэкенде — то, что интерфейс не показывает кнопку, не защита.
    if not is_allowed_for_delivery_type(new_status, order.delivery_type):
        raise InvalidStatusTransitionError(
            f"Статус «{status_label(new_status)}» не подходит заказу с самовывозом"
        )

    previous = order.status
    try:
        order.status = new_status
        await session.flush()
        await session.commit()
    except Exception:
        await session.rollback()
        raise

    refreshed = await orders_repo.get(order.id, fresh=True)
    order = refreshed if refreshed is not None else order

    logger.info(
        "order_status_changed",
        order_id=order.id,
        previous=previous.value,
        current=new_status.value,
    )
    await _notify_status_changed(order)
    return order
