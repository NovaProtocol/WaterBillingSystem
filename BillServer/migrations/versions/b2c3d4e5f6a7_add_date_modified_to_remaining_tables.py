"""add date_modified to readings, billings, billing_receives, management_logs
also drop billing_receives table (replaced by Billing)

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-25

"""
from __future__ import annotations

from typing import ClassVar

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    for table in ("meter_readings", "billings", "management_logs"):
        op.add_column(
            table,
            sa.Column(
                "date_modified",
                sa.DateTime(),
                nullable=True,
            ),
        )
    op.drop_table("billing_receives")


def downgrade() -> None:
    for table in ("meter_readings", "billings", "management_logs"):
        op.drop_column(table, "date_modified")
    op.create_table(
        "billing_receives",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("billing_id", sa.Integer(), nullable=True),
        sa.Column("staff_id", sa.Integer(), nullable=False),
        sa.Column("customer_number", sa.String(64), nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("receipt_number", sa.String(64), nullable=False, unique=True),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("date_created", sa.DateTime(), nullable=True),
        sa.Column("date_modified", sa.DateTime(), nullable=True),
    )
