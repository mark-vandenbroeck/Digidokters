"""add_communicatie_logs_table

Revision ID: af79234300a3
Revises: b8e1f2a3c4d5
Create Date: 2026-10-08 16:16:05.357486

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'af79234300a3'
down_revision = 'b8e1f2a3c4d5'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'communicatie_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organisatie_id', sa.Integer(), nullable=True),
        sa.Column('afzender_id', sa.Integer(), nullable=True),
        sa.Column('afzender_naam', sa.String(length=150), nullable=False),
        sa.Column('afzender_email', sa.String(length=150), nullable=False),
        sa.Column('type', sa.String(length=50), server_default='organisatie', nullable=False),
        sa.Column('doelgroep', sa.String(length=100), nullable=True),
        sa.Column('onderwerp', sa.String(length=255), nullable=False),
        sa.Column('inhoud', sa.Text(), nullable=False),
        sa.Column('ontvangers_json', sa.Text(), nullable=False),
        sa.Column('aantal_ontvangers', sa.Integer(), server_default='0', nullable=False),
        sa.Column('status', sa.String(length=50), server_default='verzonden', nullable=False),
        sa.Column('verzonden_op', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['afzender_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['organisatie_id'], ['organisaties.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('communicatie_logs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_communicatie_logs_afzender_id'), ['afzender_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_communicatie_logs_organisatie_id'), ['organisatie_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_communicatie_logs_verzonden_op'), ['verzonden_op'], unique=False)


def downgrade():
    with op.batch_alter_table('communicatie_logs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_communicatie_logs_verzonden_op'))
        batch_op.drop_index(batch_op.f('ix_communicatie_logs_organisatie_id'))
        batch_op.drop_index(batch_op.f('ix_communicatie_logs_afzender_id'))
    op.drop_table('communicatie_logs')
