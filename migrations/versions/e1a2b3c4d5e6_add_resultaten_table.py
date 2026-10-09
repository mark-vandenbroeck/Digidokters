"""add_resultaten_table

Revision ID: e1a2b3c4d5e6
Revises: af79234300a3
Create Date: 2026-10-09 17:15:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e1a2b3c4d5e6'
down_revision = 'af79234300a3'
branch_labels = None
depends_on = None


DEFAULT_RESULTATEN = [
    'Vraag beantwoord',
    'Bezoeker komt later terug',
    'Bezoeker doorverwezen',
    'Vraag onmogelijk te beantwoorden',
    'Andere'
]


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    if 'resultaten' not in tables:
        op.create_table(
            'resultaten',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('omschrijving', sa.String(length=100), nullable=False),
            sa.Column('organisatie_id', sa.Integer(), nullable=False),
            sa.Column('actief', sa.Boolean(), server_default=sa.sql.expression.true(), nullable=False),
            sa.Column('volgorde', sa.Integer(), server_default='0', nullable=False),
            sa.ForeignKeyConstraint(['organisatie_id'], ['organisaties.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('organisatie_id', 'omschrijving', name='uq_resultaten_organisatie_omschrijving')
        )
        with op.batch_alter_table('resultaten', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_resultaten_organisatie_id'), ['organisatie_id'], unique=False)

    # Check / add resultaat_id column to registrations
    reg_columns = [col['name'] for col in inspector.get_columns('registrations')]
    with op.batch_alter_table('registrations', schema=None) as batch_op:
        if 'resultaat_id' not in reg_columns:
            batch_op.add_column(sa.Column('resultaat_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key('fk_registrations_resultaat_id', 'resultaten', ['resultaat_id'], ['id'], ondelete='SET NULL')

    # Add indexes if missing
    reg_indexes = [idx['name'] for idx in inspector.get_indexes('registrations')]
    with op.batch_alter_table('registrations', schema=None) as batch_op:
        if 'ix_registrations_resultaat_id' not in reg_indexes:
            batch_op.create_index(batch_op.f('ix_registrations_resultaat_id'), ['resultaat_id'], unique=False)
        if 'ix_registrations_org_resultaat' not in reg_indexes:
            batch_op.create_index('ix_registrations_org_resultaat', ['organisatie_id', 'resultaat_id'], unique=False)

    # Seed default resultaten for all existing organisations
    if 'organisaties' in tables and 'resultaten' in tables:
        org_rows = conn.execute(sa.text("SELECT id FROM organisaties")).fetchall()
        for row in org_rows:
            org_id = row[0]
            for idx, omschrijving in enumerate(DEFAULT_RESULTATEN):
                existing = conn.execute(
                    sa.text("SELECT id FROM resultaten WHERE organisatie_id = :org_id AND omschrijving = :omschrijving"),
                    {'org_id': org_id, 'omschrijving': omschrijving}
                ).fetchone()
                if not existing:
                    conn.execute(
                        sa.text(
                            "INSERT INTO resultaten (organisatie_id, omschrijving, actief, volgorde) "
                            "VALUES (:org_id, :omschrijving, :actief, :volgorde)"
                        ),
                        {'org_id': org_id, 'omschrijving': omschrijving, 'actief': True, 'volgorde': idx}
                    )


def downgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    if 'registrations' in tables:
        reg_indexes = [idx['name'] for idx in inspector.get_indexes('registrations')]
        with op.batch_alter_table('registrations', schema=None) as batch_op:
            if 'ix_registrations_org_resultaat' in reg_indexes:
                batch_op.drop_index('ix_registrations_org_resultaat')
            if 'ix_registrations_resultaat_id' in reg_indexes:
                batch_op.drop_index(batch_op.f('ix_registrations_resultaat_id'))
            reg_columns = [col['name'] for col in inspector.get_columns('registrations')]
            if 'resultaat_id' in reg_columns:
                batch_op.drop_column('resultaat_id')

    if 'resultaten' in tables:
        with op.batch_alter_table('resultaten', schema=None) as batch_op:
            res_indexes = [idx['name'] for idx in inspector.get_indexes('resultaten')]
            if 'ix_resultaten_organisatie_id' in res_indexes:
                batch_op.drop_index(batch_op.f('ix_resultaten_organisatie_id'))
        op.drop_table('resultaten')
