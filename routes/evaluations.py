from datetime import datetime, date, time, timedelta
import json
import secrets
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, current_app
from flask_login import login_required, current_user
from extensions import db
from models.activity_type import ActivityType
from models.agenda import AgendaItem
from models.digidokter import Digidokter
from models.evaluation import EvaluationForm, EvaluationQuestion, EvaluationResponse, EvaluationInvitation
from models.email_template import EmailTemplate
from models.user import User
from utils.decorators import admin_required, writer_required
from utils.mail import verstuur_email
from utils.tenant import get_huidige_organisatie_id, filter_op_organisatie

eval_bp = Blueprint('eval', __name__)


# ═══════════════════════════════════════════════════════════════
# HELPER FUNCTIES VOOR EVALUATIES & E-MAIL
# ═══════════════════════════════════════════════════════════════

def get_or_create_evaluation_form(activity_type_id, org_id):
    """Haalt het evaluatieformulier op voor een activiteitstype of maakt een standaard formulier aan."""
    form = EvaluationForm.query.filter_by(activity_type_id=activity_type_id, organisatie_id=org_id).first()
    if not form:
        act_type = db.session.get(ActivityType, activity_type_id)
        titel = f"Evaluatie {act_type.naam}" if act_type else "Evaluatieformulier"
        form = EvaluationForm(
            organisatie_id=org_id,
            activity_type_id=activity_type_id,
            titel=titel,
            toelichting=f"Vul na afloop van het {act_type.naam if act_type else 'evenement'} deze korte evaluatie in.",
            actief=True
        )
        db.session.add(form)
        db.session.flush()

        # Voeg standaard voorbeeldvragen toe als het om een Digicafé of nieuwe form gaat
        standaard_vragen = [
            {
                'vraag_tekst': 'Hebben de deelnemers iets geleerd vandaag?',
                'type': 'multiple_choice',
                'opties': ['Niet veel', 'Een beetje', 'Redelijk wat', 'Veel', 'Heel veel'],
                'volgorde': 1,
                'verplicht': True
            },
            {
                'vraag_tekst': 'Zou je dit Digicafé ook aan andere klanten van de Digidokters aanraden?',
                'type': 'multiple_choice',
                'opties': ['Ja', 'Ik twijfel', 'Nee'],
                'volgorde': 2,
                'verplicht': True
            },
            {
                'vraag_tekst': 'Was het Digicafé goed opgebouwd en duidelijk?',
                'type': 'multiple_choice',
                'opties': ['Zeer goed', 'Goed', 'Matig', 'Slecht'],
                'volgorde': 3,
                'verplicht': True
            },
            {
                'vraag_tekst': 'Was het lesmateriaal (zoals presentaties of oefeningen) nuttig en begrijpelijk?',
                'type': 'multiple_choice',
                'opties': ['Zeer goed', 'Goed', 'Matig', 'Slecht'],
                'volgorde': 4,
                'verplicht': True
            },
            {
                'vraag_tekst': 'Hoe nuttig vond je deze les voor de digitale vaardigheden van de deelnemers?',
                'type': 'multiple_choice',
                'opties': ['Zeer goed', 'Goed', 'Matig', 'Slecht'],
                'volgorde': 5,
                'verplicht': True
            },
            {
                'vraag_tekst': 'Was het onderwerp en de inhoud voor hen interessant en makkelijk te begrijpen?',
                'type': 'multiple_choice',
                'opties': ['Teveel informatie (te breed)', 'Perfect zo', 'Te weinig informatie'],
                'volgorde': 6,
                'verplicht': True
            },
            {
                'vraag_tekst': 'Hoe vond je de verhouding tussen het theoretische gedeelte en de oefeningen?',
                'type': 'multiple_choice',
                'opties': ['Teveel theorie', 'Perfect zo', 'Teveel oefeningen'],
                'volgorde': 7,
                'verplicht': True
            },
            {
                'vraag_tekst': 'Was er voldoende ruimte voor interactie tussen de groep en met de docent?',
                'type': 'multiple_choice',
                'opties': ['Te weinig interactie', 'Perfect zo', 'Teveel interactie'],
                'volgorde': 8,
                'verplicht': True
            },
            {
                'vraag_tekst': 'Was het tempo van de docent goed afgestemd op het leertempo van de (meeste) deelnemers?',
                'type': 'multiple_choice',
                'opties': ['Te snel', 'Perfect zo', 'Te traag'],
                'volgorde': 9,
                'verplicht': True
            },
            {
                'vraag_tekst': 'Heb je als Digidokter één of meer deelnemers persoonlijke ondersteund?',
                'type': 'multiple_choice',
                'opties': ['In beperkte mate', 'Net voldoende', 'Er was teveel nood aan persoonlijke ondersteuning'],
                'volgorde': 10,
                'verplicht': True
            },
            {
                'vraag_tekst': 'Zijn er bepaalde onderwerpen waarover we in de toekomst zeker nog een Digicafé moeten organiseren?',
                'type': 'open_tekst',
                'opties': [],
                'volgorde': 11,
                'verplicht': True
            },
            {
                'vraag_tekst': 'Geef je eindscore: van 1 tot 10',
                'type': 'multiple_choice',
                'opties': ['1', '2', '3', '4', '5', '6', '7', '8', '9', '10'],
                'volgorde': 12,
                'verplicht': True
            }
        ]
        for v in standaard_vragen:
            vraag = EvaluationQuestion(
                form_id=form.id,
                vraag_tekst=v['vraag_tekst'],
                type=v['type'],
                opties=v['opties'],
                volgorde=v['volgorde'],
                verplicht=v['verplicht']
            )
            db.session.add(vraag)
        db.session.commit()
    return form


