"""add phase/block/street to customers

Revision ID: a1b2c3d4e5f6
Revises: d0f4d6e96c07
Create Date: 2026-06-23 16:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = "d0f4d6e96c07"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("customers") as batch_op:
        batch_op.add_column(sa.Column("phase", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("block", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("street", sa.String(length=128), nullable=True))


def downgrade():
    with op.batch_alter_table("customers") as batch_op:
        batch_op.drop_column("phase")
        batch_op.drop_column("block")
        batch_op.drop_column("street")
