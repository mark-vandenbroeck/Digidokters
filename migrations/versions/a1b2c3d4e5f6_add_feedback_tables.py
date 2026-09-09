"""add feedback tables

Revision ID: a1b2c3d4e5f6
Revises: e8c9f1a2b345
Create Date: 2026-09-09 08:17:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'e8c9f1a2b345'
branch_labels = None
depends_on = None


def upgrade():
    # 1. feedback_items tabel
    op.create_table(
        'feedback_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organisatie_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('type', sa.String(length=30), nullable=False, server_default='voorstel'),
        sa.Column('onderwerp', sa.String(length=200), nullable=False),
        sa.Column('beschrijving', sa.Text(), nullable=False),
        sa.Column('screenshot_naam', sa.String(length=255), nullable=True),
        sa.Column('screenshot_mime', sa.String(length=100), nullable=True),
        sa.Column('screenshot_data', sa.LargeBinary(), nullable=True),
        sa.Column('is_afgesloten', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('afgesloten_op', sa.DateTime(), nullable=True),
        sa.Column('afgesloten_door_id', sa.Integer(), nullable=True),
        sa.Column('aangemaakt_op', sa.DateTime(), nullable=False),
        sa.Column('gewijzigd_op', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['afgesloten_door_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['organisatie_id'], ['organisaties.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('feedback_items', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_feedback_items_aangemaakt_op'), ['aangemaakt_op'], unique=False)
        batch_op.create_index(batch_op.f('ix_feedback_items_is_afgesloten'), ['is_afgesloten'], unique=False)
        batch_op.create_index(batch_op.f('ix_feedback_items_organisatie_id'), ['organisatie_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_feedback_items_user_id'), ['user_id'], unique=False)

    # 2. feedback_stemmen tabel
    op.create_table(
        'feedback_stemmen',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('feedback_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('stem', sa.SmallInteger(), nullable=False),
        sa.Column('aangemaakt_op', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['feedback_id'], ['feedback_items.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('feedback_id', 'user_id', name='uq_feedback_user_stem')
    )
    with op.batch_alter_table('feedback_stemmen', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_feedback_stemmen_feedback_id'), ['feedback_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_feedback_stemmen_user_id'), ['user_id'], unique=False)

    # 3. feedback_reacties tabel
    op.create_table(
        'feedback_reacties',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('feedback_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('tekst', sa.Text(), nullable=False),
        sa.Column('aangemaakt_op', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['feedback_id'], ['feedback_items.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('feedback_reacties', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_feedback_reacties_feedback_id'), ['feedback_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_feedback_reacties_user_id'), ['user_id'], unique=False)


def downgrade():
    op.drop_table('feedback_reacties')
    op.drop_table('feedback_stemmen')
    op.drop_table('feedback_items')
