"""add_groups_and_permissions_tables

Revision ID: 706aed926175
Revises: e4b6c8d0f2a1
Create Date: 2026-10-06 09:56:58.062117

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '706aed926175'
down_revision = 'e4b6c8d0f2a1'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Maak 'groups' tabel aan indien deze nog niet bestaat
    op.create_table(
        'groups',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organisatie_id', sa.Integer(), nullable=False),
        sa.Column('naam', sa.String(length=100), nullable=False),
        sa.Column('beschrijving', sa.String(length=255), nullable=True),
        sa.Column('is_standaard', sa.Boolean(), server_default='0', nullable=False),
        sa.Column('alleen_eigen_registraties', sa.Boolean(), server_default='0', nullable=False),
        sa.Column('actief', sa.Boolean(), server_default='1', nullable=False),
        sa.Column('aangemaakt_op', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['organisatie_id'], ['organisaties.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organisatie_id', 'naam', name='uq_group_organisatie_naam')
    )
    with op.batch_alter_table('groups', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_groups_organisatie_id'), ['organisatie_id'], unique=False)

    # 2. Maak 'group_permissions' tabel aan
    op.create_table(
        'group_permissions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('groep_id', sa.Integer(), nullable=False),
        sa.Column('functionaliteit', sa.String(length=50), nullable=False),
        sa.Column('toegangsniveau', sa.String(length=20), server_default='geen', nullable=False),
        sa.ForeignKeyConstraint(['groep_id'], ['groups.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('groep_id', 'functionaliteit', name='uq_group_permission_feature')
    )
    with op.batch_alter_table('group_permissions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_group_permissions_groep_id'), ['groep_id'], unique=False)

    # 3. Maak 'user_groups' koppeltabel aan
    op.create_table(
        'user_groups',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('groep_id', sa.Integer(), nullable=False),
        sa.Column('toegekend_op', sa.DateTime(), nullable=False),
        sa.Column('toegekend_door_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['groep_id'], ['groups.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['toegekend_door_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'groep_id', name='uq_user_group')
    )
    with op.batch_alter_table('user_groups', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_user_groups_groep_id'), ['groep_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_user_groups_user_id'), ['user_id'], unique=False)


def downgrade():
    with op.batch_alter_table('user_groups', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_user_groups_user_id'))
        batch_op.drop_index(batch_op.f('ix_user_groups_groep_id'))
    op.drop_table('user_groups')

    with op.batch_alter_table('group_permissions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_group_permissions_groep_id'))
    op.drop_table('group_permissions')

    with op.batch_alter_table('groups', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_groups_organisatie_id'))
    op.drop_table('groups')
