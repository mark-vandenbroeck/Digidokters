"""add_agenda_item_locks_and_gewijzigd_op

Revision ID: a71c8e2d3b45
Revises: f60bb00e9edf
Create Date: 2026-10-27 17:21:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a71c8e2d3b45'
down_revision = 'f60bb00e9edf'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = insp.get_table_names()

    # 1. Voeg gewijzigd_op toe aan agenda_items indien niet aanwezig
    if 'agenda_items' in tables:
        cols = [c['name'] for c in insp.get_columns('agenda_items')]
        if 'gewijzigd_op' not in cols:
            with op.batch_alter_table('agenda_items', schema=None) as batch_op:
                batch_op.add_column(sa.Column('gewijzigd_op', sa.DateTime(), nullable=True))

    # 2. Maak agenda_item_locks tabel aan indien niet aanwezig
    if 'agenda_item_locks' not in tables:
        op.create_table(
            'agenda_item_locks',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('agenda_item_id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('user_naam', sa.String(length=100), nullable=False),
            sa.Column('locked_at', sa.DateTime(), nullable=False),
            sa.Column('expires_at', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['agenda_item_id'], ['agenda_items.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('agenda_item_id', name='uq_agenda_item_locks_agenda_item_id')
        )
        op.create_index(op.f('ix_agenda_item_locks_agenda_item_id'), 'agenda_item_locks', ['agenda_item_id'], unique=True)
        op.create_index(op.f('ix_agenda_item_locks_expires_at'), 'agenda_item_locks', ['expires_at'], unique=False)


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = insp.get_table_names()

    if 'agenda_item_locks' in tables:
        op.drop_table('agenda_item_locks')

    if 'agenda_items' in tables:
        cols = [c['name'] for c in insp.get_columns('agenda_items')]
        if 'gewijzigd_op' in cols:
            with op.batch_alter_table('agenda_items', schema=None) as batch_op:
                batch_op.drop_column('gewijzigd_op')
