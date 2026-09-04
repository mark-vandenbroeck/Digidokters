"""add email templates and reminder tracking

Revision ID: e8c9f1a2b345
Revises: f1a8c9e2b345
Create Date: 2026-09-04 20:50:00.000000

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime, timezone

# revision identifiers, used by Alembic.
revision = 'e8c9f1a2b345'
down_revision = '3d2524a3c6d4'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Maak email_templates tabel aan
    op.create_table(
        'email_templates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sleutel', sa.String(length=50), nullable=False),
        sa.Column('naam', sa.String(length=100), nullable=False),
        sa.Column('onderwerp', sa.String(length=200), nullable=False),
        sa.Column('inhoud', sa.Text(), nullable=False),
        sa.Column('beschrijving', sa.String(length=255), nullable=True),
        sa.Column('beschikbare_variabelen', sa.String(length=255), nullable=True),
        sa.Column('gewijzigd_op', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('email_templates', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_email_templates_sleutel'), ['sleutel'], unique=True)

    # 2. Voeg herinnering tracking toe aan evaluatie_uitnodigingen
    with op.batch_alter_table('evaluatie_uitnodigingen', schema=None) as batch_op:
        batch_op.add_column(sa.Column('herinnering_verzonden_op', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('herinnering_aantal', sa.Integer(), nullable=False, server_default='0'))

    # 3. Voeg initiële standaardsjablonen toe
    email_templates_table = sa.table(
        'email_templates',
        sa.column('sleutel', sa.String),
        sa.column('naam', sa.String),
        sa.column('onderwerp', sa.String),
        sa.column('inhoud', sa.Text),
        sa.column('beschrijving', sa.String),
        sa.column('beschikbare_variabelen', sa.String),
        sa.column('gewijzigd_op', sa.DateTime)
    )

    now_dt = datetime.now(timezone.utc)

    op.bulk_insert(
        email_templates_table,
        [
            {
                'sleutel': 'evaluatie_uitnodiging',
                'naam': 'Evaluatie - Uitnodiging',
                'onderwerp': 'Evaluatie: {activiteit} op {datum}',
                'inhoud': """Beste {naam},

Bedankt voor je inzet tijdens het {activiteit} op {datum} van {uur_van} tot {uur_tot} ({locatie})!{omschrijving_blok}

We horen graag hoe de sessie verlopen is. Zou je even de tijd willen nemen om het korte evaluatieformulier in te vullen? Dit helpt ons om de sessies continu te verbeteren.

👉 Klik op onderstaande link om het formulier in te vullen:
{link}

Alvast hartelijk dank voor je feedback en medewerking!

Met vriendelijke groet,
Digidokters Team
""",
                'beschrijving': 'E-mailuitnodiging die na afloop van een sessie verstuurd wordt naar aanwezige digidokters.',
                'beschikbare_variabelen': '{naam}, {activiteit}, {datum}, {uur_van}, {uur_tot}, {locatie}, {omschrijving_blok}, {link}',
                'gewijzigd_op': now_dt
            },
            {
                'sleutel': 'evaluatie_herinnering',
                'naam': 'Evaluatie - Herinnering',
                'onderwerp': 'Herinnering: Evaluatie voor {activiteit} op {datum}',
                'inhoud': """Beste {naam},

Dit is een vriendelijke herinnering om het evaluatieformulier in te vullen voor het {activiteit} op {datum} van {uur_van} tot {uur_tot} ({locatie}).{omschrijving_blok}

We hebben je feedback nog niet ontvangen. Jouw ervaringen als vrijwilliger zijn voor ons erg waardevol om de werking van Digidokters te versterken.

👉 Klik op onderstaande link om het formulier alsnog in te vullen:
{link}

Hartelijk dank voor je tijd en toewijding!

Met vriendelijke groet,
Digidokters Team
""",
                'beschrijving': 'Herinneringsmail voor digidokters die de evaluatie na afloop nog niet hebben ingevuld.',
                'beschikbare_variabelen': '{naam}, {activiteit}, {datum}, {uur_van}, {uur_tot}, {locatie}, {omschrijving_blok}, {link}',
                'gewijzigd_op': now_dt
            }
        ]
    )


def downgrade():
    with op.batch_alter_table('evaluatie_uitnodigingen', schema=None) as batch_op:
        batch_op.drop_column('herinnering_aantal')
        batch_op.drop_column('herinnering_verzonden_op')

    with op.batch_alter_table('email_templates', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_email_templates_sleutel'))

    op.drop_table('email_templates')