def verstuur_uitnodigingen_voor_sessie(agenda_item, host_url=None):
    """
    Verstuurt e-mailuitnodigingen naar alle gekoppelde digidokters van een afgelopen sessie.
    Retourneert (aantal_verzonden, lijst_van_namen_of_fouten).
    """
    if not agenda_item or not agenda_item.type.heeft_evaluatie:
        return 0, ["Geen evaluatieformulier vereist voor deze activiteit."]

    form = EvaluationForm.query.filter_by(activity_type_id=agenda_item.type_id, organisatie_id=agenda_item.organisatie_id).first()
    if not form or not form.actief or not form.vragen:
        return 0, ["Er is nog geen actief evaluatieformulier met vragen geconfigureerd voor dit type activiteit."]

    base_url = host_url or request.host_url.rstrip('/')
    verzonden_namen = []
    fouten = []

    for dd in agenda_item.digidokters:
        # Check of digidokter al heeft ingevuld
        reeds_ingevuld = EvaluationResponse.query.filter_by(agenda_item_id=agenda_item.id, digidokter_id=dd.id).first()
        if reeds_ingevuld:
            continue

        email = dd.email
        if not email:
            fouten.append(f"{dd.naam} (geen e-mailadres gekoppeld)")
            continue

        # Haal token op of maak nieuw aan
        invitation = EvaluationInvitation.query.filter_by(agenda_item_id=agenda_item.id, digidokter_id=dd.id).first()
        if not invitation:
            token = secrets.token_urlsafe(32)
            invitation = EvaluationInvitation(
                agenda_item_id=agenda_item.id,
                digidokter_id=dd.id,
                token=token,
                verzonden_op=datetime.utcnow(),
                is_ingevuld=False
            )
            db.session.add(invitation)
            db.session.commit()
        else:
            token = invitation.token

        link = f"{base_url}/evaluaties/invullen/{token}"

        datum_str = agenda_item.datum.strftime('%d-%m-%Y')
        locatie_naam = agenda_item.locatie.naam if agenda_item.locatie else 'onbekende locatie'
        omschrijving_blok = f"\nOmschrijving: {agenda_item.omschrijving.strip()}\n" if agenda_item.omschrijving and agenda_item.omschrijving.strip() else ""

        context = {
            'naam': dd.naam,
            'activiteit': agenda_item.type.naam,
            'datum': datum_str,
            'uur_van': agenda_item.uur_van,
            'uur_tot': agenda_item.uur_tot,
            'locatie': locatie_naam,
            'omschrijving_blok': omschrijving_blok,
            'link': link
        }

        tpl = EmailTemplate.query.filter_by(sleutel='evaluatie_uitnodiging').first()
        if tpl:
            onderwerp, inhoud = tpl.render(context)
        else:
            onderwerp = f"Evaluatie: {agenda_item.type.naam} op {datum_str}"
            inhoud = f"""Beste {dd.naam},

Bedankt voor je inzet tijdens het {agenda_item.type.naam} op {datum_str} van {agenda_item.uur_van} tot {agenda_item.uur_tot} ({locatie_naam})!{omschrijving_blok}

We horen graag hoe de sessie verlopen is. Zou je even de tijd willen nemen om het korte evaluatieformulier in te vullen? Dit helpt ons om de sessies continu te verbeteren.

👉 Klik op onderstaande link om het formulier in te vullen:
{link}

Alvast hartelijk dank voor je feedback en medewerking!

Met vriendelijke groet,
Digidokters Team
"""
        try:
            success, msg = verstuur_email([email], onderwerp, inhoud)
            if success:
                verzonden_namen.append(f"{dd.naam} ({email})")
                invitation.verzonden_op = datetime.utcnow()
                db.session.commit()
            else:
                fouten.append(f"{dd.naam} ({msg})")
        except Exception as e:
            fouten.append(f"{dd.naam} (Fout: {str(e)})")

    return len(verzonden_namen), verzonden_namen, fouten


