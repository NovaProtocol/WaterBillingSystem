"""add customer_number column to management_logs

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-25

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: str | None = "b2c3d4e5f6a7"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "management_logs",
        sa.Column("customer_number", sa.String(64), nullable=True, index=True),
    )
    # Backfill existing rows so the column isn't empty — C0001 as a fallback
    op.execute(
        "UPDATE management_logs SET customer_number = 'C0001' WHERE customer_number IS NULL"
    )
    op.create_foreign_key(
        "fk_management_logs_customer_number",
        "management_logs",
        "customers",
        ["customer_number"],
        ["customer_number"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_management_logs_customer_number", "management_logs", type_="foreignkey")
    op.drop_column("management_logs", "customer_number")
