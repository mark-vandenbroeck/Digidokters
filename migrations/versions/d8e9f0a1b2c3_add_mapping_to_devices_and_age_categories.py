"""add mapping to devices and age_categories

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-09-12 15:15:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd8e9f0a1b2c3'
down_revision = 'c7d8e9f0a1b2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('devices') as batch_op:
        batch_op.add_column(sa.Column('mapped_to_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_devices_mapped_to_id', 'devices', ['mapped_to_id'], ['id'], ondelete='SET NULL')

    with op.batch_alter_table('age_categories') as batch_op:
        batch_op.add_column(sa.Column('mapped_to_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_age_categories_mapped_to_id', 'age_categories', ['mapped_to_id'], ['id'], ondelete='SET NULL')


def downgrade():
    with op.batch_alter_table('age_categories') as batch_op:
        batch_op.drop_constraint('fk_age_categories_mapped_to_id', type_='foreignkey')
        batch_op.drop_column('mapped_to_id')

    with op.batch_alter_table('devices') as batch_op:
        batch_op.drop_constraint('fk_devices_mapped_to_id', type_='foreignkey')
        batch_op.drop_column('mapped_to_id')