def verstuur_herinneringen_voor_sessie(agenda_item, host_url=None):
    """
    Verstuurt e-mailherinneringen naar digidokters van een afgelopen sessie
    die de evaluatie nog niet hebben ingevuld.
    Retourneert (aantal_verzonden, lijst_van_namen_of_fouten, fouten).
    """
    if not agenda_item or not agenda_item.type.heeft_evaluatie:
        return 0, [], ["Geen evaluatieformulier vereist voor deze activiteit."]

    form = EvaluationForm.query.filter_by(activity_type_id=agenda_item.type_id, organisatie_id=agenda_item.organisatie_id).first()
    if not form or not form.actief or not form.vragen:
        return 0, [], ["Er is nog geen actief evaluatieformulier met vragen geconfigureerd voor dit type activiteit."]

    base_url = host_url or (request.host_url.rstrip('/') if request else '')
    verzonden_namen = []
    fouten = []

    tpl = EmailTemplate.query.filter_by(sleutel='evaluatie_herinnering').first()

    for dd in agenda_item.digidokters:
        # Check of digidokter al heeft ingevuld
        reeds_ingevuld = EvaluationResponse.query.filter_by(agenda_item_id=agenda_item.id, digidokter_id=dd.id).first()
        if reeds_ingevuld:
            continue

        email = dd.email
        if not email:
            fouten.append(f"{dd.naam} (geen e-mailadres gekoppeld)")
            continue

        # Haal token op of maak nieuw aan
        invitation = EvaluationInvitation.query.filter_by(agenda_item_id=agenda_item.id, digidokter_id=dd.id).first()
        if not invitation:
            token = secrets.token_urlsafe(32)
            invitation = EvaluationInvitation(
                agenda_item_id=agenda_item.id,
                digidokter_id=dd.id,
                token=token,
                verzonden_op=datetime.utcnow(),
                is_ingevuld=False
            )
            db.session.add(invitation)
            db.session.commit()
        else:
            token = invitation.token

        link = f"{base_url}/evaluaties/invullen/{token}"

        datum_str = agenda_item.datum.strftime('%d-%m-%Y')
        locatie_naam = agenda_item.locatie.naam if agenda_item.locatie else 'onbekende locatie'
        omschrijving_blok = f"\nOmschrijving: {agenda_item.omschrijving.strip()}\n" if agenda_item.omschrijving and agenda_item.omschrijving.strip() else ""

        context = {
            'naam': dd.naam,
            'activiteit': agenda_item.type.naam,
            'datum': datum_str,
            'uur_van': agenda_item.uur_van,
            'uur_tot': agenda_item.uur_tot,
            'locatie': locatie_naam,
            'omschrijving_blok': omschrijving_blok,
            'link': link
        }

        if tpl:
            onderwerp, inhoud = tpl.render(context)
        else:
            onderwerp = f"Herinnering: Evaluatie voor {agenda_item.type.naam} op {datum_str}"
            inhoud = f"""Beste {dd.naam},

Dit is een vriendelijke herinnering om het evaluatieformulier in te vullen voor het {agenda_item.type.naam} op {datum_str} van {agenda_item.uur_van} tot {agenda_item.uur_tot} ({locatie_naam}).{omschrijving_blok}

We hebben je feedback nog niet ontvangen. Jouw ervaringen als vrijwilliger zijn voor ons erg waardevol om de werking van Digidokters te versterken.

👉 Klik op onderstaande link om het formulier alsnog in te vullen:
{link}

Hartelijk dank voor je tijd en toewijding!

Met vriendelijke groet,
Digidokters Team
"""
        try:
            success, msg = verstuur_email([email], onderwerp, inhoud)
            if success:
                verzonden_namen.append(f"{dd.naam} ({email})")
                invitation.herinnering_verzonden_op = datetime.utcnow()
                invitation.herinnering_aantal = (invitation.herinnering_aantal or 0) + 1
                db.session.commit()
            else:
                fouten.append(f"{dd.naam} ({msg})")
        except Exception as e:
            fouten.append(f"{dd.naam} (Fout: {str(e)})")

    return len(verzonden_namen), verzonden_namen, fouten


