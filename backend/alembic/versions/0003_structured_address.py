"""Структурированный адрес доставки вместо интервала времени.

Зачем убираем ``delivery_time``. Интервал («12:00-15:00») был свободной строкой,
которую покупатель выбирал из выпадающего списка, а курьер всё равно созванивался
и договаривался заново. Поле не участвовало ни в одном расчёте и ни в одной
проверке — оно только создавало иллюзию обязательства, которое магазин не давал.
Осталась одна дата доставки: её действительно видно и в боте, и в админке.

**Данные интервалов при upgrade теряются безвозвратно.** Колонка удаляется вместе
со всем содержимым, резервной копии миграция не делает. ``downgrade()`` вернёт
пустую колонку той же формы (nullable String(64)), но не значения: восстановить
их будет неоткуда.

Зачем добавляем разобранный адрес. Раньше адрес хранился одной строкой ровно так,
как её набрал покупатель, — по ней нельзя ни построить маршрут, ни отсортировать
заказы по районам. Сервис адресных подсказок отдаёт разобранные части и координаты,
и теперь они сохраняются рядом с исходной строкой, а не вместо неё: плоский
``address`` остаётся тем, что покупатель видит и правит руками.

Все шесть колонок nullable, и это намеренно. Подсказка может не знать индекс или
номер дома, а покупатель — ввести адрес руками, вообще без подсказки. Заказ в таком
случае обязан оформиться: обязательным остаётся только плоский ``address`` при
доставке, и проверяет его схема, а не БД.

Координаты — ``Numeric(9, 6)``, а не ``float``: деньги, вес и координаты в этом
проекте живут только в Decimal. Шесть знаков после точки дают около 0.1 м на
местности, три знака до точки ровно покрывают предельную долготу 180.000000.

``batch_alter_table`` нужен ради SQLite: там нет ``ALTER TABLE ... DROP COLUMN``,
таблица пересоздаётся с переносом данных. В PostgreSQL это обычные ALTER.

Revision ID: 0003
Revises: 0002
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Координаты: шесть знаков после точки, три до неё (хватает долготе 180.000000).
COORDINATE = sa.Numeric(precision=9, scale=6)

#: Новые колонки разобранного адреса — все необязательные.
ADDRESS_COLUMNS: tuple[tuple[str, sa.types.TypeEngine], ...] = (
    ("address_city", sa.String(length=120)),
    ("address_street", sa.String(length=255)),
    ("address_house", sa.String(length=32)),
    ("address_postal_code", sa.String(length=16)),
    ("address_lat", COORDINATE),
    ("address_lon", COORDINATE),
)


def upgrade() -> None:
    with op.batch_alter_table("orders", schema=None) as batch_op:
        for name, column_type in ADDRESS_COLUMNS:
            batch_op.add_column(sa.Column(name, column_type, nullable=True))
        # Значения интервалов уходят вместе с колонкой и не восстанавливаются.
        batch_op.drop_column("delivery_time")


def downgrade() -> None:
    with op.batch_alter_table("orders", schema=None) as batch_op:
        # Возвращается только форма колонки: содержимое было удалено при upgrade.
        batch_op.add_column(sa.Column("delivery_time", sa.String(length=64), nullable=True))
        for name, _column_type in reversed(ADDRESS_COLUMNS):
            batch_op.drop_column(name)
