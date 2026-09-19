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
    # Отдельного «нового» статуса нет: оформленный заказ сразу подтверждён.
    assert body["status"] == "confirmed"
    assert body["status_label"] == "Подтверждён"
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


# ---------------------------------------------------------------------------
# Структурированный адрес
# ---------------------------------------------------------------------------


async def test_structured_address_is_saved_and_read_back(
    client, user_headers, make_product
) -> None:
    """Части адреса из сервиса подсказок сохраняются рядом с плоской строкой."""
    product = await make_product(stock_kg="10.0")
    payload = order_payload(
        product.id,
        "1.0",
        address_city="Москва",
        address_street="улица Ленина",
        address_house="1к2",
        address_postal_code="101000",
        address_lat="55.755814",
        address_lon="37.617635",
    )

    created = (await client.post(f"{PREFIX}/orders", json=payload, headers=user_headers)).json()
    body = (await client.get(f"{PREFIX}/orders/{created['id']}", headers=user_headers)).json()

    assert body["address_city"] == "Москва"
    assert body["address_street"] == "улица Ленина"
    assert body["address_house"] == "1к2"
    assert body["address_postal_code"] == "101000"
    # Плоский адрес остаётся тем, что покупатель видит и правит руками.
    assert body["address"] == payload["address"]


async def test_coordinates_are_serialized_as_strings(client, user_headers, make_product) -> None:
    """Координаты уезжают в JSON строками — как деньги и вес, без float."""
    product = await make_product(stock_kg="10.0")
    payload = order_payload(product.id, "1.0", address_lat="55.755814", address_lon="37.617635")

    body = (await client.post(f"{PREFIX}/orders", json=payload, headers=user_headers)).json()

    assert body["address_lat"] == "55.755814"
    assert body["address_lon"] == "37.617635"
    assert isinstance(body["address_lat"], str)
    assert isinstance(body["address_lon"], str)
    assert Decimal(body["address_lat"]) == Decimal("55.755814")


async def test_coordinates_accept_numbers_and_keep_six_places(
    client, user_headers, make_product
) -> None:
    """Число на входе допустимо, но наружу всё равно уходит строка с шестью знаками."""
    product = await make_product(stock_kg="10.0")
    payload = order_payload(product.id, "1.0", address_lat=55.75, address_lon=-0.1)

    body = (await client.post(f"{PREFIX}/orders", json=payload, headers=user_headers)).json()

    assert body["address_lat"] == "55.750000"
    assert body["address_lon"] == "-0.100000"


async def test_order_without_structured_address_still_works(
    client, user_headers, make_product
) -> None:
    """Обратная совместимость: подсказка могла не сработать — заказ всё равно создаётся."""
    product = await make_product(stock_kg="10.0")

    response = await client.post(
        f"{PREFIX}/orders", json=order_payload(product.id, "1.0"), headers=user_headers
    )

    assert response.status_code == 201
    body = response.json()
    assert body["address_city"] is None
    assert body["address_lat"] is None
    assert body["address_lon"] is None


async def test_partial_structured_address_is_accepted(client, user_headers, make_product) -> None:
    """Подсказка может не знать индекс — это не повод отклонять заказ."""
    product = await make_product(stock_kg="10.0")
    payload = order_payload(product.id, "1.0", address_city="Москва", address_street="Тверская")

    response = await client.post(f"{PREFIX}/orders", json=payload, headers=user_headers)

    assert response.status_code == 201
    body = response.json()
    assert body["address_city"] == "Москва"
    assert body["address_postal_code"] is None


async def test_blank_address_parts_become_null(client, user_headers, make_product) -> None:
    """Пустая строка от формы — это «не заполнено», а не значение."""
    product = await make_product(stock_kg="10.0")
    payload = order_payload(product.id, "1.0", address_city="", address_postal_code="")

    body = (await client.post(f"{PREFIX}/orders", json=payload, headers=user_headers)).json()

    assert body["address_city"] is None
    assert body["address_postal_code"] is None


async def test_zero_coordinates_are_preserved(client, user_headers, make_product) -> None:
    """Ноль — валидная координата и не должен схлопываться в null."""
    product = await make_product(stock_kg="10.0")
    payload = order_payload(product.id, "1.0", address_lat="0", address_lon="0")

    body = (await client.post(f"{PREFIX}/orders", json=payload, headers=user_headers)).json()

    assert body["address_lat"] == "0.000000"
    assert body["address_lon"] == "0.000000"


async def test_latitude_out_of_range_is_rejected(client, user_headers, make_product) -> None:
    """Широта вне -90..90 — это 422, а не 500 из недр БД."""
    product = await make_product(stock_kg="10.0")

    response = await client.post(
        f"{PREFIX}/orders",
        json=order_payload(product.id, "1.0", address_lat="91.0"),
        headers=user_headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_longitude_out_of_range_is_rejected(client, user_headers, make_product) -> None:
    """Долгота вне -180..180 — тоже 422."""
    product = await make_product(stock_kg="10.0")

    response = await client.post(
        f"{PREFIX}/orders",
        json=order_payload(product.id, "1.0", address_lon="-180.5"),
        headers=user_headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_non_numeric_coordinate_is_rejected(client, user_headers, make_product) -> None:
    """Мусор в координате не должен долетать до БД."""
    product = await make_product(stock_kg="10.0")

    for value in ("север", "NaN", "1e1000"):
        response = await client.post(
            f"{PREFIX}/orders",
            json=order_payload(product.id, "1.0", address_lat=value),
            headers=user_headers,
        )
        assert response.status_code == 422, value


async def test_delivery_time_is_no_longer_accepted(client, user_headers, make_product) -> None:
    """Интервал доставки убран из проекта: `extra="forbid"` не пускает его обратно."""
    product = await make_product(stock_kg="10.0")

    response = await client.post(
        f"{PREFIX}/orders",
        json=order_payload(product.id, "1.0", delivery_time="12:00-15:00"),
        headers=user_headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_order_response_has_no_delivery_time_field(
    client, user_headers, make_product
) -> None:
    """Поля нет и в ответе — фронту нечего оттуда читать."""
    product = await make_product(stock_kg="10.0")

    body = (
        await client.post(
            f"{PREFIX}/orders", json=order_payload(product.id, "1.0"), headers=user_headers
        )
    ).json()

    assert "delivery_time" not in body


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