def controleer_en_verstuur_afgelopen_evaluaties(org_id, host_url=None, async_mode=True):
    """
    Controleert automatisch op recente afgelopen sessies (afgelopen 2 dagen) met evaluatieplicht
    waarvoor nog geen uitnodiging is gestuurd.
    """
    from flask import current_app
    app = current_app._get_current_object()

    def _execute_check():
        with app.app_context():
            from sqlalchemy.orm import selectinload
            nu = datetime.now()
            vandaag = nu.date()
            # Enkel recente sessies van de laatste 2 dagen controleren (voorkom zware scans van historische data)
            min_datum = vandaag - timedelta(days=2)
            huidige_tijd_str = nu.strftime('%H:%M')

            afgelopen_items = (
                AgendaItem.query
                .filter_by(organisatie_id=org_id)
                .join(ActivityType, AgendaItem.type_id == ActivityType.id)
                .filter(ActivityType.heeft_evaluatie == True)
                .filter(AgendaItem.datum >= min_datum)
                .filter(
                    (AgendaItem.datum < vandaag) |
                    ((AgendaItem.datum == vandaag) & (AgendaItem.uur_tot <= huidige_tijd_str))
                )
                .options(selectinload(AgendaItem.digidokters))
                .all()
            )

            totaal_verzonden = 0
            for item in afgelopen_items:
                for dd in item.digidokters:
                    if not dd.email:
                        continue
                    reeds_ingevuld = EvaluationResponse.query.filter_by(agenda_item_id=item.id, digidokter_id=dd.id).first()
                    if reeds_ingevuld:
                        continue
                    inv = EvaluationInvitation.query.filter_by(agenda_item_id=item.id, digidokter_id=dd.id).first()
                    if not inv:
                        count, namen, _ = verstuur_uitnodigingen_voor_sessie(item, host_url)
                        totaal_verzonden += count
                        break
            return totaal_verzonden

    if async_mode and not current_app.config.get('TESTING'):
        import threading
        t = threading.Thread(target=_execute_check, daemon=True)
        t.start()
        return 0
    else:
        return _execute_check()


# ═══════════════════════════════════════════════════════════════
# BEHEER: EVALUATIEFORMULIEREN & VRAGEN
# ═══════════════════════════════════════════════════════════════

@eval_bp.route('/admin/evaluaties')
@login_required
@admin_required
def overzicht():
    """Overzicht van alle activiteitstypes met evaluatieformulieren en statistieken."""
    org_id = get_huidige_organisatie_id()
    
    # Automatisch uitnodigingen controleren en versturen voor afgelopen sessies
    try:
        controleer_en_verstuur_afgelopen_evaluaties(org_id, request.host_url.rstrip('/'))
    except Exception as e:
        current_app.logger.warning(f"Fout bij automatische evaluatiecheck: {e}")

    types = filter_op_organisatie(ActivityType.query, ActivityType).order_by(ActivityType.volgorde, ActivityType.naam).all()
    
    forms_dict = {}
    for t in types:
        form = EvaluationForm.query.filter_by(activity_type_id=t.id, organisatie_id=org_id).first()
        forms_dict[t.id] = form

    # Recent voltooide sessies met evaluatieplicht
    nu = datetime.now()
    vandaag = nu.date()
    huidige_tijd_str = nu.strftime('%H:%M')

    recente_sessies = (
        AgendaItem.query
        .filter_by(organisatie_id=org_id)
        .join(ActivityType, AgendaItem.type_id == ActivityType.id)
        .filter(ActivityType.heeft_evaluatie == True)
        .filter(
            (AgendaItem.datum < vandaag) |
            ((AgendaItem.datum == vandaag) & (AgendaItem.uur_tot <= huidige_tijd_str))
        )
        .order_by(AgendaItem.datum.desc(), AgendaItem.uur_van.desc())
        .limit(10)
        .all()
    )

    totaal_reacties = EvaluationResponse.query.filter_by(organisatie_id=org_id).count()

    return render_template(
        'admin/evaluaties/overzicht.html',
        types=types,
        forms_dict=forms_dict,
        recente_sessies=recente_sessies,
        totaal_reacties=totaal_reacties
    )


