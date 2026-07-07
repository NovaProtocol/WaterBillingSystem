"""add FK constraint for management_logs.customer_number

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-25

"""
from __future__ import annotations

from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "c3d4e5f6a7b8"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_foreign_key(
        "fk_management_logs_customer_number",
        "management_logs",
        "customers",
        ["customer_number"],
        ["customer_number"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_management_logs_customer_number", "management_logs", type_="foreignkey"
    )
