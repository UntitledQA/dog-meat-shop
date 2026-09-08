"""Создание заказа: расчёт сумм, доставка/самовывоз, доступ к чужим заказам."""

from __future__ import annotations

from decimal import Decimal

from tests.conftest import order_payload

PREFIX = "/api/v1"


async def test_create_order_returns_201_and_snapshot(client, user_headers, make_product) -> None:
    product = await make_product(name="Говядина", price_per_kg="890.00", stock_kg="10.0")

    response = await client.post(
        f"{PREFIX}/orders", json=order_payload(product.id, "2.0"), headers=user_headers
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "new"
    assert body["status_label"] == "Новый"
    assert body["payment_method"] == "cash_on_delivery"
    assert body["order_number"].startswith("ORD-")
    assert len(body["items"]) == 1

    item = body["items"][0]
    # Снимок товара на момент оформления.
    assert item["product_name"] == "Говядина"
    assert item["price_per_kg"] == "890.00"
    assert item["weight_kg"] == "2.000"
    assert item["line_total"] == "1780.00"


async def test_totals_are_calculated_on_backend(client, user_headers, make_product) -> None:
    """2 кг * 890 = 1780, плюс доставка 300 -> 2080."""
    product = await make_product(price_per_kg="890.00", stock_kg="10.0")

    body = (
        await client.post(
            f"{PREFIX}/orders", json=order_payload(product.id, "2.0"), headers=user_headers
        )
    ).json()

    assert body["subtotal"] == "1780.00"
    assert body["delivery_price"] == "300.00"
    assert body["total"] == "2080.00"


async def test_pickup_has_no_delivery_price(client, user_headers, make_product) -> None:
    product = await make_product(price_per_kg="500.00", stock_kg="10.0")

    body = (
        await client.post(
            f"{PREFIX}/orders",
            json=order_payload(product.id, "1.0", delivery_type="pickup"),
            headers=user_headers,
        )
    ).json()

    assert body["delivery_type"] == "pickup"
    assert body["subtotal"] == "500.00"
    assert body["delivery_price"] == "0.00"
    assert body["total"] == "500.00"


async def test_multiple_items_sum_correctly(client, user_headers, make_product) -> None:
    beef = await make_product(name="Говядина", price_per_kg="890.00", stock_kg="10.0")
    turkey = await make_product(name="Индейка", price_per_kg="450.50", stock_kg="10.0")

    payload = order_payload(beef.id, "1.5")
    payload["items"] = [
        {"product_id": beef.id, "weight_kg": "1.5"},
        {"product_id": turkey.id, "weight_kg": "0.7"},
    ]

    body = (await client.post(f"{PREFIX}/orders", json=payload, headers=user_headers)).json()

    # 1.5 * 890.00 = 1335.00 ; 0.7 * 450.50 = 315.35 ; сумма 1650.35 + 300 = 1950.35
    line_totals = {item["product_name"]: item["line_total"] for item in body["items"]}
    assert line_totals["Говядина"] == "1335.00"
    assert line_totals["Индейка"] == "315.35"
    assert body["subtotal"] == "1650.35"
    assert body["total"] == "1950.35"


async def test_price_is_taken_from_database_not_from_request(
    client, user_headers, make_product
) -> None:
    """Корзина фронта не источник истины: цена из тела запроса игнорируется."""
    product = await make_product(price_per_kg="890.00", stock_kg="10.0")

    payload = order_payload(product.id, "1.0")
    # Пытаемся подсунуть свою цену и сумму.
    payload["items"] = [{"product_id": product.id, "weight_kg": "1.0", "price_per_kg": "1.00"}]

    response = await client.post(f"{PREFIX}/orders", json=payload, headers=user_headers)

    # Лишние поля запрещены схемой — подмена цены невозможна в принципе.
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_totals_ignore_client_supplied_totals(client, user_headers, make_product) -> None:
    product = await make_product(price_per_kg="890.00", stock_kg="10.0")
    payload = order_payload(product.id, "1.0")
    payload["total"] = "1.00"

    response = await client.post(f"{PREFIX}/orders", json=payload, headers=user_headers)

    assert response.status_code == 422


async def test_order_number_is_unique_and_readable(client, user_headers, make_product) -> None:
    product = await make_product(stock_kg="10.0")

    first = (
        await client.post(
            f"{PREFIX}/orders", json=order_payload(product.id, "1.0"), headers=user_headers
        )
    ).json()
    second = (
        await client.post(
            f"{PREFIX}/orders", json=order_payload(product.id, "1.0"), headers=user_headers
        )
    ).json()

    assert first["order_number"] != second["order_number"]
    for number in (first["order_number"], second["order_number"]):
        prefix, date_part, seq = number.split("-")
        assert prefix == "ORD"
        assert len(date_part) == 8 and date_part.isdigit()
        assert len(seq) == 5 and seq.isdigit()


async def test_empty_cart_is_rejected(client, user_headers) -> None:
    payload = order_payload(1)
    payload["items"] = []

    response = await client.post(f"{PREFIX}/orders", json=payload, headers=user_headers)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_unknown_product_is_rejected(client, user_headers) -> None:
    response = await client.post(
        f"{PREFIX}/orders", json=order_payload(999999, "1.0"), headers=user_headers
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_hidden_product_cannot_be_ordered(client, user_headers, make_product) -> None:
    product = await make_product(is_active=False, stock_kg="10.0")

    response = await client.post(
        f"{PREFIX}/orders", json=order_payload(product.id, "1.0"), headers=user_headers
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "product_unavailable"


async def test_delivery_requires_address(client, user_headers, make_product) -> None:
    product = await make_product(stock_kg="10.0")
    payload = order_payload(product.id, "1.0")
    payload.pop("address")

    response = await client.post(f"{PREFIX}/orders", json=payload, headers=user_headers)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_pickup_does_not_require_address(client, user_headers, make_product) -> None:
    product = await make_product(stock_kg="10.0")

    response = await client.post(
        f"{PREFIX}/orders",
        json=order_payload(product.id, "1.0", delivery_type="pickup"),
        headers=user_headers,
    )

    assert response.status_code == 201


async def test_weight_below_minimum_is_rejected(client, user_headers, make_product) -> None:
    product = await make_product(stock_kg="10.0")

    response = await client.post(
        f"{PREFIX}/orders", json=order_payload(product.id, "0.05"), headers=user_headers
    )

    assert response.status_code == 422


async def test_weight_off_step_is_rejected(client, user_headers, make_product) -> None:
    """Шаг веса — 0.1 кг."""
    product = await make_product(stock_kg="10.0")

    response = await client.post(
        f"{PREFIX}/orders", json=order_payload(product.id, "1.25"), headers=user_headers
    )

    assert response.status_code == 422


async def test_duplicate_product_in_cart_is_rejected(client, user_headers, make_product) -> None:
    product = await make_product(stock_kg="10.0")
    payload = order_payload(product.id, "1.0")
    payload["items"] = [
        {"product_id": product.id, "weight_kg": "1.0"},
        {"product_id": product.id, "weight_kg": "2.0"},
    ]

    response = await client.post(f"{PREFIX}/orders", json=payload, headers=user_headers)

    assert response.status_code == 422


async def test_invalid_phone_is_rejected(client, user_headers, make_product) -> None:
    product = await make_product(stock_kg="10.0")

    response = await client.post(
        f"{PREFIX}/orders",
        json=order_payload(product.id, "1.0", phone="123"),
        headers=user_headers,
    )

    assert response.status_code == 422


async def test_order_creation_notifies_telegram(
    client, user_headers, make_product, notifications
) -> None:
    """Связка order_service -> notification_service должна реально вызываться."""
    product = await make_product(stock_kg="10.0")

    body = (
        await client.post(
            f"{PREFIX}/orders", json=order_payload(product.id, "1.0"), headers=user_headers
        )
    ).json()

    assert notifications.new_orders == [body["id"]]


# ---------------------------------------------------------------------------
# Чтение заказов
# ---------------------------------------------------------------------------


async def test_user_sees_only_own_orders(
    client, user_headers, other_user_headers, make_product
) -> None:
    product = await make_product(stock_kg="10.0")
    await client.post(
        f"{PREFIX}/orders", json=order_payload(product.id, "1.0"), headers=user_headers
    )

    mine = (await client.get(f"{PREFIX}/orders", headers=user_headers)).json()
    theirs = (await client.get(f"{PREFIX}/orders", headers=other_user_headers)).json()

    assert mine["total"] == 1
    assert theirs["total"] == 0


async def test_foreign_order_returns_403(
    client, user_headers, other_user_headers, make_product
) -> None:
    """Подмена id в URL не даёт прочитать чужой заказ."""
    product = await make_product(stock_kg="10.0")
    created = (
        await client.post(
            f"{PREFIX}/orders", json=order_payload(product.id, "1.0"), headers=user_headers
        )
    ).json()

    response = await client.get(f"{PREFIX}/orders/{created['id']}", headers=other_user_headers)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_own_order_is_readable(client, user_headers, make_product) -> None:
    product = await make_product(stock_kg="10.0")
    created = (
        await client.post(
            f"{PREFIX}/orders", json=order_payload(product.id, "1.0"), headers=user_headers
        )
    ).json()

    response = await client.get(f"{PREFIX}/orders/{created['id']}", headers=user_headers)

    assert response.status_code == 200
    assert response.json()["order_number"] == created["order_number"]


async def test_missing_order_returns_404(client, user_headers) -> None:
    response = await client.get(f"{PREFIX}/orders/999999", headers=user_headers)

    assert response.status_code == 404


async def test_orders_require_authorization(client) -> None:
    assert (await client.get(f"{PREFIX}/orders")).status_code == 401
    assert (await client.post(f"{PREFIX}/orders", json={})).status_code == 401


async def test_order_snapshot_survives_catalog_change(
    client, user_headers, admin_headers, make_product, session
) -> None:
    """Изменение каталога не меняет уже оформленный заказ."""
    product = await make_product(name="Говядина", price_per_kg="890.00", stock_kg="10.0")
    created = (
        await client.post(
            f"{PREFIX}/orders", json=order_payload(product.id, "1.0"), headers=user_headers
        )
    ).json()

    await client.patch(
        f"{PREFIX}/admin/products/{product.id}",
        json={"name": "Говядина премиум", "price_per_kg": "1500.00"},
        headers=admin_headers,
    )

    body = (await client.get(f"{PREFIX}/orders/{created['id']}", headers=user_headers)).json()

    assert body["items"][0]["product_name"] == "Говядина"
    assert body["items"][0]["price_per_kg"] == "890.00"
    assert Decimal(body["total"]) == Decimal("1190.00")
