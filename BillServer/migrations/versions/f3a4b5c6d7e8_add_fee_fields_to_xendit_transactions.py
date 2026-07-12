"""add fee fields to xendit transactions + seed default fee configs

Revision ID: f3a4b5c6d7e8
Revises: 2f15e6cca1c5
Create Date: 2026-07-12 08:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql
from datetime import datetime

# revision identifiers, used by Alembic.
revision = 'f3a4b5c6d7e8'
down_revision = '735b09844168'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('xendit_transactions', sa.Column('base_amount', sa.Numeric(10, 2), nullable=True))
    op.add_column('xendit_transactions', sa.Column('fee_amount', sa.Numeric(10, 2), nullable=True))
    op.add_column('xendit_transactions', sa.Column('fee_rate', sa.Numeric(5, 2), nullable=True))

    conn = op.get_bind()
    now = datetime.utcnow()

    default_fees = {
        'payment_fee_gcash': '2.0',
        'payment_fee_maya': '2.0',
        'payment_fee_card': '2.5',
        'payment_fee_online_banking': '1.5',
        'payment_fee_otc': '1.5',
        'payment_fee_paylater': '3.0',
        'payment_fee_default': '2.0',
    }

    for key, value in default_fees.items():
        exists = conn.execute(
            sa.text("SELECT COUNT(*) FROM app_config WHERE `key` = :key"),
            {"key": key},
        ).scalar()
        if not exists:
            conn.execute(
                sa.text(
                    "INSERT INTO app_config (`key`, `value`, `date_created`, `date_modified`) "
                    "VALUES (:key, :value, :now, :now)"
                ),
                {"key": key, "value": value, "now": now},
            )


def downgrade():
    op.drop_column('xendit_transactions', 'fee_rate')
    op.drop_column('xendit_transactions', 'fee_amount')
    op.drop_column('xendit_transactions', 'base_amount')

    conn = op.get_bind()
    conn.execute(
        sa.text("DELETE FROM app_config WHERE `key` LIKE 'payment_fee_%'")
    )
