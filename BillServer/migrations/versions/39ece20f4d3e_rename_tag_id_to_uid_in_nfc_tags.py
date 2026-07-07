"""rename tag_id to uid in nfc_tags

Revision ID: 39ece20f4d3e
Revises: 935b84a34f9c
Create Date: 2026-07-04

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = '39ece20f4d3e'
down_revision = '935b84a34f9c'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('nfc_tags', sa.Column('uid', sa.String(64), nullable=False, server_default=''))
    op.create_index('idx_uid', 'nfc_tags', ['uid'], unique=True)
    op.drop_column('nfc_tags', 'tag_id')


def downgrade():
    op.add_column('nfc_tags', sa.Column('tag_id', sa.String(128), nullable=False, server_default=''))
    op.create_index('idx_tag_id', 'nfc_tags', ['tag_id'], unique=True)
    op.drop_column('nfc_tags', 'uid')
