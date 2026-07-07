"""add carryover_offset, drop receipt_number unique

Revision ID: 735b09844168
Revises: 5eeffdafdd6c
Create Date: 2026-07-06 16:38:14.211437

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '735b09844168'
down_revision = '5eeffdafdd6c'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('billings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('carryover_offset', sa.Numeric(precision=10, scale=2), nullable=False, server_default=sa.text('0')))
        batch_op.drop_index(batch_op.f('receipt_number'))


def downgrade():
    with op.batch_alter_table('billings', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('receipt_number'), ['receipt_number'], unique=True)
        batch_op.drop_column('carryover_offset')