@eval_bp.route('/admin/evaluaties/<int:type_id>/bewerken', methods=['GET', 'POST'])
@login_required
@admin_required
def formulier_bewerken(type_id):
    """Formulier titel, toelichting en vragen beheren."""
    org_id = get_huidige_organisatie_id()
    act_type = db.session.get(ActivityType, type_id)
    if not act_type or act_type.organisatie_id != org_id:
        abort(404)

    form = get_or_create_evaluation_form(type_id, org_id)

    if request.method == 'POST':
        form.titel = request.form.get('titel', form.titel).strip()
        form.toelichting = request.form.get('toelichting', '').strip()
        form.actief = request.form.get('actief') == 'on'
        act_type.heeft_evaluatie = True  # Zorg dat de vlag aan staat
        db.session.commit()
        flash('Evaluatieformulier succesvol opgeslagen.', 'success')
        return redirect(url_for('eval.formulier_bewerken', type_id=type_id))

    return render_template(
        'admin/evaluaties/formulier_editor.html',
        form=form,
        act_type=act_type
    )


@eval_bp.route('/admin/evaluaties/formulier/<int:form_id>/vraag/toevoegen', methods=['POST'])
@login_required
@admin_required
def vraag_toevoegen(form_id):
    """Voegt een nieuwe vraag toe aan het evaluatieformulier."""
    org_id = get_huidige_organisatie_id()
    form = db.session.get(EvaluationForm, form_id)
    if not form or form.organisatie_id != org_id:
        abort(404)

    vraag_tekst = request.form.get('vraag_tekst', '').strip()
    v_type = request.form.get('type', 'multiple_choice')
    verplicht = request.form.get('verplicht') == 'on'
    opties_tekst = request.form.get('opties', '').strip()

    if not vraag_tekst:
        flash('Vraagtekst is verplicht.', 'danger')
        return redirect(url_for('eval.formulier_bewerken', type_id=form.activity_type_id))

    opties = []
    if v_type == 'multiple_choice':
        opties = [opt.strip() for opt in opties_tekst.split('\n') if opt.strip()]
        if not opties:
            opties = [opt.strip() for opt in opties_tekst.split(',') if opt.strip()]
        if not opties:
            opties = ['Niet veel', 'Een beetje', 'Redelijk wat', 'Veel', 'Heel veel']

    max_volgorde = db.session.query(db.func.max(EvaluationQuestion.volgorde)).filter_by(form_id=form.id).scalar() or 0

    nieuwe_vraag = EvaluationQuestion(
        form_id=form.id,
        vraag_tekst=vraag_tekst,
        type=v_type,
        opties=opties,
        volgorde=max_volgorde + 1,
        verplicht=verplicht
    )
    db.session.add(nieuwe_vraag)
    db.session.commit()

    flash('Vraag succesvol toegevoegd.', 'success')
    return redirect(url_for('eval.formulier_bewerken', type_id=form.activity_type_id))


@eval_bp.route('/admin/evaluaties/vraag/<int:vraag_id>/bewerken', methods=['POST'])
@login_required
@admin_required
def vraag_bewerken(vraag_id):
    """Bewerkt een bestaande vraag."""
    org_id = get_huidige_organisatie_id()
    vraag = db.session.get(EvaluationQuestion, vraag_id)
    if not vraag or vraag.form.organisatie_id != org_id:
        abort(404)

    vraag_tekst = request.form.get('vraag_tekst', '').strip()
    v_type = request.form.get('type', 'multiple_choice')
    verplicht = request.form.get('verplicht') == 'on'
    opties_tekst = request.form.get('opties', '').strip()

    if not vraag_tekst:
        flash('Vraagtekst is verplicht.', 'danger')
        return redirect(url_for('eval.formulier_bewerken', type_id=vraag.form.activity_type_id))

    opties = []
    if v_type == 'multiple_choice':
        opties = [opt.strip() for opt in opties_tekst.split('\n') if opt.strip()]
        if not opties:
            opties = [opt.strip() for opt in opties_tekst.split(',') if opt.strip()]

    vraag.vraag_tekst = vraag_tekst
    vraag.type = v_type
    vraag.opties = opties
    vraag.verplicht = verplicht
    db.session.commit()

    flash('Vraag succesvol bijgewerkt.', 'success')
    return redirect(url_for('eval.formulier_bewerken', type_id=vraag.form.activity_type_id))


