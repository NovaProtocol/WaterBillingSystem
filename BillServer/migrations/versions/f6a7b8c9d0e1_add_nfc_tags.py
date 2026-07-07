"""add nfc_tags table for NFC tag enrollment

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-07-01

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "nfc_tags",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("uid", sa.String(length=64), nullable=False),
        sa.Column("customer_number", sa.String(length=64), nullable=False),
        sa.Column("enrolled_by_id", sa.Integer(), nullable=False),
        sa.Column("date_created", sa.DateTime(), nullable=True),
        sa.Column("last_modified", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["customer_number"],
            ["customers.customer_number"],
        ),
        sa.ForeignKeyConstraint(
            ["enrolled_by_id"],
            ["staff.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uid"),
        mysql_collate="utf8mb4_0900_ai_ci",
        mysql_default_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index(
        op.f("ix_nfc_tags_customer_number"),
        "nfc_tags",
        ["customer_number"],
    )


def downgrade() -> None:
    op.drop_table("nfc_tags")
