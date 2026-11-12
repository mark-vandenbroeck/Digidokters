"""add_deelnemers_and_activity_type_flag

Revision ID: d1e2f3a4b5c6
Revises: c9e1a2b3d4f5
Create Date: 2026-11-04 07:17:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd1e2f3a4b5c6'
down_revision = 'c9e1a2b3d4f5'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = insp.get_table_names()

    # 1. Add registreer_deelnemers flag to activity_types if not present
    if 'activity_types' in tables:
        cols = [c['name'] for c in insp.get_columns('activity_types')]
        if 'registreer_deelnemers' not in cols:
            with op.batch_alter_table('activity_types', schema=None) as batch_op:
                batch_op.add_column(sa.Column('registreer_deelnemers', sa.Boolean(), nullable=False, server_default=sa.false()))

    # 2. Create deelnemers table if not exists
    if 'deelnemers' not in tables:
        op.create_table(
            'deelnemers',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('naam', sa.String(length=150), nullable=False),
            sa.Column('actief', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('organisatie_id', sa.Integer(), nullable=False),
            sa.Column('aangemaakt_op', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(['organisatie_id'], ['organisaties.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('organisatie_id', 'naam', name='uq_deelnemer_org_naam')
        )
        with op.batch_alter_table('deelnemers', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_deelnemers_organisatie_id'), ['organisatie_id'], unique=False)

    # 3. Create agenda_item_deelnemers association table if not exists
    if 'agenda_item_deelnemers' not in tables:
        op.create_table(
            'agenda_item_deelnemers',
            sa.Column('agenda_item_id', sa.Integer(), nullable=False),
            sa.Column('deelnemer_id', sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(['agenda_item_id'], ['agenda_items.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['deelnemer_id'], ['deelnemers.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('agenda_item_id', 'deelnemer_id')
        )


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = insp.get_table_names()

    if 'agenda_item_deelnemers' in tables:
        op.drop_table('agenda_item_deelnemers')

    if 'deelnemers' in tables:
        op.drop_table('deelnemers')

    if 'activity_types' in tables:
        cols = [c['name'] for c in insp.get_columns('activity_types')]
        if 'registreer_deelnemers' in cols:
            with op.batch_alter_table('activity_types', schema=None) as batch_op:
                batch_op.drop_column('registreer_deelnemers')