@eval_bp.route('/admin/evaluaties/vraag/<int:vraag_id>/verwijderen', methods=['POST'])
@login_required
@admin_required
def vraag_verwijderen(vraag_id):
    """Verwijdert een vraag uit het evaluatieformulier."""
    org_id = get_huidige_organisatie_id()
    vraag = db.session.get(EvaluationQuestion, vraag_id)
    if not vraag or vraag.form.organisatie_id != org_id:
        abort(404)

    type_id = vraag.form.activity_type_id
    db.session.delete(vraag)
    db.session.commit()

    flash('Vraag verwijderd.', 'success')
    return redirect(url_for('eval.formulier_bewerken', type_id=type_id))


@eval_bp.route('/admin/evaluaties/vraag/<int:vraag_id>/volgorde/<richting>', methods=['GET', 'POST'])
@login_required
@admin_required
def vraag_volgorde(vraag_id, richting):
    """Verplaatst een vraag omhoog of omlaag."""
    org_id = get_huidige_organisatie_id()
    vraag = db.session.get(EvaluationQuestion, vraag_id)
    if not vraag or vraag.form.organisatie_id != org_id:
        abort(404)

    form_id = vraag.form_id
    type_id = vraag.form.activity_type_id

    alle_vragen = EvaluationQuestion.query.filter_by(form_id=form_id).order_by(EvaluationQuestion.volgorde).all()
    try:
        idx = alle_vragen.index(vraag)
        if richting == 'omhoog' and idx > 0:
            buur = alle_vragen[idx - 1]
            vraag.volgorde, buur.volgorde = buur.volgorde, vraag.volgorde
            db.session.commit()
        elif richting == 'omlaag' and idx < len(alle_vragen) - 1:
            buur = alle_vragen[idx + 1]
            vraag.volgorde, buur.volgorde = buur.volgorde, vraag.volgorde
            db.session.commit()
    except ValueError:
        pass

    return redirect(url_for('eval.formulier_bewerken', type_id=type_id))


# ═══════════════════════════════════════════════════════════════
# BEHEER: RESULTATEN & OVERZICHT
# ═══════════════════════════════════════════════════════════════

@eval_bp.route('/admin/evaluaties/resultaten')
@login_required
@admin_required
def resultaten():
    """Overzicht van ingevulde evaluaties per sessie."""
    org_id = get_huidige_organisatie_id()

    type_filter = request.args.get('type_id', 0, type=int)
    enkel_ingevuld = request.args.get('enkel_ingevuld') == 'on' or request.args.get('enkel_ingevuld') == '1'

    query = (
        AgendaItem.query
        .filter_by(organisatie_id=org_id)
        .join(ActivityType, AgendaItem.type_id == ActivityType.id)
        .filter(ActivityType.heeft_evaluatie == True)
    )
    if type_filter:
        query = query.filter(AgendaItem.type_id == type_filter)

    if enkel_ingevuld:
        query = query.filter(AgendaItem.evaluatie_reacties.any())

    sessies = query.order_by(AgendaItem.datum.desc(), AgendaItem.uur_van.desc()).all()
    types = filter_op_organisatie(ActivityType.query.filter_by(heeft_evaluatie=True), ActivityType).all()

    return render_template(
        'admin/evaluaties/resultaten.html',
        sessies=sessies,
        types=types,
        type_filter=type_filter,
        enkel_ingevuld=enkel_ingevuld
    )


@eval_bp.route('/admin/evaluaties/sessie/<int:agenda_id>')
@login_required
@admin_required
def sessie_detail(agenda_id):
    """Toont alle ingevulde reacties voor een specifieke sessie."""
    org_id = get_huidige_organisatie_id()
    item = db.session.get(AgendaItem, agenda_id)
    if not item or item.organisatie_id != org_id:
        abort(404)

    form = EvaluationForm.query.filter_by(activity_type_id=item.type_id, organisatie_id=org_id).first()
    reacties = EvaluationResponse.query.filter_by(agenda_item_id=item.id).order_by(EvaluationResponse.ingediend_op.desc()).all()
    uitnodigingen = EvaluationInvitation.query.filter_by(agenda_item_id=item.id).all()
    uitnodigingen_map = {inv.digidokter_id: inv for inv in uitnodigingen}

    return render_template(
        'admin/evaluaties/sessie_detail.html',
        item=item,
        form=form,
        reacties=reacties,
        uitnodigingen=uitnodigingen,
        uitnodigingen_map=uitnodigingen_map
    )


