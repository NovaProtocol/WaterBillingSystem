"""billing_overhaul_and_max_meter_value

Revision ID: b2825fc5a8c4
Revises: 2f15e6cca1c5
Create Date: 2026-07-06 06:08:39.634364

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects import mysql

revision = 'b2825fc5a8c4'
down_revision = '2f15e6cca1c5'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('billings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('previous_reading_value', sa.Numeric(precision=10, scale=2), nullable=True))
        batch_op.add_column(sa.Column('current_reading_value', sa.Numeric(precision=10, scale=2), nullable=True))
        batch_op.add_column(sa.Column('consumption', sa.Numeric(precision=10, scale=2), nullable=True))
        batch_op.add_column(sa.Column('billed_amount', sa.Numeric(precision=10, scale=2), nullable=True))
        batch_op.add_column(sa.Column('penalty', sa.Numeric(precision=10, scale=2), nullable=True))
        batch_op.add_column(sa.Column('is_paid', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('payment_timestamp', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('date_paid', sa.DateTime(), nullable=True))

    # Backfill existing records (all represent completed payments)
    conn = op.get_bind()
    conn.execute(text(
        "UPDATE billings SET "
        "billed_amount = paid_amount, "
        "penalty = 0, "
        "is_paid = TRUE, "
        "payment_timestamp = `timestamp`, "
        "date_paid = `timestamp` "
        "WHERE is_paid IS NULL"
    ))
    conn.execute(text("UPDATE billings SET billed_amount = 0 WHERE billed_amount IS NULL"))
    conn.execute(text("UPDATE billings SET penalty = 0 WHERE penalty IS NULL"))
    conn.execute(text("UPDATE billings SET is_paid = FALSE WHERE is_paid IS NULL"))

    with op.batch_alter_table('billings', schema=None) as batch_op:
        batch_op.alter_column('billed_amount', existing_type=mysql.DECIMAL(10, 2), nullable=False)
        batch_op.alter_column('penalty', existing_type=mysql.DECIMAL(10, 2), nullable=False)
        batch_op.alter_column('is_paid', existing_type=sa.Boolean(), nullable=False)
        batch_op.alter_column('receipt_number', existing_type=mysql.VARCHAR(length=64), nullable=True)
        batch_op.alter_column('cashier_id', existing_type=mysql.INTEGER(), nullable=True)
        batch_op.drop_index(batch_op.f('ix_billings_timestamp'))
        batch_op.drop_column('timestamp')

    with op.batch_alter_table('customers', schema=None) as batch_op:
        batch_op.add_column(sa.Column('max_meter_value', sa.Numeric(precision=10, scale=2), nullable=True))
        batch_op.drop_index(batch_op.f('ix_customers_customer_number'))
        batch_op.create_index(batch_op.f('ix_customers_customer_number'), ['customer_number'], unique=True)

    # Set default max_meter_value for existing customers
    conn.execute(text("UPDATE customers SET max_meter_value = 99999 WHERE max_meter_value IS NULL"))


def downgrade():
    with op.batch_alter_table('customers', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_customers_customer_number'))
        batch_op.create_index(batch_op.f('ix_customers_customer_number'), ['customer_number'], unique=False)
        batch_op.drop_column('max_meter_value')

    with op.batch_alter_table('billings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('timestamp', mysql.DATETIME(), nullable=True))
    conn = op.get_bind()
    conn.execute(text("UPDATE billings SET `timestamp` = payment_timestamp WHERE `timestamp` IS NULL"))
    with op.batch_alter_table('billings', schema=None) as batch_op:
        batch_op.alter_column('timestamp', existing_type=mysql.DATETIME(), nullable=False)
        batch_op.create_index(batch_op.f('ix_billings_timestamp'), ['timestamp'], unique=False)
        batch_op.alter_column('cashier_id', existing_type=mysql.INTEGER(), nullable=False)
        batch_op.alter_column('receipt_number', existing_type=mysql.VARCHAR(length=64), nullable=False)
        batch_op.drop_column('date_paid')
        batch_op.drop_column('payment_timestamp')
        batch_op.drop_column('is_paid')
        batch_op.drop_column('penalty')
        batch_op.drop_column('billed_amount')
        batch_op.drop_column('consumption')
        batch_op.drop_column('current_reading_value')
        batch_op.drop_column('previous_reading_value')
