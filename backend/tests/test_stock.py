"""Остатки: списание, превышение, возврат при отмене и его идемпотентность."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select

from app.models import Order, OrderStatus, Product
from tests.conftest import order_payload

PREFIX = "/api/v1"


async def _stock(session, product_id: int) -> Decimal:
    session.expire_all()
    product = await session.scalar(select(Product).where(Product.id == product_id))
    return Decimal(str(product.stock_kg))


async def _status(session, order_id: int) -> OrderStatus:
    session.expire_all()
    order = await session.scalar(select(Order).where(Order.id == order_id))
    return order.status


# ---------------------------------------------------------------------------
# Списание
# ---------------------------------------------------------------------------


async def test_stock_decreases_after_order(client, user_headers, make_product, session) -> None:
    product = await make_product(stock_kg="10.0")

    response = await client.post(
        f"{PREFIX}/orders", json=order_payload(product.id, "2.5"), headers=user_headers
    )

    assert response.status_code == 201
    assert await _stock(session, product.id) == Decimal("7.500")


async def test_stock_decreases_for_each_item(client, user_headers, make_product, session) -> None:
    beef = await make_product(name="Говядина", stock_kg="10.0")
    turkey = await make_product(name="Индейка", stock_kg="5.0")

    payload = order_payload(beef.id, "1.0")
    payload["items"] = [
        {"product_id": beef.id, "weight_kg": "1.0"},
        {"product_id": turkey.id, "weight_kg": "0.5"},
    ]
    await client.post(f"{PREFIX}/orders", json=payload, headers=user_headers)

    assert await _stock(session, beef.id) == Decimal("9.000")
    assert await _stock(session, turkey.id) == Decimal("4.500")


async def test_order_can_take_entire_stock(client, user_headers, make_product, session) -> None:
    product = await make_product(stock_kg="3.0")

    response = await client.post(
        f"{PREFIX}/orders", json=order_payload(product.id, "3.0"), headers=user_headers
    )

    assert response.status_code == 201
    assert await _stock(session, product.id) == Decimal("0.000")


# ---------------------------------------------------------------------------
# Превышение остатка
# ---------------------------------------------------------------------------


async def test_order_above_stock_is_rejected(client, user_headers, make_product, session) -> None:
    product = await make_product(name="Говядина", stock_kg="1.5")

    response = await client.post(
        f"{PREFIX}/orders", json=order_payload(product.id, "3.0"), headers=user_headers
    )

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "insufficient_stock"
    # В ошибке указан проблемный товар и доступное количество.
    problem = error["details"]["items"][0]
    assert problem["product_id"] == product.id
    assert problem["product_name"] == "Говядина"
    assert problem["requested_kg"] == "3.000"
    assert problem["available_kg"] == "1.500"
    # Остаток не тронут.
    assert await _stock(session, product.id) == Decimal("1.500")


async def test_out_of_stock_product_cannot_be_ordered(
    client, user_headers, make_product
) -> None:
    product = await make_product(stock_kg="0")

    response = await client.post(
        f"{PREFIX}/orders", json=order_payload(product.id, "0.1"), headers=user_headers
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "insufficient_stock"


async def test_all_problem_items_are_reported(client, user_headers, make_product) -> None:
    """В ошибке перечисляются все проблемные позиции, а не только первая."""
    beef = await make_product(name="Говядина", stock_kg="0.5")
    turkey = await make_product(name="Индейка", stock_kg="0.2")

    payload = order_payload(beef.id, "1.0")
    payload["items"] = [
        {"product_id": beef.id, "weight_kg": "1.0"},
        {"product_id": turkey.id, "weight_kg": "1.0"},
    ]
    response = await client.post(f"{PREFIX}/orders", json=payload, headers=user_headers)

    problems = response.json()["error"]["details"]["items"]
    assert {item["product_name"] for item in problems} == {"Говядина", "Индейка"}


async def test_second_order_cannot_exceed_remaining_stock(
    client, user_headers, make_product, session
) -> None:
    """Последовательные заказы не могут суммарно превысить остаток."""
    product = await make_product(stock_kg="2.0")

    first = await client.post(
        f"{PREFIX}/orders", json=order_payload(product.id, "1.5"), headers=user_headers
    )
    second = await client.post(
        f"{PREFIX}/orders", json=order_payload(product.id, "1.0"), headers=user_headers
    )

    assert first.status_code == 201
    assert second.status_code == 409
    assert await _stock(session, product.id) == Decimal("0.500")


async def test_failed_order_does_not_create_record(
    client, user_headers, make_product, session
) -> None:
    """Транзакция откатывается целиком: заказа нет, остаток на месте."""
    beef = await make_product(name="Говядина", stock_kg="10.0")
    turkey = await make_product(name="Индейка", stock_kg="0.1")

    payload = order_payload(beef.id, "1.0")
    payload["items"] = [
        {"product_id": beef.id, "weight_kg": "1.0"},
        {"product_id": turkey.id, "weight_kg": "5.0"},
    ]
    response = await client.post(f"{PREFIX}/orders", json=payload, headers=user_headers)

    assert response.status_code == 409
    assert await _stock(session, beef.id) == Decimal("10.000")
    assert await _stock(session, turkey.id) == Decimal("0.100")
    assert (await client.get(f"{PREFIX}/orders", headers=user_headers)).json()["total"] == 0


# ---------------------------------------------------------------------------
# Возврат остатка при отмене
# ---------------------------------------------------------------------------


async def test_cancel_restores_stock(
    client, user_headers, admin_headers, make_product, session
) -> None:
    product = await make_product(stock_kg="10.0")
    order = (
        await client.post(
            f"{PREFIX}/orders", json=order_payload(product.id, "2.0"), headers=user_headers
        )
    ).json()
    assert await _stock(session, product.id) == Decimal("8.000")

    response = await client.patch(
        f"{PREFIX}/admin/orders/{order['id']}/status",
        json={"status": "cancelled"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert await _stock(session, product.id) == Decimal("10.000")


async def test_repeated_cancel_does_not_restore_stock_twice(
    client, user_headers, admin_headers, make_product, session
) -> None:
    """Ключевое требование: повторная отмена не возвращает остаток второй раз."""
    product = await make_product(stock_kg="10.0")
    order = (
        await client.post(
            f"{PREFIX}/orders", json=order_payload(product.id, "2.0"), headers=user_headers
        )
    ).json()

    first = await client.patch(
        f"{PREFIX}/admin/orders/{order['id']}/status",
        json={"status": "cancelled"},
        headers=admin_headers,
    )
    assert first.status_code == 200
    assert await _stock(session, product.id) == Decimal("10.000")

    for _ in range(3):
        again = await client.patch(
            f"{PREFIX}/admin/orders/{order['id']}/status",
            json={"status": "cancelled"},
            headers=admin_headers,
        )
        assert again.status_code == 200
        assert again.json()["status"] == "cancelled"

    # Остаток ровно исходный, а не 12, 14 или 16.
    assert await _stock(session, product.id) == Decimal("10.000")


async def test_cancel_sets_stock_restored_marker(
    client, user_headers, admin_headers, make_product, session
) -> None:
    product = await make_product(stock_kg="5.0")
    order = (
        await client.post(
            f"{PREFIX}/orders", json=order_payload(product.id, "1.0"), headers=user_headers
        )
    ).json()

    await client.patch(
        f"{PREFIX}/admin/orders/{order['id']}/status",
        json={"status": "cancelled"},
        headers=admin_headers,
    )

    session.expire_all()
    stored = await session.scalar(select(Order).where(Order.id == order["id"]))
    assert stored.stock_restored_at is not None


async def test_cancel_after_progress_still_restores_once(
    client, user_headers, admin_headers, make_product, session
) -> None:
    product = await make_product(stock_kg="10.0")
    order = (
        await client.post(
            f"{PREFIX}/orders", json=order_payload(product.id, "3.0"), headers=user_headers
        )
    ).json()

    for status_value in ("confirmed", "preparing"):
        await client.patch(
            f"{PREFIX}/admin/orders/{order['id']}/status",
            json={"status": status_value},
            headers=admin_headers,
        )
    assert await _stock(session, product.id) == Decimal("7.000")

    await client.patch(
        f"{PREFIX}/admin/orders/{order['id']}/status",
        json={"status": "cancelled"},
        headers=admin_headers,
    )

    assert await _stock(session, product.id) == Decimal("10.000")


# ---------------------------------------------------------------------------
# Переходы статусов
# ---------------------------------------------------------------------------


async def test_status_update_is_idempotent(
    client, user_headers, admin_headers, make_product, session, notifications
) -> None:
    """Повторная установка того же статуса — no-op без уведомления."""
    product = await make_product(stock_kg="10.0")
    order = (
        await client.post(
            f"{PREFIX}/orders", json=order_payload(product.id, "1.0"), headers=user_headers
        )
    ).json()

    first = await client.patch(
        f"{PREFIX}/admin/orders/{order['id']}/status",
        json={"status": "confirmed"},
        headers=admin_headers,
    )
    assert first.status_code == 200
    notifications.status_changes.clear()

    second = await client.patch(
        f"{PREFIX}/admin/orders/{order['id']}/status",
        json={"status": "confirmed"},
        headers=admin_headers,
    )

    assert second.status_code == 200
    assert second.json()["status"] == "confirmed"
    assert await _status(session, order["id"]) == OrderStatus.CONFIRMED
    # Повторная установка не рассылает уведомление ещё раз.
    assert notifications.status_changes == []


async def test_status_change_notifies_customer(
    client, user_headers, admin_headers, make_product, notifications
) -> None:
    product = await make_product(stock_kg="10.0")
    order = (
        await client.post(
            f"{PREFIX}/orders", json=order_payload(product.id, "1.0"), headers=user_headers
        )
    ).json()

    await client.patch(
        f"{PREFIX}/admin/orders/{order['id']}/status",
        json={"status": "confirmed"},
        headers=admin_headers,
    )

    assert (order["id"], "confirmed") in notifications.status_changes


async def test_invalid_transition_is_rejected(
    client, user_headers, admin_headers, make_product
) -> None:
    """Из «Новый» нельзя сразу прыгнуть в «Выполнен»."""
    product = await make_product(stock_kg="10.0")
    order = (
        await client.post(
            f"{PREFIX}/orders", json=order_payload(product.id, "1.0"), headers=user_headers
        )
    ).json()

    response = await client.patch(
        f"{PREFIX}/admin/orders/{order['id']}/status",
        json={"status": "completed"},
        headers=admin_headers,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_status_transition"


async def test_completed_order_cannot_be_cancelled(
    client, user_headers, admin_headers, make_product, session
) -> None:
    product = await make_product(stock_kg="10.0")
    order = (
        await client.post(
            f"{PREFIX}/orders", json=order_payload(product.id, "2.0"), headers=user_headers
        )
    ).json()

    for status_value in ("confirmed", "preparing", "delivering", "completed"):
        assert (
            await client.patch(
                f"{PREFIX}/admin/orders/{order['id']}/status",
                json={"status": status_value},
                headers=admin_headers,
            )
        ).status_code == 200

    response = await client.patch(
        f"{PREFIX}/admin/orders/{order['id']}/status",
        json={"status": "cancelled"},
        headers=admin_headers,
    )

    assert response.status_code == 409
    # Выполненный заказ не возвращает остаток.
    assert await _stock(session, product.id) == Decimal("8.000")


async def test_unknown_status_is_rejected(
    client, user_headers, admin_headers, make_product
) -> None:
    product = await make_product(stock_kg="10.0")
    order = (
        await client.post(
            f"{PREFIX}/orders", json=order_payload(product.id, "1.0"), headers=user_headers
        )
    ).json()

    response = await client.patch(
        f"{PREFIX}/admin/orders/{order['id']}/status",
        json={"status": "teleported"},
        headers=admin_headers,
    )

    assert response.status_code == 422


async def test_regular_user_cannot_change_status(
    client, user_headers, make_product
) -> None:
    product = await make_product(stock_kg="10.0")
    order = (
        await client.post(
            f"{PREFIX}/orders", json=order_payload(product.id, "1.0"), headers=user_headers
        )
    ).json()

    response = await client.patch(
        f"{PREFIX}/admin/orders/{order['id']}/status",
        json={"status": "confirmed"},
        headers=user_headers,
    )

    assert response.status_code == 403
