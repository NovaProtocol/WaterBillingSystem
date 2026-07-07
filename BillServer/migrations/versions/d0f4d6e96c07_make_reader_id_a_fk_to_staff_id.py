"""make reader_id a FK to staff.id

Existing string data in reader_id cannot be converted to integer FK references,
so meter_readings data is discarded (test data only at this stage).

Revision ID: d0f4d6e96c07
Revises: f1a2b3c4d5e6
Create Date: 2026-06-23 11:30:14.422621

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = "d0f4d6e96c07"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None

FK_NAME = "fk_meter_readings_reader_id_staff"


def upgrade():
    op.execute("DELETE FROM billing_receives")
    op.execute("DELETE FROM billings")
    op.execute("DELETE FROM meter_readings")
    op.drop_column("meter_readings", "reader_id")
    op.add_column(
        "meter_readings", sa.Column("reader_id", sa.Integer(), nullable=False)
    )
    op.create_foreign_key(FK_NAME, "meter_readings", "staff", ["reader_id"], ["id"])
    op.create_index(
        op.f("ix_meter_readings_reader_id"), "meter_readings", ["reader_id"]
    )


def downgrade():
    op.execute("DELETE FROM billing_receives")
    op.execute("DELETE FROM billings")
    op.execute("DELETE FROM meter_readings")
    op.drop_constraint(FK_NAME, "meter_readings", type_="foreignkey")
    op.drop_index(op.f("ix_meter_readings_reader_id"), table_name="meter_readings")
    op.drop_column("meter_readings", "reader_id")
    op.add_column(
        "meter_readings",
        sa.Column("reader_id", mysql.VARCHAR(length=64), nullable=False),
    )
    op.create_index(
        op.f("ix_meter_readings_reader_id"), "meter_readings", ["reader_id"]
    )