# ═══════════════════════════════════════════════════════════════
# UITNODIGINGEN & HERINNERINGEN VERSTUREN (HANDMATIG / VANUIT AGENDA)
# ═══════════════════════════════════════════════════════════════

@eval_bp.route('/agenda/<int:agenda_id>/verstuur-evaluaties', methods=['POST'])
@login_required
@writer_required
def verstuur_uitnodigingen(agenda_id):
    """Verstuurt handmatig evaluatie-uitnodigingen naar de digidokters van dit agenda-item."""
    org_id = get_huidige_organisatie_id()
    item = db.session.get(AgendaItem, agenda_id)
    if not item or item.organisatie_id != org_id:
        abort(404)

    if not item.type.heeft_evaluatie:
        flash('Voor dit type activiteit is geen evaluatieformulier ingeschakeld.', 'warning')
        return redirect(request.referrer or url_for('agenda.lijst'))

    aantal, namen, fouten = verstuur_uitnodigingen_voor_sessie(item, request.host_url.rstrip('/'))

    if aantal > 0:
        flash(f'Evaluatie-uitnodiging succesvol verstuurd naar: {", ".join(namen)}.', 'success')
    elif not fouten:
        flash('Alle gekoppelde digidokters hebben de evaluatie reeds ingevuld of ontvangen.', 'info')

    if fouten:
        flash(f'Kon niet versturen naar: {", ".join(fouten)}.', 'warning')

    return redirect(request.referrer or url_for('agenda.lijst'))


@eval_bp.route('/agenda/<int:agenda_id>/verstuur-herinneringen', methods=['POST'])
@login_required
@writer_required
def verstuur_herinneringen(agenda_id):
    """Verstuurt handmatig evaluatie-herinneringen naar digidokters die de evaluatie nog niet hebben ingevuld."""
    org_id = get_huidige_organisatie_id()
    item = db.session.get(AgendaItem, agenda_id)
    if not item or item.organisatie_id != org_id:
        abort(404)

    if not item.type.heeft_evaluatie:
        flash('Voor dit type activiteit is geen evaluatieformulier ingeschakeld.', 'warning')
        return redirect(request.referrer or url_for('agenda.lijst'))

    aantal, namen, fouten = verstuur_herinneringen_voor_sessie(item, request.host_url.rstrip('/'))

    if aantal > 0:
        flash(f'Evaluatie-herinnering succesvol verstuurd naar: {", ".join(namen)}.', 'success')
    elif not fouten:
        flash('Alle gekoppelde digidokters hebben de evaluatie reeds ingevuld.', 'info')

    if fouten:
        flash(f'Kon herinnering niet versturen naar: {", ".join(fouten)}.', 'warning')

    return redirect(request.referrer or url_for('agenda.lijst'))


# ═══════════════════════════════════════════════════════════════
# FORMULIER INVULLEN (VOOR DIGIDOKTERS / MEDEWERKERS)
# ═══════════════════════════════════════════════════════════════

