"""Каталог: видимость товаров, отметка «нет в наличии», формат чисел."""

from __future__ import annotations

PREFIX = "/api/v1"


async def test_catalog_shows_only_active_products(client, user_headers, make_product) -> None:
    visible = await make_product(name="Говядина")
    hidden = await make_product(name="Скрытый деликатес", is_active=False)

    response = await client.get(f"{PREFIX}/catalog", headers=user_headers)

    assert response.status_code == 200
    body = response.json()
    names = [item["name"] for item in body["items"]]
    assert visible.name in names
    assert hidden.name not in names
    assert body["total"] == 1


async def test_catalog_page_shape(client, user_headers, make_product) -> None:
    await make_product()

    response = await client.get(f"{PREFIX}/catalog", headers=user_headers)

    body = response.json()
    assert set(body) >= {"items", "total", "limit", "offset"}
    assert body["offset"] == 0
    assert body["limit"] >= 1


async def test_catalog_returns_decimals_as_strings(client, user_headers, make_product) -> None:
    """Деньги и вес уходят строками — иначе JS теряет точность."""
    await make_product(price_per_kg="890.00", stock_kg="12.5")

    item = (await client.get(f"{PREFIX}/catalog", headers=user_headers)).json()["items"][0]

    assert item["price_per_kg"] == "890.00"
    assert item["stock_kg"] == "12.500"
    assert isinstance(item["price_per_kg"], str)
    assert isinstance(item["stock_kg"], str)


async def test_out_of_stock_product_is_visible_but_marked(
    client, user_headers, make_product
) -> None:
    """Товар без остатка показывается, но помечен как отсутствующий."""
    await make_product(name="Индейка", stock_kg="0")

    item = (await client.get(f"{PREFIX}/catalog", headers=user_headers)).json()["items"][0]

    assert item["name"] == "Индейка"
    assert item["stock_kg"] == "0.000"
    assert item["in_stock"] is False


async def test_in_stock_flag_is_true_when_stock_left(client, user_headers, make_product) -> None:
    await make_product(stock_kg="0.1")

    item = (await client.get(f"{PREFIX}/catalog", headers=user_headers)).json()["items"][0]

    assert item["in_stock"] is True


async def test_empty_catalog_returns_empty_page(client, user_headers) -> None:
    response = await client.get(f"{PREFIX}/catalog", headers=user_headers)

    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "limit": 20, "offset": 0}


async def test_catalog_pagination(client, user_headers, make_product) -> None:
    for index in range(5):
        await make_product(name=f"Товар {index}")

    response = await client.get(f"{PREFIX}/catalog?limit=2&offset=2", headers=user_headers)

    body = response.json()
    assert len(body["items"]) == 2
    assert body["total"] == 5
    assert body["limit"] == 2
    assert body["offset"] == 2


# ---------------------------------------------------------------------------
# Фильтр по категории
# ---------------------------------------------------------------------------


async def test_catalog_filters_by_category(client, user_headers, make_product) -> None:
    """`?category=<slug>` оставляет только товары этой категории."""
    await make_product(name="Говядина", category="beef")
    await make_product(name="Утка", category="duck")
    await make_product(name="Без категории")  # по умолчанию category=None

    body = (await client.get(f"{PREFIX}/catalog?category=beef", headers=user_headers)).json()

    assert [item["name"] for item in body["items"]] == ["Говядина"]
    assert body["total"] == 1
    assert body["items"][0]["category"] == "beef"


async def test_catalog_filter_matches_hyphenated_slug(
    client, user_headers, make_product
) -> None:
    """Slug с дефисом (`horse-meat`) как query-параметр тоже валиден."""
    await make_product(name="Конина", category="horse-meat")
    await make_product(name="Рыба", category="fish")

    body = (
        await client.get(f"{PREFIX}/catalog?category=horse-meat", headers=user_headers)
    ).json()

    assert [item["name"] for item in body["items"]] == ["Конина"]
    assert body["total"] == 1


async def test_catalog_without_category_returns_all_active(
    client, user_headers, make_product
) -> None:
    """Без параметра — все активные товары, включая товары без категории."""
    await make_product(name="С категорией", category="beef")
    await make_product(name="Без категории")

    body = (await client.get(f"{PREFIX}/catalog", headers=user_headers)).json()

    assert {item["name"] for item in body["items"]} == {"С категорией", "Без категории"}
    assert body["total"] == 2


async def test_catalog_invalid_category_returns_422(
    client, user_headers, make_product
) -> None:
    """Неизвестный slug в query — единый 422, а не пустой список."""
    await make_product(name="Говядина", category="beef")

    response = await client.get(f"{PREFIX}/catalog?category=chicken", headers=user_headers)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_single_product_available(client, user_headers, make_product) -> None:
    product = await make_product(name="Куриные шеи", description="Хрустящие")

    response = await client.get(f"{PREFIX}/catalog/{product.id}", headers=user_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == product.id
    assert body["name"] == "Куриные шеи"
    assert body["description"] == "Хрустящие"


async def test_hidden_product_is_not_reachable_by_id(client, user_headers, make_product) -> None:
    hidden = await make_product(is_active=False)

    response = await client.get(f"{PREFIX}/catalog/{hidden.id}", headers=user_headers)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_missing_product_returns_unified_error(client, user_headers) -> None:
    response = await client.get(f"{PREFIX}/catalog/999999", headers=user_headers)

    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "not_found"
    assert error["message"]
    assert "details" in error


async def test_catalog_requires_authorization(client) -> None:
    response = await client.get(f"{PREFIX}/catalog")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_settings_endpoint_exposes_delivery_price(client, user_headers) -> None:
    response = await client.get(f"{PREFIX}/settings", headers=user_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["delivery_price"] == "300.00"
    assert body["min_weight_kg"] == "0.100"
    assert body["weight_step_kg"] == "0.100"
    assert body["currency"] == "RUB"
    assert body["payment_note"]
