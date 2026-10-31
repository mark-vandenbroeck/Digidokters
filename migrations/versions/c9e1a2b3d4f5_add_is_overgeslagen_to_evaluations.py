"""add_is_overgeslagen_to_evaluations

Revision ID: c9e1a2b3d4f5
Revises: a71c8e2d3b45
Create Date: 2026-10-31 20:25:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c9e1a2b3d4f5'
down_revision = 'a71c8e2d3b45'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = insp.get_table_names()

    if 'evaluatie_reacties' in tables:
        cols = [c['name'] for c in insp.get_columns('evaluatie_reacties')]
        if 'is_overgeslagen' not in cols:
            with op.batch_alter_table('evaluatie_reacties', schema=None) as batch_op:
                batch_op.add_column(sa.Column('is_overgeslagen', sa.Boolean(), nullable=False, server_default=sa.false()))

    if 'evaluatie_uitnodigingen' in tables:
        cols = [c['name'] for c in insp.get_columns('evaluatie_uitnodigingen')]
        if 'is_overgeslagen' not in cols:
            with op.batch_alter_table('evaluatie_uitnodigingen', schema=None) as batch_op:
                batch_op.add_column(sa.Column('is_overgeslagen', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = insp.get_table_names()

    if 'evaluatie_uitnodigingen' in tables:
        cols = [c['name'] for c in insp.get_columns('evaluatie_uitnodigingen')]
        if 'is_overgeslagen' in cols:
            with op.batch_alter_table('evaluatie_uitnodigingen', schema=None) as batch_op:
                batch_op.drop_column('is_overgeslagen')

    if 'evaluatie_reacties' in tables:
        cols = [c['name'] for c in insp.get_columns('evaluatie_reacties')]
        if 'is_overgeslagen' in cols:
            with op.batch_alter_table('evaluatie_reacties', schema=None) as batch_op:
                batch_op.drop_column('is_overgeslagen')

