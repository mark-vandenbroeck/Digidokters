"""add sjabloon organisatie

Revision ID: f1a8c9e2b345
Revises: 8279b19fe421
Create Date: 2026-09-01 08:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime

# revision identifiers, used by Alembic.
revision = 'f1a8c9e2b345'
down_revision = '8279b19fe421'
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    now_dt = datetime.utcnow()

    orgs_table = sa.table(
        'organisaties',
        sa.column('id', sa.Integer),
        sa.column('naam', sa.String),
        sa.column('slug', sa.String),
        sa.column('actief', sa.Boolean),
        sa.column('aangemaakt_op', sa.DateTime)
    )

    age_cat_table = sa.table(
        'age_categories',
        sa.column('id', sa.Integer),
        sa.column('naam', sa.String),
        sa.column('actief', sa.Boolean),
        sa.column('volgorde', sa.Integer),
        sa.column('organisatie_id', sa.Integer)
    )

    device_table = sa.table(
        'devices',
        sa.column('id', sa.Integer),
        sa.column('naam', sa.String),
        sa.column('actief', sa.Boolean),
        sa.column('volgorde', sa.Integer),
        sa.column('organisatie_id', sa.Integer)
    )

    act_type_table = sa.table(
        'activity_types',
        sa.column('id', sa.Integer),
        sa.column('naam', sa.String),
        sa.column('actief', sa.Boolean),
        sa.column('kleur', sa.String),
        sa.column('heeft_evaluatie', sa.Boolean),
        sa.column('volgorde', sa.Integer),
        sa.column('organisatie_id', sa.Integer)
    )

    location_table = sa.table(
        'locations',
        sa.column('id', sa.Integer),
        sa.column('naam', sa.String),
        sa.column('actief', sa.Boolean),
        sa.column('volgorde', sa.Integer),
        sa.column('organisatie_id', sa.Integer)
    )

    herkomst_table = sa.table(
        'herkomst',
        sa.column('id', sa.Integer),
        sa.column('naam', sa.String),
        sa.column('actief', sa.Boolean),
        sa.column('volgorde', sa.Integer),
        sa.column('organisatie_id', sa.Integer)
    )

    eval_forms_table = sa.table(
        'evaluatie_formulieren',
        sa.column('id', sa.Integer),
        sa.column('organisatie_id', sa.Integer),
        sa.column('activity_type_id', sa.Integer),
        sa.column('titel', sa.String),
        sa.column('toelichting', sa.Text),
        sa.column('actief', sa.Boolean),
        sa.column('aangemaakt_op', sa.DateTime),
        sa.column('gewijzigd_op', sa.DateTime)
    )

    eval_vragen_table = sa.table(
        'evaluatie_vragen',
        sa.column('id', sa.Integer),
        sa.column('form_id', sa.Integer),
        sa.column('vraag_tekst', sa.Text),
        sa.column('type', sa.String),
        sa.column('opties', sa.JSON),
        sa.column('volgorde', sa.Integer),
        sa.column('verplicht', sa.Boolean)
    )

    # 1. Check of Sjabloon al bestaat
    existing_sjabloon = connection.execute(
        sa.select(orgs_table.c.id).where(orgs_table.c.slug == 'sjabloon')
    ).fetchone()

    if not existing_sjabloon:
        # Maak Sjabloon organisatie aan
        connection.execute(
            orgs_table.insert().values(
                naam='Sjabloon',
                slug='sjabloon',
                actief=True,
                aangemaakt_op=now_dt
            )
        )
        sjabloon_row = connection.execute(
            sa.select(orgs_table.c.id).where(orgs_table.c.slug == 'sjabloon')
        ).fetchone()
        sjabloon_id = sjabloon_row[0]

        # 2. Kopieer actieve Leeftijdscategorieën van org 1
        active_cats = connection.execute(
            sa.select(age_cat_table.c.naam, age_cat_table.c.volgorde)
            .where(age_cat_table.c.organisatie_id == 1, age_cat_table.c.actief == True)
            .order_by(age_cat_table.c.volgorde)
        ).fetchall()
        for i, row in enumerate(active_cats):
            connection.execute(
                age_cat_table.insert().values(
                    naam=row[0],
                    actief=True,
                    volgorde=i,
                    organisatie_id=sjabloon_id
                )
            )

        # 3. Kopieer actieve Toestellen van org 1
        active_devs = connection.execute(
            sa.select(device_table.c.naam, device_table.c.volgorde)
            .where(device_table.c.organisatie_id == 1, device_table.c.actief == True)
            .order_by(device_table.c.volgorde)
        ).fetchall()
        for i, row in enumerate(active_devs):
            connection.execute(
                device_table.insert().values(
                    naam=row[0],
                    actief=True,
                    volgorde=i,
                    organisatie_id=sjabloon_id
                )
            )

        # 4. Kopieer actieve Activiteitstypes van org 1 (en hun evaluatieformulieren/vragen)
        active_types = connection.execute(
            sa.select(act_type_table.c.id, act_type_table.c.naam, act_type_table.c.kleur, act_type_table.c.heeft_evaluatie, act_type_table.c.volgorde)
            .where(act_type_table.c.organisatie_id == 1, act_type_table.c.actief == True)
            .order_by(act_type_table.c.volgorde)
        ).fetchall()
        for i, row in enumerate(active_types):
            old_at_id = row[0]
            at_naam = row[1]
            at_kleur = row[2]
            heeft_eval = row[3]

            connection.execute(
                act_type_table.insert().values(
                    naam=at_naam,
                    actief=True,
                    kleur=at_kleur,
                    heeft_evaluatie=heeft_eval,
                    volgorde=i,
                    organisatie_id=sjabloon_id
                )
            )
            new_at_row = connection.execute(
                sa.select(act_type_table.c.id)
                .where(act_type_table.c.organisatie_id == sjabloon_id, act_type_table.c.naam == at_naam)
            ).fetchone()
            new_at_id = new_at_row[0]

            # Als dit type een evaluatieformulier heeft in org 1, kopieer het formulier en alle vragen
            if heeft_eval:
                source_form = connection.execute(
                    sa.select(eval_forms_table.c.id, eval_forms_table.c.titel, eval_forms_table.c.toelichting)
                    .where(eval_forms_table.c.activity_type_id == old_at_id, eval_forms_table.c.organisatie_id == 1)
                ).fetchone()

                titel = source_form[1] if source_form else f"Evaluatie {at_naam}"
                toelichting = source_form[2] if source_form else f"Vul na afloop van het {at_naam} deze korte evaluatie in."

                connection.execute(
                    eval_forms_table.insert().values(
                        organisatie_id=sjabloon_id,
                        activity_type_id=new_at_id,
                        titel=titel,
                        toelichting=toelichting,
                        actief=True,
                        aangemaakt_op=now_dt,
                        gewijzigd_op=now_dt
                    )
                )
                new_form_row = connection.execute(
                    sa.select(eval_forms_table.c.id)
                    .where(eval_forms_table.c.activity_type_id == new_at_id, eval_forms_table.c.organisatie_id == sjabloon_id)
                ).fetchone()
                new_form_id = new_form_row[0]

                if source_form:
                    source_vragen = connection.execute(
                        sa.select(eval_vragen_table.c.vraag_tekst, eval_vragen_table.c.type, eval_vragen_table.c.opties, eval_vragen_table.c.volgorde, eval_vragen_table.c.verplicht)
                        .where(eval_vragen_table.c.form_id == source_form[0])
                        .order_by(eval_vragen_table.c.volgorde)
                    ).fetchall()
                    for v in source_vragen:
                        connection.execute(
                            eval_vragen_table.insert().values(
                                form_id=new_form_id,
                                vraag_tekst=v[0],
                                type=v[1],
                                opties=v[2],
                                volgorde=v[3],
                                verplicht=v[4]
                            )
                        )

        # 5. Kopieer actieve Locaties van org 1
        active_locs = connection.execute(
            sa.select(location_table.c.naam, location_table.c.volgorde)
            .where(location_table.c.organisatie_id == 1, location_table.c.actief == True)
            .order_by(location_table.c.volgorde)
        ).fetchall()
        for i, row in enumerate(active_locs):
            connection.execute(
                location_table.insert().values(
                    naam=row[0],
                    actief=True,
                    volgorde=i,
                    organisatie_id=sjabloon_id
                )
            )

        # 6. Kopieer actieve Herkomsten van org 1
        active_herkomsten = connection.execute(
            sa.select(herkomst_table.c.naam, herkomst_table.c.volgorde)
            .where(herkomst_table.c.organisatie_id == 1, herkomst_table.c.actief == True)
            .order_by(herkomst_table.c.volgorde)
        ).fetchall()
        for i, row in enumerate(active_herkomsten):
            connection.execute(
                herkomst_table.insert().values(
                    naam=row[0],
                    actief=True,
                    volgorde=i,
                    organisatie_id=sjabloon_id
                )
            )


def downgrade():
    connection = op.get_bind()
    # Verwijder sjabloon indien nodig
    sjabloon = connection.execute(
        sa.text("SELECT id FROM organisaties WHERE slug = 'sjabloon'")
    ).fetchone()
    if sjabloon:
        s_id = sjabloon[0]
        connection.execute(sa.text(f"DELETE FROM evaluatie_vragen WHERE form_id IN (SELECT id FROM evaluatie_formulieren WHERE organisatie_id = {s_id})"))
        connection.execute(sa.text(f"DELETE FROM evaluatie_formulieren WHERE organisatie_id = {s_id}"))
        connection.execute(sa.text(f"DELETE FROM age_categories WHERE organisatie_id = {s_id}"))
        connection.execute(sa.text(f"DELETE FROM devices WHERE organisatie_id = {s_id}"))
        connection.execute(sa.text(f"DELETE FROM activity_types WHERE organisatie_id = {s_id}"))
        connection.execute(sa.text(f"DELETE FROM locations WHERE organisatie_id = {s_id}"))
        connection.execute(sa.text(f"DELETE FROM herkomst WHERE organisatie_id = {s_id}"))
        connection.execute(sa.text(f"DELETE FROM organisaties WHERE id = {s_id}"))
