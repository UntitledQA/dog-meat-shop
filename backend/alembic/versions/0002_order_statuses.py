"""Сокращение набора статусов заказа.

Было: new -> confirmed -> preparing -> delivering -> completed (+ cancelled).
Стало: заказ создаётся сразу подтверждённым, промежуточной «сборки» нет.

    самовывоз : confirmed -> completed
    доставка  : confirmed -> delivering -> completed

Существующие заказы в статусах ``new`` и ``preparing`` переводятся в
``confirmed``: оба означали «принят, но ещё не отдан покупателю», и ближайший
к ним статус из нового набора — именно подтверждённый. Отменённые и
выполненные заказы не трогаем.

Заодно добавляется CHECK-ограничение на ``status`` и ``delivery_type``.
Раньше его не было: у ``sa.Enum(native_enum=False)`` параметр
``create_constraint`` с SQLAlchemy 1.4 по умолчанию False, поэтому колонки
создавались обычным VARCHAR, и мимо приложения в них можно было записать
произвольную строку.

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_STATUSES = ("confirmed", "delivering", "completed", "cancelled")
OLD_STATUSES = ("new", "confirmed", "preparing", "delivering", "completed", "cancelled")
DELIVERY_TYPES = ("delivery", "pickup")


def _in_list(values: Sequence[str]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def upgrade() -> None:
    # 1. Данные: убираемые статусы схлопываются в confirmed.
    op.execute(
        sa.text(
            "UPDATE orders SET status = 'confirmed' WHERE status IN ('new', 'preparing')"
        )
    )

    # 2. Значение по умолчанию: заказ рождается подтверждённым.
    op.alter_column(
        "orders",
        "status",
        existing_type=sa.String(length=20),
        existing_nullable=False,
        server_default="confirmed",
    )

    # 3. Ограничения. batch_alter_table нужен ради SQLite: там CHECK нельзя
    #    добавить на месте, таблица пересоздаётся. В PostgreSQL это обычный ALTER.
    with op.batch_alter_table("orders", schema=None) as batch_op:
        batch_op.create_check_constraint(
            "order_status", f"status IN ({_in_list(NEW_STATUSES)})"
        )
        batch_op.create_check_constraint(
            "delivery_type", f"delivery_type IN ({_in_list(DELIVERY_TYPES)})"
        )


def downgrade() -> None:
    with op.batch_alter_table("orders", schema=None) as batch_op:
        batch_op.drop_constraint("delivery_type", type_="check")
        batch_op.drop_constraint("order_status", type_="check")

    op.alter_column(
        "orders",
        "status",
        existing_type=sa.String(length=20),
        existing_nullable=False,
        server_default="new",
    )
    # Данные назад не разворачиваем: исходные new и preparing неразличимы после
    # схлопывания, и угадывать, каким был каждый заказ, значило бы портить их.
    _ = OLD_STATUSES
