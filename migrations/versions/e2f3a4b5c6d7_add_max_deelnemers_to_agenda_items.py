"""add_max_deelnemers_to_agenda_items

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-11-05 19:54:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e2f3a4b5c6d7'
down_revision = 'd1e2f3a4b5c6'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = insp.get_table_names()

    if 'agenda_items' in tables:
        cols = [c['name'] for c in insp.get_columns('agenda_items')]
        if 'max_deelnemers' not in cols:
            with op.batch_alter_table('agenda_items', schema=None) as batch_op:
                batch_op.add_column(sa.Column('max_deelnemers', sa.Integer(), nullable=True))


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = insp.get_table_names()

    if 'agenda_items' in tables:
        cols = [c['name'] for c in insp.get_columns('agenda_items')]
        if 'max_deelnemers' in cols:
            with op.batch_alter_table('agenda_items', schema=None) as batch_op:
                batch_op.drop_column('max_deelnemers')

