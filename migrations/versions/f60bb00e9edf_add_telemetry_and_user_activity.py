"""add_telemetry_and_user_activity

Revision ID: f60bb00e9edf
Revises: e1a2b3c4d5e6
Create Date: 2026-10-26 22:45:13.632565

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f60bb00e9edf'
down_revision = 'e1a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = insp.get_table_names()

    if 'page_view_stats' not in tables:
        op.create_table(
            'page_view_stats',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('datum', sa.Date(), nullable=False),
            sa.Column('endpoint', sa.String(length=100), nullable=False),
            sa.Column('pad', sa.String(length=255), nullable=True),
            sa.Column('label', sa.String(length=100), nullable=True),
            sa.Column('organisatie_id', sa.Integer(), nullable=True),
            sa.Column('aantal_hits', sa.Integer(), nullable=False, server_default='1'),
            sa.ForeignKeyConstraint(['organisatie_id'], ['organisaties.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('datum', 'endpoint', 'organisatie_id', name='uq_pageview_datum_endpoint_org')
        )
        op.create_index(op.f('ix_page_view_stats_datum'), 'page_view_stats', ['datum'], unique=False)
        op.create_index(op.f('ix_page_view_stats_endpoint'), 'page_view_stats', ['endpoint'], unique=False)
        op.create_index(op.f('ix_page_view_stats_organisatie_id'), 'page_view_stats', ['organisatie_id'], unique=False)

    if 'system_error_logs' not in tables:
        op.create_table(
            'system_error_logs',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('timestamp', sa.DateTime(), nullable=False),
            sa.Column('status_code', sa.Integer(), nullable=False, server_default='500'),
            sa.Column('type_fout', sa.String(length=100), nullable=True),
            sa.Column('bericht', sa.Text(), nullable=True),
            sa.Column('stacktrace', sa.Text(), nullable=True),
            sa.Column('endpoint', sa.String(length=100), nullable=True),
            sa.Column('pad', sa.String(length=255), nullable=True),
            sa.Column('methode', sa.String(length=10), nullable=True),
            sa.Column('ip_adres', sa.String(length=50), nullable=True),
            sa.Column('gebruiker', sa.String(length=100), nullable=True),
            sa.Column('organisatie_id', sa.Integer(), nullable=True),
            sa.Column('is_opgelost', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('opgelost_op', sa.DateTime(), nullable=True),
            sa.Column('opgelost_door', sa.String(length=100), nullable=True),
            sa.ForeignKeyConstraint(['organisatie_id'], ['organisaties.id'], ondelete='SET NULL'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_system_error_logs_timestamp'), 'system_error_logs', ['timestamp'], unique=False)
        op.create_index(op.f('ix_system_error_logs_status_code'), 'system_error_logs', ['status_code'], unique=False)
        op.create_index(op.f('ix_system_error_logs_is_opgelost'), 'system_error_logs', ['is_opgelost'], unique=False)
    else:
        err_cols = [c['name'] for c in insp.get_columns('system_error_logs')]
        with op.batch_alter_table('system_error_logs', schema=None) as batch_op:
            if 'is_opgelost' not in err_cols:
                batch_op.add_column(sa.Column('is_opgelost', sa.Boolean(), nullable=False, server_default='false'))
                batch_op.create_index(op.f('ix_system_error_logs_is_opgelost'), ['is_opgelost'], unique=False)
            if 'opgelost_op' not in err_cols:
                batch_op.add_column(sa.Column('opgelost_op', sa.DateTime(), nullable=True))
            if 'opgelost_door' not in err_cols:
                batch_op.add_column(sa.Column('opgelost_door', sa.String(length=100), nullable=True))

    user_cols = [c['name'] for c in insp.get_columns('users')]
    if 'laatste_activiteit' not in user_cols:
        with op.batch_alter_table('users', schema=None) as batch_op:
            batch_op.add_column(sa.Column('laatste_activiteit', sa.DateTime(), nullable=True))


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = insp.get_table_names()

    if 'system_error_logs' in tables:
        op.drop_table('system_error_logs')

    if 'page_view_stats' in tables:
        op.drop_table('page_view_stats')

    user_cols = [c['name'] for c in insp.get_columns('users')]
    if 'laatste_activiteit' in user_cols:
        with op.batch_alter_table('users', schema=None) as batch_op:
            batch_op.drop_column('laatste_activiteit')
