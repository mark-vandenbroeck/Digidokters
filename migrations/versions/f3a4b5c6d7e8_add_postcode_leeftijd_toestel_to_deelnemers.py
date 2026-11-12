"""add_postcode_leeftijd_toestel_to_deelnemers

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-11-12 14:45:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f3a4b5c6d7e8'
down_revision = 'e2f3a4b5c6d7'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = insp.get_table_names()

    if 'deelnemers' in tables:
        cols = [c['name'] for c in insp.get_columns('deelnemers')]
        with op.batch_alter_table('deelnemers', schema=None) as batch_op:
            if 'postcode' not in cols:
                batch_op.add_column(sa.Column('postcode', sa.String(length=20), nullable=True))
            if 'leeftijdscategorie_id' not in cols:
                batch_op.add_column(sa.Column('leeftijdscategorie_id', sa.Integer(), nullable=True))
                batch_op.create_foreign_key('fk_deelnemers_leeftijdscategorie_id', 'age_categories', ['leeftijdscategorie_id'], ['id'], ondelete='SET NULL')
                batch_op.create_index(batch_op.f('ix_deelnemers_leeftijdscategorie_id'), ['leeftijdscategorie_id'], unique=False)
            if 'toestel_id' not in cols:
                batch_op.add_column(sa.Column('toestel_id', sa.Integer(), nullable=True))
                batch_op.create_foreign_key('fk_deelnemers_toestel_id', 'devices', ['toestel_id'], ['id'], ondelete='SET NULL')
                batch_op.create_index(batch_op.f('ix_deelnemers_toestel_id'), ['toestel_id'], unique=False)


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = insp.get_table_names()

    if 'deelnemers' in tables:
        cols = [c['name'] for c in insp.get_columns('deelnemers')]
        with op.batch_alter_table('deelnemers', schema=None) as batch_op:
            if 'toestel_id' in cols:
                batch_op.drop_constraint('fk_deelnemers_toestel_id', type_='foreignkey')
                batch_op.drop_index(batch_op.f('ix_deelnemers_toestel_id'))
                batch_op.drop_column('toestel_id')
            if 'leeftijdscategorie_id' in cols:
                batch_op.drop_constraint('fk_deelnemers_leeftijdscategorie_id', type_='foreignkey')
                batch_op.drop_index(batch_op.f('ix_deelnemers_leeftijdscategorie_id'))
                batch_op.drop_column('leeftijdscategorie_id')
            if 'postcode' in cols:
                batch_op.drop_column('postcode')

