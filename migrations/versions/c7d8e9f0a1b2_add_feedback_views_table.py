"""add feedback_views table

Revision ID: c7d8e9f0a1b2
Revises: bb850f7f1354
Create Date: 2026-09-12 14:26:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c7d8e9f0a1b2'
down_revision = 'bb850f7f1354'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'feedback_views',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('feedback_id', sa.Integer(), nullable=True),
        sa.Column('bekeken_op', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['feedback_id'], ['feedback_items.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'feedback_id', name='uq_user_feedback_view')
    )
    with op.batch_alter_table('feedback_views', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_feedback_views_feedback_id'), ['feedback_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_feedback_views_user_id'), ['user_id'], unique=False)


def downgrade():
    with op.batch_alter_table('feedback_views', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_feedback_views_user_id'))
        batch_op.drop_index(batch_op.f('ix_feedback_views_feedback_id'))
    op.drop_table('feedback_views')
