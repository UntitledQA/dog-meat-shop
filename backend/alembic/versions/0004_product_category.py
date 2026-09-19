"""Категория товара: необязательная колонка ``category`` в ``products``.

Категории хранятся тем же способом, что и статусы заказа, — фиксированный
перечень значений в колонке VARCHAR(32) + CHECK (``native_enum=False``), а не
отдельной таблицей. Это повторяет уже принятый в проекте паттерн и не требует
ни новой таблицы, ни справочника.

Колонка **nullable** и намеренно: у существующих товаров категории нет, и
проставлять её миграцией нельзя — заказы и витрина должны продолжать работать
с товарами «без категории». Поэтому upgrade только добавляет колонку и CHECK,
не трогая ни одной существующей строки (все они остаются с ``category = NULL``).

CHECK допускает NULL явно (``category IS NULL OR category IN (...)``): для
nullable-колонки это читается однозначно и одинаково ведёт себя в PostgreSQL и
SQLite.

``batch_alter_table`` нужен ради SQLite: там нет ``ALTER TABLE ... ADD CONSTRAINT``
и таблица пересоздаётся с переносом данных. В PostgreSQL это обычные ALTER.
Индекс создаётся отдельным ``op.create_index`` уже поверх готовой колонки —
имя ``ix_products_category`` совпадает с тем, что порождает ``index=True`` в модели.

Новая категория в будущем добавляется отдельной миграцией, которая пересоздаёт
CHECK с расширенным списком (существующие миграции не редактируются).

Revision ID: 0004
Revises: 0003
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Допустимые slug категорий. Тот же список, что и ProductCategory в модели.
CATEGORIES = ("beef", "veal", "horse-meat", "duck", "fish", "dried-treats")


def _in_list(values: Sequence[str]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def upgrade() -> None:
    with op.batch_alter_table("products", schema=None) as batch_op:
        batch_op.add_column(sa.Column("category", sa.String(length=32), nullable=True))
        batch_op.create_check_constraint(
            "product_category",
            f"category IS NULL OR category IN ({_in_list(CATEGORIES)})",
        )
    op.create_index("ix_products_category", "products", ["category"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_products_category", table_name="products")
    with op.batch_alter_table("products", schema=None) as batch_op:
        batch_op.drop_constraint("product_category", type_="check")
        batch_op.drop_column("category")
