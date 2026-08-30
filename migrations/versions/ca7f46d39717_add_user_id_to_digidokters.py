"""add user_id to digidokters

Revision ID: ca7f46d39717
Revises: af67403ee61e
Create Date: 2026-08-24 21:54:14.785377

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ca7f46d39717'
down_revision = 'af67403ee61e'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE digidokters ADD COLUMN user_id INTEGER REFERENCES users(id)")
    try:
        op.create_index('ix_digidokters_user_id', 'digidokters', ['user_id'])
    except Exception:
        pass

    # Seeding / Data migratie: koppel digidokters zonder user_id aan gebruiker met dezelfde naam en ingevuld e-mailadres
    op.execute("""
        UPDATE digidokters
        SET user_id = (
            SELECT u.id FROM users u
            WHERE LOWER(u.naam) = LOWER(digidokters.naam)
            AND u.email IS NOT NULL AND u.email != ''
            LIMIT 1
        )
        WHERE user_id IS NULL
    """)


def downgrade():
    try:
        op.drop_index('ix_digidokters_user_id', table_name='digidokters')
    except Exception:
        pass
