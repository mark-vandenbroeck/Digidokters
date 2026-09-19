"""Replace geslacht text column with gender_identity_id foreign key

Revision ID: e4b6c8d0f2a1
Revises: f1a8c9e2b345
Create Date: 2026-09-19 21:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e4b6c8d0f2a1'
down_revision = 'd8e9f0a1b2c3'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Add gender_identity_id column to registrations
    with op.batch_alter_table('registrations', schema=None) as batch_op:
        batch_op.add_column(sa.Column('gender_identity_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_registrations_gender_identity', 'gender_identities', ['gender_identity_id'], ['id'], ondelete='SET NULL')
        batch_op.create_index('ix_registrations_org_gender', ['organisatie_id', 'gender_identity_id'])

    # 2. Data Migration: Populate gender_identity_id via case-insensitive matching per organization
    connection = op.get_bind()
    genders = connection.execute(
        sa.text("SELECT id, organisatie_id, naam FROM gender_identities")
    ).fetchall()

    gender_map = {(g[1], g[2].strip().lower()): g[0] for g in genders}

    # Fetch registrations that have a non-empty geslacht text value
    try:
        regs = connection.execute(
            sa.text("SELECT id, organisatie_id, geslacht FROM registrations WHERE geslacht IS NOT NULL AND TRIM(geslacht) != '' AND TRIM(LOWER(geslacht)) NOT IN ('nan', 'none', 'null')")
        ).fetchall()

        for r in regs:
            reg_id = r[0]
            org_id = r[1]
            geslacht_str = str(r[2]).strip().lower()
            gid = gender_map.get((org_id, geslacht_str))
            if gid:
                connection.execute(
                    sa.text("UPDATE registrations SET gender_identity_id = :gid WHERE id = :reg_id"),
                    {"gid": gid, "reg_id": reg_id}
                )
    except Exception as e:
        print(f"Waarschuwing tijdens datamigratie: {e}")

    # 3. Drop the old geslacht column
    with op.batch_alter_table('registrations', schema=None) as batch_op:
        batch_op.drop_column('geslacht')


def downgrade():
    # 1. Re-add geslacht text column
    with op.batch_alter_table('registrations', schema=None) as batch_op:
        batch_op.add_column(sa.Column('geslacht', sa.String(length=10), nullable=True))

    # 2. Populate geslacht from gender_identities
    connection = op.get_bind()
    try:
        genders = connection.execute(
            sa.text("SELECT id, naam FROM gender_identities")
        ).fetchall()
        gender_id_to_name = {g[0]: g[1] for g in genders}

        regs = connection.execute(
            sa.text("SELECT id, gender_identity_id FROM registrations WHERE gender_identity_id IS NOT NULL")
        ).fetchall()

        for r in regs:
            reg_id = r[0]
            gid = r[1]
            naam = gender_id_to_name.get(gid)
            if naam:
                connection.execute(
                    sa.text("UPDATE registrations SET geslacht = :naam WHERE id = :reg_id"),
                    {"naam": naam, "reg_id": reg_id}
                )
    except Exception as e:
        print(f"Waarschuwing tijdens downgrade datamigratie: {e}")

    # 3. Drop gender_identity_id column and index
    with op.batch_alter_table('registrations', schema=None) as batch_op:
        batch_op.drop_index('ix_registrations_org_gender')
        batch_op.drop_column('gender_identity_id')
