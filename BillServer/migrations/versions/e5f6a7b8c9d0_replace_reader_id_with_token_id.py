"""replace reader_id (FK→staff) with token_id (FK→api_keys), make api_keys.staff_id non-nullable

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-06-30

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | None = None
depends_on: str | None = None

OLD_FK = "fk_meter_readings_reader_id_staff"


def upgrade() -> None:
    # ------- meter_readings: reader_id -> token_id -------
    op.execute("DELETE FROM billings")
    op.execute("DELETE FROM meter_readings")

    op.drop_constraint(OLD_FK, "meter_readings", type_="foreignkey")
    op.drop_index(op.f("ix_meter_readings_reader_id"), table_name="meter_readings")
    op.drop_column("meter_readings", "reader_id")

    op.add_column(
        "meter_readings",
        sa.Column("token_id", sa.Integer(), nullable=False),
    )
    op.create_foreign_key(
        "fk_meter_readings_token_id", "meter_readings", "api_keys", ["token_id"], ["id"]
    )
    op.create_index(
        op.f("ix_meter_readings_token_id"), "meter_readings", ["token_id"]
    )

    # ------- api_keys: staff_id non-nullable -------
    op.alter_column("api_keys", "staff_id", existing_type=sa.Integer(), nullable=False)


def downgrade() -> None:
    # ------- api_keys: staff_id nullable -------
    op.alter_column("api_keys", "staff_id", existing_type=sa.Integer(), nullable=True)

    # ------- meter_readings: token_id -> reader_id -------
    op.execute("DELETE FROM meter_readings")
    op.drop_constraint("fk_meter_readings_token_id", "meter_readings", type_="foreignkey")
    op.drop_index(op.f("ix_meter_readings_token_id"), table_name="meter_readings")
    op.drop_column("meter_readings", "token_id")

    op.add_column(
        "meter_readings",
        sa.Column("reader_id", sa.Integer(), nullable=False),
    )
    op.create_foreign_key(OLD_FK, "meter_readings", "staff", ["reader_id"], ["id"])
    op.create_index(
        op.f("ix_meter_readings_reader_id"), "meter_readings", ["reader_id"]
    )
