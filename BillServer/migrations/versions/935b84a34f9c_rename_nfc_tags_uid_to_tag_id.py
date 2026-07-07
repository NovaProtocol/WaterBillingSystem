"""rename_nfc_tags_uid_to_tag_id

Revision ID: 935b84a34f9c
Revises: f6a7b8c9d0e1
Create Date: 2026-07-03 16:52:44.996775

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '935b84a34f9c'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('nfc_tags', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tag_id', sa.String(length=128), nullable=False))
        batch_op.drop_index(batch_op.f('uid'))
        batch_op.create_unique_constraint(None, ['tag_id'])
        batch_op.drop_column('uid')


def downgrade():
    with op.batch_alter_table('nfc_tags', schema=None) as batch_op:
        batch_op.add_column(sa.Column('uid', mysql.VARCHAR(length=64), nullable=False))
        batch_op.drop_constraint(None, type_='unique')
        batch_op.create_index(batch_op.f('uid'), ['uid'], unique=True)
        batch_op.drop_column('tag_id')
