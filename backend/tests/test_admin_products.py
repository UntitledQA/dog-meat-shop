"""Административное управление каталогом: создание, валидация, скрытие, фото."""

from __future__ import annotations

import io
import struct

import pytest

PREFIX = "/api/v1"


def _png_bytes() -> bytes:
    """Минимальный корректный PNG (сигнатура + IHDR)."""
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    ihdr = struct.pack(">I", len(ihdr_data)) + b"IHDR" + ihdr_data + b"\x00\x00\x00\x00"
    return signature + ihdr + b"\x00" * 32


def _jpeg_bytes() -> bytes:
    return b"\xff\xd8\xff\xe0" + b"\x00" * 64


# ---------------------------------------------------------------------------
# Создание
# ---------------------------------------------------------------------------


async def test_admin_creates_product(client, admin_headers) -> None:
    response = await client.post(
        f"{PREFIX}/admin/products",
        json={
            "name": "Рубец говяжий",
            "description": "Очищенный, для взрослых собак",
            "price_per_kg": "320.00",
            "stock_kg": "8.5",
        },
        headers=admin_headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Рубец говяжий"
    assert body["price_per_kg"] == "320.00"
    assert body["stock_kg"] == "8.500"
    assert body["is_active"] is True
    assert body["in_stock"] is True


async def test_created_product_appears_in_catalog(client, admin_headers, user_headers) -> None:
    await client.post(
        f"{PREFIX}/admin/products",
        json={"name": "Сердце говяжье", "price_per_kg": "410.00", "stock_kg": "4"},
        headers=admin_headers,
    )

    catalog = (await client.get(f"{PREFIX}/catalog", headers=user_headers)).json()

    assert [item["name"] for item in catalog["items"]] == ["Сердце говяжье"]


async def test_price_accepts_number_and_string(client, admin_headers) -> None:
    from_string = await client.post(
        f"{PREFIX}/admin/products",
        json={"name": "Товар А", "price_per_kg": "100.50", "stock_kg": "1"},
        headers=admin_headers,
    )
    from_number = await client.post(
        f"{PREFIX}/admin/products",
        json={"name": "Товар Б", "price_per_kg": 100.5, "stock_kg": 1},
        headers=admin_headers,
    )

    assert from_string.json()["price_per_kg"] == "100.50"
    assert from_number.json()["price_per_kg"] == "100.50"


# ---------------------------------------------------------------------------
# Валидация
# ---------------------------------------------------------------------------


async def test_negative_price_is_rejected(client, admin_headers) -> None:
    response = await client.post(
        f"{PREFIX}/admin/products",
        json={"name": "Плохой товар", "price_per_kg": "-1.00", "stock_kg": "1"},
        headers=admin_headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_negative_stock_is_rejected(client, admin_headers) -> None:
    response = await client.post(
        f"{PREFIX}/admin/products",
        json={"name": "Плохой товар", "price_per_kg": "100.00", "stock_kg": "-5"},
        headers=admin_headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_empty_name_is_rejected(client, admin_headers) -> None:
    response = await client.post(
        f"{PREFIX}/admin/products",
        json={"name": "   ", "price_per_kg": "100.00", "stock_kg": "1"},
        headers=admin_headers,
    )

    assert response.status_code == 422


async def test_missing_name_is_rejected(client, admin_headers) -> None:
    response = await client.post(
        f"{PREFIX}/admin/products",
        json={"price_per_kg": "100.00", "stock_kg": "1"},
        headers=admin_headers,
    )

    assert response.status_code == 422
    fields = response.json()["error"]["details"]["fields"]
    assert any("name" in field["field"] for field in fields)


async def test_negative_price_on_update_is_rejected(client, admin_headers, make_product) -> None:
    product = await make_product()

    response = await client.patch(
        f"{PREFIX}/admin/products/{product.id}",
        json={"price_per_kg": "-10"},
        headers=admin_headers,
    )

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Редактирование
# ---------------------------------------------------------------------------


async def test_admin_updates_price_and_stock(client, admin_headers, make_product) -> None:
    product = await make_product(price_per_kg="500.00", stock_kg="1.0")

    response = await client.patch(
        f"{PREFIX}/admin/products/{product.id}",
        json={"price_per_kg": "650.00", "stock_kg": "12.3"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["price_per_kg"] == "650.00"
    assert body["stock_kg"] == "12.300"


async def test_partial_update_keeps_other_fields(client, admin_headers, make_product) -> None:
    product = await make_product(name="Индейка", price_per_kg="450.00", stock_kg="3.0")

    body = (
        await client.patch(
            f"{PREFIX}/admin/products/{product.id}",
            json={"stock_kg": "7"},
            headers=admin_headers,
        )
    ).json()

    assert body["name"] == "Индейка"
    assert body["price_per_kg"] == "450.00"
    assert body["stock_kg"] == "7.000"


# ---------------------------------------------------------------------------
# Категории
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("category", ["beef", "veal", "horse-meat", "dried-treats"])
async def test_admin_creates_product_with_category(
    client, admin_headers, category: str
) -> None:
    """Категория сохраняется и возвращается slug'ом — в т.ч. с дефисом."""
    response = await client.post(
        f"{PREFIX}/admin/products",
        json={
            "name": "Товар с категорией",
            "price_per_kg": "100.00",
            "stock_kg": "1",
            "category": category,
        },
        headers=admin_headers,
    )

    assert response.status_code == 201
    assert response.json()["category"] == category


async def test_admin_creates_product_without_category(client, admin_headers) -> None:
    """Поле не передано — товар остаётся без категории (null)."""
    response = await client.post(
        f"{PREFIX}/admin/products",
        json={"name": "Без категории", "price_per_kg": "100.00", "stock_kg": "1"},
        headers=admin_headers,
    )

    assert response.status_code == 201
    assert response.json()["category"] is None


async def test_admin_updates_category(client, admin_headers, make_product) -> None:
    product = await make_product(category="beef")

    response = await client.patch(
        f"{PREFIX}/admin/products/{product.id}",
        json={"category": "duck"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json()["category"] == "duck"


async def test_admin_clears_category_with_null(client, admin_headers, make_product) -> None:
    """Явный null очищает категорию — она обнуляемая (в отличие от name/price)."""
    product = await make_product(category="fish")

    response = await client.patch(
        f"{PREFIX}/admin/products/{product.id}",
        json={"category": None},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json()["category"] is None


async def test_invalid_category_on_create_is_rejected(client, admin_headers) -> None:
    """Неизвестный slug — единый 422, а не 500."""
    response = await client.post(
        f"{PREFIX}/admin/products",
        json={
            "name": "Товар",
            "price_per_kg": "100.00",
            "stock_kg": "1",
            "category": "chicken",
        },
        headers=admin_headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


# ---------------------------------------------------------------------------
# Скрытие и восстановление
# ---------------------------------------------------------------------------


async def test_archive_hides_product_from_catalog(
    client, admin_headers, user_headers, make_product
) -> None:
    product = await make_product()

    response = await client.post(
        f"{PREFIX}/admin/products/{product.id}/archive", headers=admin_headers
    )

    assert response.status_code == 200
    assert response.json()["is_active"] is False
    catalog = (await client.get(f"{PREFIX}/catalog", headers=user_headers)).json()
    assert catalog["total"] == 0


async def test_restore_returns_product_to_catalog(
    client, admin_headers, user_headers, make_product
) -> None:
    product = await make_product(is_active=False)

    response = await client.post(
        f"{PREFIX}/admin/products/{product.id}/restore", headers=admin_headers
    )

    assert response.status_code == 200
    assert response.json()["is_active"] is True
    catalog = (await client.get(f"{PREFIX}/catalog", headers=user_headers)).json()
    assert catalog["total"] == 1


async def test_archive_is_idempotent(client, admin_headers, make_product) -> None:
    product = await make_product()

    first = await client.post(
        f"{PREFIX}/admin/products/{product.id}/archive", headers=admin_headers
    )
    second = await client.post(
        f"{PREFIX}/admin/products/{product.id}/archive", headers=admin_headers
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["is_active"] is False


async def test_admin_list_includes_hidden_products(client, admin_headers, make_product) -> None:
    await make_product(name="Активный")
    await make_product(name="Скрытый", is_active=False)

    response = await client.get(
        f"{PREFIX}/admin/products?include_inactive=true", headers=admin_headers
    )

    assert response.status_code == 200
    names = {item["name"] for item in response.json()["items"]}
    assert names == {"Активный", "Скрытый"}


async def test_admin_list_supports_pagination(client, admin_headers, make_product) -> None:
    for index in range(5):
        await make_product(name=f"Товар {index}")

    body = (
        await client.get(
            f"{PREFIX}/admin/products?limit=2&offset=1&include_inactive=true",
            headers=admin_headers,
        )
    ).json()

    assert len(body["items"]) == 2
    assert body["total"] == 5
    assert body["limit"] == 2
    assert body["offset"] == 1


# ---------------------------------------------------------------------------
# Загрузка фотографий
# ---------------------------------------------------------------------------


async def test_admin_uploads_png_photo(client, admin_headers, make_product) -> None:
    product = await make_product()

    response = await client.post(
        f"{PREFIX}/admin/products/{product.id}/photo",
        files={"file": ("photo.png", io.BytesIO(_png_bytes()), "image/png")},
        headers=admin_headers,
    )

    assert response.status_code == 200
    photo_url = response.json()["photo_url"]
    assert photo_url.startswith("/uploads/")
    assert photo_url.endswith(".png")


async def test_admin_uploads_jpeg_photo(client, admin_headers) -> None:
    response = await client.post(
        f"{PREFIX}/admin/uploads/photo",
        files={"file": ("photo.jpg", io.BytesIO(_jpeg_bytes()), "image/jpeg")},
        headers=admin_headers,
    )

    assert response.status_code == 201
    assert response.json()["photo_url"].startswith("/uploads/")


async def test_fake_image_is_rejected_by_signature(client, admin_headers) -> None:
    """Расширение и Content-Type подделать легко — проверяются реальные байты."""
    response = await client.post(
        f"{PREFIX}/admin/uploads/photo",
        files={"file": ("evil.png", io.BytesIO(b"<?php echo 1; ?>"), "image/png")},
        headers=admin_headers,
    )

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_media_type"


async def test_upload_requires_admin(client, user_headers) -> None:
    response = await client.post(
        f"{PREFIX}/admin/uploads/photo",
        files={"file": ("photo.png", io.BytesIO(_png_bytes()), "image/png")},
        headers=user_headers,
    )

    assert response.status_code == 403


async def test_photo_replacement_updates_url(client, admin_headers, make_product) -> None:
    product = await make_product()

    first = await client.post(
        f"{PREFIX}/admin/products/{product.id}/photo",
        files={"file": ("a.png", io.BytesIO(_png_bytes()), "image/png")},
        headers=admin_headers,
    )
    second = await client.post(
        f"{PREFIX}/admin/products/{product.id}/photo",
        files={"file": ("b.jpg", io.BytesIO(_jpeg_bytes()), "image/jpeg")},
        headers=admin_headers,
    )

    assert first.json()["photo_url"] != second.json()["photo_url"]
    assert second.json()["photo_url"].endswith(".jpg")


# ---------------------------------------------------------------------------
# Права
# ---------------------------------------------------------------------------


async def test_regular_user_cannot_create_product(client, user_headers) -> None:
    response = await client.post(
        f"{PREFIX}/admin/products",
        json={"name": "Товар", "price_per_kg": "100.00", "stock_kg": "1"},
        headers=user_headers,
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_anonymous_cannot_create_product(client) -> None:
    response = await client.post(
        f"{PREFIX}/admin/products",
        json={"name": "Товар", "price_per_kg": "100.00", "stock_kg": "1"},
    )

    assert response.status_code == 401


async def test_update_missing_product_returns_404(client, admin_headers) -> None:
    response = await client.patch(
        f"{PREFIX}/admin/products/999999", json={"stock_kg": "1"}, headers=admin_headers
    )

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Устойчивость к «плохому» вводу: 422, а не 500
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("field", ["name", "price_per_kg", "stock_kg", "is_active"])
async def test_explicit_null_on_required_field_returns_422(
    client, admin_headers, make_product, field: str
) -> None:
    """Регрессия: явный null доходил до UPDATE и падал как IntegrityError (500)."""
    product = await make_product()

    response = await client.patch(
        f"{PREFIX}/admin/products/{product.id}",
        json={field: None},
        headers=admin_headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


@pytest.mark.parametrize("field", ["description", "photo_url"])
async def test_explicit_null_clears_optional_field(
    client, admin_headers, make_product, field: str
) -> None:
    """Обнуляемые поля по-прежнему можно очистить явным null."""
    product = await make_product(description="Было описание", photo_url="/uploads/a.jpg")

    response = await client.patch(
        f"{PREFIX}/admin/products/{product.id}",
        json={field: None},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json()[field] is None


@pytest.mark.parametrize("value", ["1e1000", "NaN", "Infinity", "-Infinity", "1e400"])
async def test_non_finite_price_returns_422(client, admin_headers, value: str) -> None:
    """Регрессия: decimal.InvalidOperation — ArithmeticError, Pydantic его не ловил."""
    response = await client.post(
        f"{PREFIX}/admin/products",
        json={"name": "Товар", "price_per_kg": value, "stock_kg": "1"},
        headers=admin_headers,
    )

    assert response.status_code == 422, f"{value} дал {response.status_code}"


async def test_price_beyond_column_range_returns_422(client, admin_headers) -> None:
    """Numeric(10,2) не вмещает 12 цифр — отсекаем до похода в БД."""
    response = await client.post(
        f"{PREFIX}/admin/products",
        json={"name": "Товар", "price_per_kg": "999999999999", "stock_kg": "1"},
        headers=admin_headers,
    )

    assert response.status_code == 422


async def test_stock_beyond_column_range_returns_422(client, admin_headers) -> None:
    response = await client.post(
        f"{PREFIX}/admin/products",
        json={"name": "Товар", "price_per_kg": "100", "stock_kg": "99999999999"},
        headers=admin_headers,
    )

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Файлы на диске: §8 контракта
# ---------------------------------------------------------------------------


def _disk_path(photo_url: str):
    from app.core.config import settings

    return settings.upload_path / photo_url.rsplit("/", 1)[-1]


async def test_uploaded_file_really_lands_on_disk(client, admin_headers) -> None:
    response = await client.post(
        f"{PREFIX}/admin/uploads/photo",
        files={"file": ("photo.png", io.BytesIO(_png_bytes()), "image/png")},
        headers=admin_headers,
    )

    assert _disk_path(response.json()["photo_url"]).exists()


async def test_replacing_photo_deletes_the_old_file(
    client, admin_headers, make_product
) -> None:
    """§8: старый файл удаляется, если больше нигде не используется."""
    product = await make_product()

    first_url = (
        await client.post(
            f"{PREFIX}/admin/products/{product.id}/photo",
            files={"file": ("a.png", io.BytesIO(_png_bytes()), "image/png")},
            headers=admin_headers,
        )
    ).json()["photo_url"]
    assert _disk_path(first_url).exists()

    second_url = (
        await client.post(
            f"{PREFIX}/admin/products/{product.id}/photo",
            files={"file": ("b.jpg", io.BytesIO(_jpeg_bytes()), "image/jpeg")},
            headers=admin_headers,
        )
    ).json()["photo_url"]

    assert not _disk_path(first_url).exists(), "старый файл остался на диске"
    assert _disk_path(second_url).exists(), "новый файл не сохранён"


async def test_shared_photo_is_not_deleted_while_still_used(
    client, admin_headers, make_product
) -> None:
    """Файл, на который ссылается другой товар, удалять нельзя."""
    first = await make_product(name="Первый")
    second = await make_product(name="Второй")

    shared_url = (
        await client.post(
            f"{PREFIX}/admin/products/{first.id}/photo",
            files={"file": ("shared.png", io.BytesIO(_png_bytes()), "image/png")},
            headers=admin_headers,
        )
    ).json()["photo_url"]

    # Второй товар начинает ссылаться на тот же файл.
    await client.patch(
        f"{PREFIX}/admin/products/{second.id}",
        json={"photo_url": shared_url},
        headers=admin_headers,
    )

    # Первый товар меняет фото — файл всё ещё нужен второму.
    await client.post(
        f"{PREFIX}/admin/products/{first.id}/photo",
        files={"file": ("new.jpg", io.BytesIO(_jpeg_bytes()), "image/jpeg")},
        headers=admin_headers,
    )

    assert _disk_path(shared_url).exists(), "удалён файл, который ещё используется"


async def test_oversized_upload_returns_413(client, admin_headers) -> None:
    """Превышение MAX_UPLOAD_SIZE_MB обрывается до записи на диск."""
    from app.core.config import settings

    before = set(settings.upload_path.iterdir())
    huge = _png_bytes() + b"\x00" * (settings.max_upload_size_bytes + 1024)

    response = await client.post(
        f"{PREFIX}/admin/uploads/photo",
        files={"file": ("huge.png", io.BytesIO(huge), "image/png")},
        headers=admin_headers,
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "file_too_large"
    assert set(settings.upload_path.iterdir()) == before, "огромный файл всё-таки записан"


@pytest.mark.parametrize(
    "name",
    ["../../evil.png", r"..\..\evil.png", "/etc/passwd", "a/../../b.png"],
)
async def test_filename_cannot_escape_upload_dir(client, admin_headers, name: str) -> None:
    """Имя файла приходит от клиента и никогда не используется как путь."""
    from app.core.config import settings

    response = await client.post(
        f"{PREFIX}/admin/uploads/photo",
        files={"file": (name, io.BytesIO(_png_bytes()), "image/png")},
        headers=admin_headers,
    )

    assert response.status_code == 201
    photo_url = response.json()["photo_url"]
    assert ".." not in photo_url
    saved = _disk_path(photo_url).resolve()
    assert saved.parent == settings.upload_path.resolve(), "файл ушёл за пределы UPLOAD_DIR"
