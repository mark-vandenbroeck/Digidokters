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
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    existing_tables = inspector.get_table_names()

    # 0a. Ensure gender_identities table exists
    if 'gender_identities' not in existing_tables:
        op.create_table(
            'gender_identities',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('naam', sa.String(length=100), nullable=False),
            sa.Column('actief', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('volgorde', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('organisatie_id', sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(['organisatie_id'], ['organisaties.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('organisatie_id', 'naam', name='uq_gender_identity_org_naam')
        )
        # Seed standard Man / Vrouw per organisatie
        orgs = connection.execute(sa.text("SELECT id FROM organisaties")).fetchall()
        for org in orgs:
            connection.execute(
                sa.text("INSERT INTO gender_identities (organisatie_id, naam, actief, volgorde) VALUES (:org_id, 'Man', true, 0)"),
                {"org_id": org[0]}
            )
            connection.execute(
                sa.text("INSERT INTO gender_identities (organisatie_id, naam, actief, volgorde) VALUES (:org_id, 'Vrouw', true, 1)"),
                {"org_id": org[0]}
            )

    # 0b. Ensure functies and user_functies tables exist
    if 'functies' not in existing_tables:
        op.create_table(
            'functies',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('naam', sa.String(length=100), nullable=False),
            sa.Column('actief', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('volgorde', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('organisatie_id', sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(['organisatie_id'], ['organisaties.id']),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('organisatie_id', 'naam', name='uq_functie_org_naam')
        )
        orgs = connection.execute(sa.text("SELECT id FROM organisaties")).fetchall()
        for org in orgs:
            for i, name in enumerate(['Digidokter', 'Digihelper', 'Lesgever']):
                connection.execute(
                    sa.text("INSERT INTO functies (organisatie_id, naam, actief, volgorde) VALUES (:org_id, :naam, true, :volgorde)"),
                    {"org_id": org[0], "naam": name, "volgorde": i}
                )

    if 'user_functies' not in existing_tables:
        op.create_table(
            'user_functies',
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('functie_id', sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(['functie_id'], ['functies.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('user_id', 'functie_id')
        )

    # 0c. Ensure locatie_id column exists on registrations
    reg_cols = [c['name'] for c in inspector.get_columns('registrations')]
    if 'locatie_id' not in reg_cols:
        with op.batch_alter_table('registrations', schema=None) as batch_op:
            batch_op.add_column(sa.Column('locatie_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key('fk_registrations_locatie', 'locations', ['locatie_id'], ['id'])

    # 1. Add gender_identity_id column to registrations
    if 'gender_identity_id' not in reg_cols:
        with op.batch_alter_table('registrations', schema=None) as batch_op:
            batch_op.add_column(sa.Column('gender_identity_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key('fk_registrations_gender_identity', 'gender_identities', ['gender_identity_id'], ['id'], ondelete='SET NULL')
            batch_op.create_index('ix_registrations_org_gender', ['organisatie_id', 'gender_identity_id'])

    # 2. Data Migration: Populate gender_identity_id via case-insensitive matching per organization
    genders = connection.execute(
        sa.text("SELECT id, organisatie_id, naam FROM gender_identities")
    ).fetchall()

    gender_map = {(g[1], g[2].strip().lower()): g[0] for g in genders}

    # Fetch registrations that have a non-empty geslacht text value (if column exists)
    if 'geslacht' in reg_cols:
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