@eval_bp.route('/evaluaties/agenda/<int:agenda_id>/invullen', methods=['GET', 'POST'])
@login_required
def invullen_sessie(agenda_id):
    """Formulier invullen voor een ingelogde gebruiker/digidokter."""
    org_id = get_huidige_organisatie_id()
    item = db.session.get(AgendaItem, agenda_id)
    if not item or item.organisatie_id != org_id:
        abort(404)

    form = get_or_create_evaluation_form(item.type_id, org_id)

    # Bepaal actieve digidokter voor de huidige ingelogde gebruiker
    huidige_dd = Digidokter.query.filter_by(user_id=current_user.id, organisatie_id=org_id).first()
    if not huidige_dd and current_user.naam:
        huidige_dd = Digidokter.query.filter(
            Digidokter.organisatie_id == org_id,
            db.func.lower(Digidokter.naam) == db.func.lower(current_user.naam)
        ).first()

    if request.method == 'POST':
        dd_id = request.form.get('digidokter_id', type=int)
        if not dd_id and huidige_dd:
            dd_id = huidige_dd.id

        # Controleer of digidokter al ingevuld heeft
        if dd_id:
            bestaand = EvaluationResponse.query.filter_by(agenda_item_id=item.id, digidokter_id=dd_id).first()
            if bestaand:
                flash('Je hebt dit evaluatieformulier al eerder ingevuld voor deze sessie. Bedankt!', 'info')
                return redirect(url_for('agenda.lijst'))

        # Verwerk antwoorden
        antwoorden = {}
        ontbrekende_vragen = []
        for vraag in form.vragen:
            key = f"vraag_{vraag.id}"
            val = request.form.get(key, '').strip()
            if vraag.verplicht and not val:
                ontbrekende_vragen.append(vraag.vraag_tekst)
            antwoorden[str(vraag.id)] = val

        if ontbrekende_vragen:
            flash(f'Gelieve alle verplichte vragen in te vullen.', 'danger')
            return render_template(
                'evaluaties/invullen.html',
                item=item,
                form=form,
                huidige_dd=huidige_dd,
                antwoorden=antwoorden
            )

        reactie = EvaluationResponse(
            organisatie_id=org_id,
            agenda_item_id=item.id,
            form_id=form.id,
            digidokter_id=dd_id,
            user_id=current_user.id if current_user.is_authenticated else None,
            ingediend_op=datetime.utcnow(),
            antwoorden=antwoorden
        )
        db.session.add(reactie)

        # Werk eventuele uitnodigingstoken bij
        if dd_id:
            invitation = EvaluationInvitation.query.filter_by(agenda_item_id=item.id, digidokter_id=dd_id).first()
            if invitation:
                invitation.is_ingevuld = True

        db.session.commit()
        flash('Bedankt voor het invullen van de evaluatie!', 'success')
        return redirect(url_for('agenda.lijst'))

    return render_template(
        'evaluaties/invullen.html',
        item=item,
        form=form,
        huidige_dd=huidige_dd,
        antwoorden={}
    )


@eval_bp.route('/evaluaties/invullen/<token>', methods=['GET', 'POST'])
def invullen_token(token):
    """Direct formulier invullen via de token uit de e-mail (zowel voor ingelogde als niet-ingelogde digidokters)."""
    invitation = EvaluationInvitation.query.filter_by(token=token).first()
    if not invitation:
        flash('Ongeldige of verlopen evaluatielink.', 'danger')
        return redirect(url_for('auth.login'))

    item = invitation.agenda_item
    form = EvaluationForm.query.filter_by(activity_type_id=item.type_id, organisatie_id=item.organisatie_id).first()
    if not form:
        form = get_or_create_evaluation_form(item.type_id, item.organisatie_id)

    dd = invitation.digidokter

    # Check of al ingevuld
    bestaand = EvaluationResponse.query.filter_by(agenda_item_id=item.id, digidokter_id=dd.id).first()
    if bestaand or invitation.is_ingevuld:
        return render_template(
            'evaluaties/bedankt.html',
            item=item,
            dd=dd,
            reeds_ingevuld=True
        )

    if request.method == 'POST':
        antwoorden = {}
        ontbrekende = []
        for vraag in form.vragen:
            key = f"vraag_{vraag.id}"
            val = request.form.get(key, '').strip()
            if vraag.verplicht and not val:
                ontbrekende.append(vraag.vraag_tekst)
            antwoorden[str(vraag.id)] = val

        if ontbrekende:
            flash('Gelieve alle verplichte vragen in te vullen.', 'danger')
            return render_template(
                'evaluaties/invullen.html',
                item=item,
                form=form,
                huidige_dd=dd,
                token=token,
                antwoorden=antwoorden
            )

        reactie = EvaluationResponse(
            organisatie_id=item.organisatie_id,
            agenda_item_id=item.id,
            form_id=form.id,
            digidokter_id=dd.id,
            user_id=dd.user_id if dd else None,
            ingediend_op=datetime.utcnow(),
            antwoorden=antwoorden
        )
        db.session.add(reactie)
        invitation.is_ingevuld = True
        db.session.commit()

        return render_template(
            'evaluaties/bedankt.html',
            item=item,
            dd=dd,
            reeds_ingevuld=False
        )

    return render_template(
        'evaluaties/invullen.html',
        item=item,
        form=form,
        huidige_dd=dd,
        token=token,
        antwoorden={}
    )
