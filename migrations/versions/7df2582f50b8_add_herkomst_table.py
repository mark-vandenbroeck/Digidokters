"""add herkomst table

Revision ID: 7df2582f50b8
Revises: 3c49eab9a595
Create Date: 2026-07-25 20:29:09.280120

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7df2582f50b8'
down_revision = '3c49eab9a595'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Create table herkomst
    op.create_table('herkomst',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('naam', sa.String(length=100), nullable=False),
    sa.Column('actief', sa.Boolean(), nullable=False, server_default='1'),
    sa.Column('volgorde', sa.Integer(), nullable=False, server_default='0'),
    sa.Column('organisatie_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['organisatie_id'], ['organisaties.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organisatie_id', 'naam', name='uq_herkomst_org_naam')
    )

    # 2. Add herkomst_id to registrations
    with op.batch_alter_table('registrations', schema=None) as batch_op:
        batch_op.add_column(sa.Column('herkomst_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_registrations_herkomst', 'herkomst', ['herkomst_id'], ['id'])

    # 3. Data Migration: Extract distinct values from herkomst column
    connection = op.get_bind()
    results = connection.execute(
        sa.text("SELECT distinct organisatie_id, herkomst FROM registrations WHERE herkomst IS NOT NULL AND herkomst != '' AND herkomst != 'nan'")
    ).fetchall()

    inserted = set()
    volgordes = {}
    for row in results:
        org_id = row[0]
        orig_herkomst = row[1]
        if not orig_herkomst:
            continue
        naam = orig_herkomst.strip()
        if naam.lower() == 'nan' or not naam:
            continue
        key = (org_id, naam.lower())
        if key not in inserted:
            inserted.add(key)
            volgorde = volgordes.get(org_id, 0)
            volgordes[org_id] = volgorde + 1
            connection.execute(
                sa.text("INSERT INTO herkomst (organisatie_id, naam, actief, volgorde) VALUES (:org_id, :naam, :actief, :volgorde)"),
                {"org_id": org_id, "naam": naam, "actief": 1, "volgorde": volgorde}
            )

    # 4. Data Migration: Populate herkomst_id on registrations
    herkomsten = connection.execute(
        sa.text("SELECT id, organisatie_id, naam FROM herkomst")
    ).fetchall()
    
    mapping = {(h[1], h[2].lower().strip()): h[0] for h in herkomsten}

    regs = connection.execute(
        sa.text("SELECT id, organisatie_id, herkomst FROM registrations WHERE herkomst IS NOT NULL AND herkomst != '' AND herkomst != 'nan'")
    ).fetchall()

    for r in regs:
        reg_id = r[0]
        org_id = r[1]
        herkomst_str = r[2].strip()
        h_id = mapping.get((org_id, herkomst_str.lower()))
        if h_id:
            connection.execute(
                sa.text("UPDATE registrations SET herkomst_id = :h_id WHERE id = :reg_id"),
                {"h_id": h_id, "reg_id": reg_id}
            )

    # 5. Drop the old herkomst string column
    with op.batch_alter_table('registrations', schema=None) as batch_op:
        batch_op.drop_column('herkomst')


def downgrade():
    # 1. Re-add herkomst string column to registrations
    with op.batch_alter_table('registrations', schema=None) as batch_op:
        batch_op.add_column(sa.Column('herkomst', sa.String(length=200), nullable=True))

    # 2. Populate old herkomst column with names from herkomst table
    connection = op.get_bind()
    try:
        herkomsten = connection.execute(
            sa.text("SELECT id, naam FROM herkomst")
        ).fetchall()
        mapping = {h[0]: h[1] for h in herkomsten}

        regs = connection.execute(
            sa.text("SELECT id, herkomst_id FROM registrations WHERE herkomst_id IS NOT NULL")
        ).fetchall()

        for r in regs:
            reg_id = r[0]
            h_id = r[1]
            h_name = mapping.get(h_id)
            if h_name:
                connection.execute(
                    sa.text("UPDATE registrations SET herkomst = :h_name WHERE id = :reg_id"),
                    {"h_name": h_name, "reg_id": reg_id}
                )
    except Exception:
        pass

    # 3. Drop constraint and herkomst_id column, drop herkomst table
    with op.batch_alter_table('registrations', schema=None) as batch_op:
        batch_op.drop_constraint('fk_registrations_herkomst', type_='foreignkey')
        batch_op.drop_column('herkomst_id')

    op.drop_table('herkomst')
