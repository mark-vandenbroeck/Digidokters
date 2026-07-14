"""naam uniek (login) + onderwerp als Text

Revision ID: b7c3f1a9e2d4
Revises: 850e8dfeb533
Create Date: 2026-07-14 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b7c3f1a9e2d4'
down_revision = '850e8dfeb533'
branch_labels = None
depends_on = None


def upgrade():
    # ── users.naam wordt gebruikt om in te loggen, dus moet uniek zijn ──
    # batch_alter_table werkt zowel op SQLite (lokaal, via kopieer-strategie)
    # als op Postgres (Render/Supabase, directe ALTER TABLE).
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.create_unique_constraint('uq_users_naam', ['naam'])

    # ── registrations.onderwerp: VARCHAR(500) -> TEXT ──────────────────
    with op.batch_alter_table('registrations', schema=None) as batch_op:
        batch_op.alter_column('onderwerp',
                               existing_type=sa.String(length=500),
                               type_=sa.Text(),
                               existing_nullable=False)


def downgrade():
    with op.batch_alter_table('registrations', schema=None) as batch_op:
        batch_op.alter_column('onderwerp',
                               existing_type=sa.Text(),
                               type_=sa.String(length=500),
                               existing_nullable=False)

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_constraint('uq_users_naam', type_='unique')