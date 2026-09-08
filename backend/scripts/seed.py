"""Наполнение каталога демонстрационными товарами.

Запуск:

    python -m scripts.seed

Скрипт идемпотентен: товары сопоставляются по названию, повторный запуск
обновляет цену и остаток, но не плодит дубликаты.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.logging import configure_logging, get_logger
from app.models import Product

logger = get_logger(__name__)

#: (название, описание, цена за кг, остаток, активен)
DEMO_PRODUCTS: list[tuple[str, str, str, str, bool]] = [
    (
        "Говядина односортная",
        "Мякоть говядины без костей, крупная нарезка. Основа рациона для взрослых "
        "собак средних и крупных пород. Поставляется охлаждённой.",
        "620.00",
        "24.500",
        True,
    ),
    (
        "Куриные шеи",
        "Мягкие куриные шеи — источник кальция и природная чистка зубов. "
        "Подходят для щенков с четырёх месяцев.",
        "230.00",
        "18.000",
        True,
    ),
    (
        "Индейка, филе бедра",
        "Диетическое мясо индейки для собак со склонностью к аллергии. "
        "Нежирное, легко усваивается.",
        "540.00",
        "12.300",
        True,
    ),
    (
        "Рубец говяжий неочищенный",
        "Натуральный неочищенный рубец — источник ферментов и полезной микрофлоры. "
        "Обладает выраженным запахом, который очень нравится собакам.",
        "320.00",
        "9.700",
        True,
    ),
    (
        "Сердце говяжье",
        "Мышечный субпродукт с высоким содержанием таурина и белка. "
        "Рекомендуется как добавка два-три раза в неделю.",
        "410.00",
        "0.000",  # проверка отображения «Нет в наличии»
        True,
    ),
    (
        "Печень куриная",
        "Богата витамином A и железом. Даётся небольшими порциями как дополнение "
        "к основному рациону.",
        "280.00",
        "6.400",
        True,
    ),
    (
        "Ягнёнок, обрезь (сезонно)",
        "Сезонная позиция, временно снята с продажи. Пример скрытого товара: "
        "покупателям он не показывается, но сохраняется в старых заказах.",
        "780.00",
        "0.000",
        False,
    ),
]


async def seed() -> tuple[int, int]:
    """Создаёт или обновляет демонстрационные товары. Возвращает (создано, обновлено)."""
    created = 0
    updated = 0

    async with SessionLocal() as session:
        for name, description, price, stock, is_active in DEMO_PRODUCTS:
            product = await session.scalar(select(Product).where(Product.name == name))
            if product is None:
                session.add(
                    Product(
                        name=name,
                        description=description,
                        price_per_kg=Decimal(price),
                        stock_kg=Decimal(stock),
                        is_active=is_active,
                    )
                )
                created += 1
            else:
                product.description = description
                product.price_per_kg = Decimal(price)
                product.stock_kg = Decimal(stock)
                product.is_active = is_active
                updated += 1

        await session.commit()

    return created, updated


async def main() -> None:
    configure_logging()
    created, updated = await seed()
    logger.info("seed_completed", created=created, updated=updated)
    print(f"Готово: создано {created}, обновлено {updated} товаров.")


if __name__ == "__main__":
    asyncio.run(main())
