"""email optioneel voor gebruikers

Revision ID: c4d8e2f6a1b3
Revises: b7c3f1a9e2d4
Create Date: 2026-07-14 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c4d8e2f6a1b3'
down_revision = 'b7c3f1a9e2d4'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('email', existing_type=sa.String(length=150), nullable=True)


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('email', existing_type=sa.String(length=150), nullable=False)