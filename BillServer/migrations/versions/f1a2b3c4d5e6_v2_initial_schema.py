"""v2 initial schema

Revision ID: f1a2b3c4d5e6
Revises:
Create Date: 2026-06-22

"""

import sqlalchemy as sa
from alembic import op

revision = "f1a2b3c4d5e6"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # --- staff ---
    op.create_table(
        "staff",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("password", sa.LargeBinary(), nullable=False),
        sa.Column("email", sa.String(length=128), nullable=True),
        sa.Column("contact_number", sa.String(length=32), nullable=True),
        sa.Column("can_read_meters", sa.Boolean(), nullable=True),
        sa.Column("can_accept_payment", sa.Boolean(), nullable=True),
        sa.Column("can_enroll_customer", sa.Boolean(), nullable=True),
        sa.Column("can_drop_reading", sa.Boolean(), nullable=True),
        sa.Column("can_drop_payment", sa.Boolean(), nullable=True),
        sa.Column("can_enroll_staff", sa.Boolean(), nullable=True),
        sa.Column("can_manage_billing", sa.Boolean(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column("date_created", sa.DateTime(), nullable=True),
        sa.Column("last_modified", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
        mysql_collate="utf8mb4_0900_ai_ci",
        mysql_default_charset="utf8mb4",
        mysql_engine="InnoDB",
    )

    # --- customers ---
    op.create_table(
        "customers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("customer_number", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("contact_number", sa.String(length=32), nullable=True),
        sa.Column("email", sa.String(length=128), nullable=True),
        sa.Column("x_coordinate", sa.Float(), nullable=True),
        sa.Column("y_coordinate", sa.Float(), nullable=True),
        sa.Column(
            "cumulative_balance", sa.Numeric(precision=10, scale=2), nullable=True
        ),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("date_created", sa.DateTime(), nullable=True),
        sa.Column("date_modified", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("customer_number"),
        mysql_collate="utf8mb4_0900_ai_ci",
        mysql_default_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index(
        op.f("ix_customers_customer_number"), "customers", ["customer_number"]
    )

    # --- meter_readings ---
    op.create_table(
        "meter_readings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("customer_number", sa.String(length=64), nullable=False),
        sa.Column("reading_value", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("reader_id", sa.String(length=64), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("date_created", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["customer_number"],
            ["customers.customer_number"],
        ),
        sa.PrimaryKeyConstraint("id"),
        mysql_collate="utf8mb4_0900_ai_ci",
        mysql_default_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index(
        op.f("ix_meter_readings_customer_number"), "meter_readings", ["customer_number"]
    )
    op.create_index(
        op.f("ix_meter_readings_reader_id"), "meter_readings", ["reader_id"]
    )
    op.create_index(
        op.f("ix_meter_readings_timestamp"), "meter_readings", ["timestamp"]
    )

    # --- billings ---
    op.create_table(
        "billings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("customer_number", sa.String(length=64), nullable=False),
        sa.Column("receipt_number", sa.String(length=64), nullable=False),
        sa.Column("paid_amount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("cashier_id", sa.Integer(), nullable=False),
        sa.Column("reading_id", sa.Integer(), nullable=True),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("date_created", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["customer_number"],
            ["customers.customer_number"],
        ),
        sa.ForeignKeyConstraint(
            ["cashier_id"],
            ["staff.id"],
        ),
        sa.ForeignKeyConstraint(
            ["reading_id"],
            ["meter_readings.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("receipt_number"),
        mysql_collate="utf8mb4_0900_ai_ci",
        mysql_default_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index(
        op.f("ix_billings_customer_number"), "billings", ["customer_number"]
    )
    op.create_index(op.f("ix_billings_cashier_id"), "billings", ["cashier_id"])
    op.create_index(op.f("ix_billings_timestamp"), "billings", ["timestamp"])

    # --- api_keys ---
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("label", sa.String(length=128), nullable=True),
        sa.Column("staff_id", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column("date_created", sa.DateTime(), nullable=True),
        sa.Column("last_modified", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["staff_id"],
            ["staff.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
        mysql_collate="utf8mb4_0900_ai_ci",
        mysql_default_charset="utf8mb4",
        mysql_engine="InnoDB",
    )

    # --- billing_receives ---
    op.create_table(
        "billing_receives",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("billing_id", sa.Integer(), nullable=True),
        sa.Column("staff_id", sa.Integer(), nullable=False),
        sa.Column("customer_number", sa.String(length=64), nullable=False),
        sa.Column("amount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("receipt_number", sa.String(length=64), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("date_created", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["billing_id"],
            ["billings.id"],
        ),
        sa.ForeignKeyConstraint(
            ["staff_id"],
            ["staff.id"],
        ),
        sa.ForeignKeyConstraint(
            ["customer_number"],
            ["customers.customer_number"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("receipt_number"),
        mysql_collate="utf8mb4_0900_ai_ci",
        mysql_default_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index(
        op.f("ix_billing_receives_customer_number"),
        "billing_receives",
        ["customer_number"],
    )
    op.create_index(
        op.f("ix_billing_receives_timestamp"), "billing_receives", ["timestamp"]
    )

    # --- management_logs ---
    op.create_table(
        "management_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("staff_id", sa.Integer(), nullable=False),
        sa.Column("action_type", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("date_created", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["staff_id"],
            ["staff.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        mysql_collate="utf8mb4_0900_ai_ci",
        mysql_default_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index(
        op.f("ix_management_logs_timestamp"), "management_logs", ["timestamp"]
    )


def downgrade():
    op.drop_table("management_logs")
    op.drop_table("billing_receives")
    op.drop_table("api_keys")
    op.drop_table("billings")
    op.drop_table("meter_readings")
    op.drop_table("customers")
    op.drop_table("staff")
