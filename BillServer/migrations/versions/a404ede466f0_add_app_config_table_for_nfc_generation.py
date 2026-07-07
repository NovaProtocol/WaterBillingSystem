"""add app_config table for nfc_generation

Revision ID: a404ede466f0
Revises: 935b84a34f9c
Create Date: 2026-07-03 21:26:05.107349

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a404ede466f0'
down_revision = '935b84a34f9c'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('app_config',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('key', sa.String(length=128), nullable=False),
    sa.Column('value', sa.Text(), nullable=True),
    sa.Column('date_created', sa.DateTime(), nullable=True),
    sa.Column('date_modified', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('key')
    )


def downgrade():
    op.drop_table('app_config')
