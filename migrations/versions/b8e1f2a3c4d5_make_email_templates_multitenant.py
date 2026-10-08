"""make email templates multitenant

Revision ID: b8e1f2a3c4d5
Revises: 706aed926175
Create Date: 2026-10-08 15:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime, timezone

# revision identifiers, used by Alembic.
revision = 'b8e1f2a3c4d5'
down_revision = '706aed926175'
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    now_dt = datetime.now(timezone.utc)

    # 1. Alter email_templates table
    with op.batch_alter_table('email_templates', schema=None) as batch_op:
        batch_op.add_column(sa.Column('organisatie_id', sa.Integer(), nullable=True))
        try:
            batch_op.drop_index('ix_email_templates_sleutel')
        except Exception:
            pass
        batch_op.create_index(batch_op.f('ix_email_templates_organisatie_id'), ['organisatie_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_email_templates_sleutel'), ['sleutel'], unique=False)
        batch_op.create_foreign_key(
            'fk_email_templates_organisatie_id',
            'organisaties',
            ['organisatie_id'],
            ['id'],
            ondelete='CASCADE'
        )
        batch_op.create_unique_constraint('uq_email_template_org_sleutel', ['organisatie_id', 'sleutel'])

    # 2. Voeg welkomstmail toe aan globale sjablonen indien ontbrekend
    email_templates_table = sa.table(
        'email_templates',
        sa.column('id', sa.Integer),
        sa.column('organisatie_id', sa.Integer),
        sa.column('sleutel', sa.String),
        sa.column('naam', sa.String),
        sa.column('onderwerp', sa.String),
        sa.column('inhoud', sa.Text),
        sa.column('beschrijving', sa.String),
        sa.column('beschikbare_variabelen', sa.String),
        sa.column('gewijzigd_op', sa.DateTime)
    )

    welkom_inhoud = """Beste {naam},

Welkom bij de Digidokters-applicatie!

Er is een nieuw account voor jou aangemaakt. Je kunt de applicatie bereiken via onderstaande URL:
{login_url}

Je inloggegevens:
E-mailadres: {email}
{wachtwoord_blok}
Als bijlage sturen we je alvast de gebruikershandleiding mee. Hierin vind je een duidelijke uitleg over het gebruik van de applicatie (zoals het registreren van bezoeken, de agenda en documentbeheer).

Mocht je vragen of problemen hebben, neem dan gerust contact op met de beheerder via {contact_email}.

Met vriendelijke groet,
Digidokters Team
"""

    existing_global_welkom = connection.execute(
        sa.select(email_templates_table.c.id).where(
            email_templates_table.c.organisatie_id.is_(None),
            email_templates_table.c.sleutel == 'welkomstmail'
        )
    ).fetchone()

    if not existing_global_welkom:
        connection.execute(
            email_templates_table.insert().values(
                organisatie_id=None,
                sleutel='welkomstmail',
                naam='Welkomstmail nieuwe gebruiker',
                onderwerp='Welkom bij Digidokters!',
                inhoud=welkom_inhoud,
                beschrijving='Welkomstmail die verzonden wordt naar een nieuw aangemaakte gebruiker met inloginstructies en handleiding.',
                beschikbare_variabelen='{naam}, {email}, {login_url}, {wachtwoord_blok}, {contact_email}',
                gewijzigd_op=now_dt
            )
        )


def downgrade():
    with op.batch_alter_table('email_templates', schema=None) as batch_op:
        batch_op.drop_constraint('uq_email_template_org_sleutel', type_='unique')
        batch_op.drop_constraint('fk_email_templates_organisatie_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_email_templates_organisatie_id'))
        batch_op.drop_index(batch_op.f('ix_email_templates_sleutel'))
        batch_op.create_index('ix_email_templates_sleutel', ['sleutel'], unique=True)
        batch_op.drop_column('organisatie_id')
