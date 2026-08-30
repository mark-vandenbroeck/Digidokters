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
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('digidokters')]

    if 'user_id' not in columns:
        with op.batch_alter_table('digidokters', schema=None) as batch_op:
            batch_op.add_column(sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True))
            batch_op.create_index(batch_op.f('ix_digidokters_user_id'), ['user_id'], unique=False)
    else:
        indexes = [idx['name'] for idx in inspector.get_indexes('digidokters')]
        if 'ix_digidokters_user_id' not in indexes:
            try:
                op.create_index('ix_digidokters_user_id', 'digidokters', ['user_id'])
            except Exception:
                pass

    # Seeding / Data migratie: koppel digidokters zonder user_id aan gebruiker met dezelfde naam en ingevuld e-mailadres
    try:
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
    except Exception:
        pass


def downgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('digidokters')]
    if 'user_id' in columns:
        with op.batch_alter_table('digidokters', schema=None) as batch_op:
            try:
                batch_op.drop_index(batch_op.f('ix_digidokters_user_id'))
            except Exception:
                pass
            batch_op.drop_column('user_id')
