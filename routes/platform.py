from datetime import datetime, timezone
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from extensions import db
from models.organisatie import Organisatie, UserOrganisatie
from models.user import User
from models.registration import Registration
from models.digidokter import Digidokter
from models.agenda import AgendaItem
from models.email_template import EmailTemplate, ensure_default_email_templates
from sqlalchemy import func, extract
from utils.decorators import platform_admin_required

platform_bp = Blueprint('platform', __name__, url_prefix='/platform')

@platform_bp.route('/dashboard')
@login_required
@platform_admin_required
def dashboard():
    ensure_default_email_templates()

    # Jaarfilter
    geselecteerd_jaar = request.args.get('jaar', 'alle').strip()

    # Haal alle jaren op waarin registraties zijn gedaan
    beschikbare_jaren_tuples = (
        db.session.query(extract('year', Registration.datum).label('jr'))
        .distinct()
        .order_by(extract('year', Registration.datum).desc())
        .all()
    )
    beschikbare_jaren = [int(j[0]) for j in beschikbare_jaren_tuples if j[0] is not None]

    # Basis platform tellers
    total_orgs = Organisatie.query.count()
    active_orgs = Organisatie.query.filter_by(actief=True).count()
    total_users = User.query.count()
    total_links = UserOrganisatie.query.count()

    # 1. Totaal aantal consultaties (excl. 'sjabloon' organisatie)
    reg_query = Registration.query.join(Organisatie, Registration.organisatie_id == Organisatie.id).filter(Organisatie.slug != 'sjabloon')
    if geselecteerd_jaar != 'alle':
        try:
            jaar_int = int(geselecteerd_jaar)
            reg_query = reg_query.filter(extract('year', Registration.datum) == jaar_int)
        except ValueError:
            geselecteerd_jaar = 'alle'

    total_consultaties = reg_query.count()

    # 2. Aantal actieve vrijwilligers (Digidokters) over aangesloten gemeenten heen
    active_volunteers = Digidokter.query.join(Organisatie, Digidokter.organisatie_id == Organisatie.id).filter(
        Organisatie.slug != 'sjabloon',
        Digidokter.actief == True
    ).count()

    unique_active_volunteers = db.session.query(Digidokter.naam).join(
        Organisatie, Digidokter.organisatie_id == Organisatie.id
    ).filter(
        Organisatie.slug != 'sjabloon',
        Digidokter.actief == True
    ).distinct().count()

    # 3. Totaal aantal geplande/uitgevoerde sessies
    total_sessions = AgendaItem.query.join(Organisatie, AgendaItem.organisatie_id == Organisatie.id).filter(
        Organisatie.slug != 'sjabloon'
    ).count()

    # 4. Spreiding over gemeenten / organisaties
    alle_organisaties = Organisatie.query.order_by(Organisatie.naam).all()

    consultaties_per_org_query = (
        db.session.query(Registration.organisatie_id, func.count(Registration.id))
        .join(Organisatie, Registration.organisatie_id == Organisatie.id)
    )
    if geselecteerd_jaar != 'alle':
        consultaties_per_org_query = consultaties_per_org_query.filter(extract('year', Registration.datum) == int(geselecteerd_jaar))
    consultaties_map = dict(consultaties_per_org_query.group_by(Registration.organisatie_id).all())

    vrijwilligers_map = dict(
        db.session.query(Digidokter.organisatie_id, func.count(Digidokter.id))
        .filter(Digidokter.actief == True)
        .group_by(Digidokter.organisatie_id)
        .all()
    )

    sessies_map = dict(
        db.session.query(AgendaItem.organisatie_id, func.count(AgendaItem.id))
        .group_by(AgendaItem.organisatie_id)
        .all()
    )

    gebruikers_map = dict(
        db.session.query(UserOrganisatie.organisatie_id, func.count(UserOrganisatie.id))
        .filter(UserOrganisatie.actief == True)
        .group_by(UserOrganisatie.organisatie_id)
        .all()
    )

    gemeenten_statistieken = []
    for org in alle_organisaties:
        c_count = consultaties_map.get(org.id, 0)
        v_count = vrijwilligers_map.get(org.id, 0)
        s_count = sessies_map.get(org.id, 0)
        u_count = gebruikers_map.get(org.id, 0)
        percentage = round((c_count / total_consultaties * 100), 1) if total_consultaties > 0 else 0

        gemeenten_statistieken.append({
            'id': org.id,
            'naam': org.naam,
            'slug': org.slug,
            'actief': org.actief,
            'is_sjabloon': org.slug == 'sjabloon',
            'consultaties': c_count,
            'vrijwilligers': v_count,
            'sessies': s_count,
            'gebruikers': u_count,
            'percentage': percentage
        })

    # Sorteer op aantal consultaties (aflopend), daarna op naam (sjabloon onderaan)
    gemeenten_statistieken.sort(key=lambda x: (x['is_sjabloon'], -x['consultaties'], x['naam']))

    chart_gemeenten = [g['naam'] for g in gemeenten_statistieken if not g['is_sjabloon']]
    chart_consultaties = [g['consultaties'] for g in gemeenten_statistieken if not g['is_sjabloon']]
    chart_vrijwilligers = [g['vrijwilligers'] for g in gemeenten_statistieken if not g['is_sjabloon']]

    return render_template(
        'platform/dashboard.html',
        total_orgs=total_orgs,
        active_orgs=active_orgs,
        total_users=total_users,
        total_links=total_links,
        total_consultaties=total_consultaties,
        active_volunteers=active_volunteers,
        unique_active_volunteers=unique_active_volunteers,
        total_sessions=total_sessions,
        gemeenten_statistieken=gemeenten_statistieken,
        geselecteerd_jaar=geselecteerd_jaar,
        beschikbare_jaren=beschikbare_jaren,
        chart_gemeenten=chart_gemeenten,
        chart_consultaties=chart_consultaties,
        chart_vrijwilligers=chart_vrijwilligers
    )

# --- Organisaties CRUD ---

@platform_bp.route('/organisaties')
@login_required
@platform_admin_required
def organisaties():
    orgs = Organisatie.query.order_by(Organisatie.naam).all()
    return render_template('platform/organisaties.html', organisaties=orgs)

@platform_bp.route('/organisaties/nieuw', methods=['GET', 'POST'])
@login_required
@platform_admin_required
def organisatie_nieuw():
    if request.method == 'POST':
        naam = request.form.get('naam', '').strip()
        slug = request.form.get('slug', '').strip().lower()
        actief = request.form.get('actief') == 'on'

        if not naam or not slug:
            flash('Naam en slug zijn verplicht.', 'danger')
            return render_template('platform/organisatie_form.html', actie='Nieuw', org=None)

        if Organisatie.query.filter_by(slug=slug).first():
            flash('Er bestaat al een organisatie met deze slug.', 'danger')
            return render_template('platform/organisatie_form.html', actie='Nieuw', org=None, form_data=request.form)

        org = Organisatie(naam=naam, slug=slug, actief=actief)
        db.session.add(org)
        db.session.commit()
        
        from utils.tenant import seed_organisatie_defaults
        seed_organisatie_defaults(org.id)
        
        flash(f'Organisatie {naam} aangemaakt.', 'success')
        return redirect(url_for('platform.organisaties'))

    return render_template('platform/organisatie_form.html', actie='Nieuw', org=None)

@platform_bp.route('/organisaties/<int:org_id>/wijzig', methods=['GET', 'POST'])
@login_required
@platform_admin_required
def organisatie_wijzigen(org_id):
    org = db.get_or_404(Organisatie, org_id)

    if request.method == 'POST':
        naam = request.form.get('naam', '').strip()
        slug = request.form.get('slug', '').strip().lower()
        org.actief = request.form.get('actief') == 'on'

        if not naam or not slug:
            flash('Naam en slug zijn verplicht.', 'danger')
            return render_template('platform/organisatie_form.html', actie='Wijzigen', org=org)

        existing = Organisatie.query.filter_by(slug=slug).first()
        if existing and existing.id != org.id:
            flash('Er bestaat al een andere organisatie met deze slug.', 'danger')
            return render_template('platform/organisatie_form.html', actie='Wijzigen', org=org, form_data=request.form)

        org.naam = naam
        org.slug = slug
        db.session.commit()
        flash(f'Organisatie {naam} bijgewerkt.', 'success')
        return redirect(url_for('platform.organisaties'))

    return render_template('platform/organisatie_form.html', actie='Wijzigen', org=org)

@platform_bp.route('/organisaties/<int:org_id>/toggle')
@login_required
@platform_admin_required
def organisatie_toggle(org_id):
    org = db.get_or_404(Organisatie, org_id)
    if org.id == 1:
        flash('De default organisatie kan niet worden gedeactiveerd.', 'warning')
        return redirect(url_for('platform.organisaties'))
    org.actief = not org.actief
    db.session.commit()
    status = 'geactiveerd' if org.actief else 'gedeactiveerd'
    flash(f'Organisatie {org.naam} {status}.', 'info')
    return redirect(url_for('platform.organisaties'))


@platform_bp.route('/organisaties/<int:org_id>/verwijderen', methods=['POST'])
@login_required
@platform_admin_required
def organisatie_verwijderen(org_id):
    """Wist een organisatie en alle geassocieerde data permanent."""
    org = db.get_or_404(Organisatie, org_id)
    if org.id == 1 or org.slug == 'sjabloon':
        flash(f'De organisatie "{org.naam}" is een beschermde systeemorganisatie en kan niet worden gewist.', 'danger')
        return redirect(url_for('platform.organisaties'))

    org_naam = org.naam

    from flask import session
    from models.registration import Registration
    from models.agenda import AgendaItem, agenda_digidokters
    from models.digidokter import Digidokter
    from models.activity_type import ActivityType
    from models.location import Location
    from models.device import Device
    from models.age_category import AgeCategory
    from models.herkomst import Herkomst
    from models.document import Document, Folder
    from models.evaluation import EvaluationForm, EvaluationQuestion, EvaluationResponse, EvaluationInvitation
    from models.audit import AuditLog

    # 1. Evaluatiedata
    EvaluationResponse.query.filter_by(organisatie_id=org_id).delete(synchronize_session=False)

    agenda_ids = [item.id for item in AgendaItem.query.filter_by(organisatie_id=org_id).all()]
    if agenda_ids:
        EvaluationInvitation.query.filter(EvaluationInvitation.agenda_item_id.in_(agenda_ids)).delete(synchronize_session=False)

    form_ids = [f.id for f in EvaluationForm.query.filter_by(organisatie_id=org_id).all()]
    if form_ids:
        EvaluationQuestion.query.filter(EvaluationQuestion.form_id.in_(form_ids)).delete(synchronize_session=False)

    EvaluationForm.query.filter_by(organisatie_id=org_id).delete(synchronize_session=False)

    # 2. Agenda-items en aanwezigheden
    if agenda_ids:
        db.session.execute(
            agenda_digidokters.delete().where(agenda_digidokters.c.agenda_item_id.in_(agenda_ids))
        )
    AgendaItem.query.filter_by(organisatie_id=org_id).delete(synchronize_session=False)

    # 3. Registraties
    Registration.query.filter_by(organisatie_id=org_id).delete(synchronize_session=False)

    # 4. Documenten en Mappen
    Document.query.filter_by(organisatie_id=org_id).delete(synchronize_session=False)
    folders = Folder.query.filter_by(organisatie_id=org_id).all()
    for f in folders:
        f.parent_id = None
    db.session.flush()
    Folder.query.filter_by(organisatie_id=org_id).delete(synchronize_session=False)

    # 5. Stamgegevens
    Digidokter.query.filter_by(organisatie_id=org_id).delete(synchronize_session=False)
    ActivityType.query.filter_by(organisatie_id=org_id).delete(synchronize_session=False)
    Location.query.filter_by(organisatie_id=org_id).delete(synchronize_session=False)
    Device.query.filter_by(organisatie_id=org_id).delete(synchronize_session=False)
    AgeCategory.query.filter_by(organisatie_id=org_id).delete(synchronize_session=False)
    Herkomst.query.filter_by(organisatie_id=org_id).delete(synchronize_session=False)

    # 6. Audit Logs
    AuditLog.query.filter_by(organisatie_id=org_id).delete(synchronize_session=False)

    # 7. Gebruikerskoppelingen & Wees-gebruikers opruimen
    user_links = UserOrganisatie.query.filter_by(organisatie_id=org_id).all()
    user_ids_to_check = [link.user_id for link in user_links]
    UserOrganisatie.query.filter_by(organisatie_id=org_id).delete(synchronize_session=False)
    db.session.flush()

    for uid in user_ids_to_check:
        u = db.session.get(User, uid)
        if u and u.rol != 'platformbeheerder':
            other_links = UserOrganisatie.query.filter_by(user_id=uid).count()
            if other_links == 0:
                db.session.delete(u)

    # 8. Sessie herstel
    if session.get('organisatie_id') == org_id:
        default_org = db.session.get(Organisatie, 1)
        if default_org:
            session['organisatie_id'] = default_org.id
            session['organisatie_naam'] = default_org.naam

    # 9. Organisatie zelf verwijderen
    db.session.delete(org)
    db.session.commit()

    flash(f'Organisatie "{org_naam}" en alle bijbehorende gegevens zijn definitief gewist.', 'success')
    return redirect(url_for('platform.organisaties'))


# --- Koppelingen ---

@platform_bp.route('/koppelingen', methods=['GET', 'POST'])
@login_required
@platform_admin_required
def koppelingen():
    if request.method == 'POST':
        user_id = request.form.get('user_id', type=int)
        organisatie_id = request.form.get('organisatie_id', type=int)
        rol = request.form.get('rol', 'medewerker')
        actief = request.form.get('actief') == 'on'

        if not user_id or not organisatie_id:
            flash('Gebruiker en organisatie zijn verplicht.', 'danger')
            return redirect(url_for('platform.koppelingen'))

        user = db.session.get(User, user_id)
        org = db.session.get(Organisatie, organisatie_id)

        if not user or not org:
            flash('Ongeldige gebruiker of organisatie.', 'danger')
            return redirect(url_for('platform.koppelingen'))

        if org.slug == 'sjabloon' and user.rol != 'platformbeheerder':
            flash('Enkel platformbeheerders hebben toegang tot de Sjabloon-organisatie.', 'danger')
            return redirect(url_for('platform.koppelingen'))

        # Check of koppeling al bestaat
        existing = UserOrganisatie.query.filter_by(user_id=user_id, organisatie_id=organisatie_id).first()
        if existing:
            flash(f'Gebruiker {user.naam} is al gekoppeld aan {org.naam}.', 'warning')
            return redirect(url_for('platform.koppelingen'))

        uo = UserOrganisatie(
            user_id=user_id,
            organisatie_id=organisatie_id,
            rol=rol,
            actief=actief
        )
        db.session.add(uo)
        db.session.commit()
        flash(f'Gebruiker {user.naam} succesvol gekoppeld aan {org.naam}.', 'success')
        return redirect(url_for('platform.koppelingen'))

    sort_by = request.args.get('sort_by', 'gebruiker').strip()
    direction = request.args.get('direction', 'asc').strip()

    query = UserOrganisatie.query.join(User, UserOrganisatie.user_id == User.id).join(Organisatie, UserOrganisatie.organisatie_id == Organisatie.id)

    if sort_by == 'organisatie':
        order_col = Organisatie.naam.desc() if direction == 'desc' else Organisatie.naam.asc()
    elif sort_by == 'rol':
        order_col = UserOrganisatie.rol.desc() if direction == 'desc' else UserOrganisatie.rol.asc()
    elif sort_by == 'status':
        order_col = UserOrganisatie.actief.desc() if direction == 'desc' else UserOrganisatie.actief.asc()
    else:  # sort_by == 'gebruiker'
        order_col = User.naam.desc() if direction == 'desc' else User.naam.asc()

    links = query.order_by(order_col).all()
    all_users = User.query.order_by(User.naam).all()
    all_orgs = Organisatie.query.filter(Organisatie.slug != 'sjabloon').order_by(Organisatie.naam).all()
    return render_template(
        'platform/koppelingen.html',
        links=links,
        users=all_users,
        organisaties=all_orgs,
        sort_by=sort_by,
        direction=direction
    )

@platform_bp.route('/koppelingen/<int:link_id>/toggle')
@login_required
@platform_admin_required
def koppeling_toggle(link_id):
    uo = db.get_or_404(UserOrganisatie, link_id)
    # Beveiliging: de eerste beheerder op de eerste organisatie niet deactiveren
    if uo.user_id == 1 and uo.organisatie_id == 1:
        flash('De default beheerkoppeling kan niet worden gedeactiveerd.', 'warning')
        return redirect(url_for('platform.koppelingen'))

    uo.actief = not uo.actief
    db.session.commit()
    status = 'geactiveerd' if uo.actief else 'gedeactiveerd'
    flash(f'Koppeling voor {uo.user.naam} bij {uo.organisatie.naam} {status}.', 'info')
    return redirect(url_for('platform.koppelingen'))

@platform_bp.route('/koppelingen/<int:link_id>/ontkoppelen', methods=['POST'])
@login_required
@platform_admin_required
def koppeling_verwijderen(link_id):
    uo = db.get_or_404(UserOrganisatie, link_id)
    if uo.user_id == 1 and uo.organisatie_id == 1:
        flash('De default beheerkoppeling kan niet worden verwijderd.', 'warning')
        return redirect(url_for('platform.koppelingen'))

    db.session.delete(uo)
    db.session.commit()
    flash(f'Koppeling voor {uo.user.naam} bij {uo.organisatie.naam} verwijderd.', 'success')
    return redirect(url_for('platform.koppelingen'))


# --- E-mailsjablonen Beheer ---

@platform_bp.route('/emailsjablonen')
@login_required
@platform_admin_required
def emailsjablonen():
    ensure_default_email_templates()
    templates = EmailTemplate.query.order_by(EmailTemplate.naam).all()
    return render_template('platform/emailsjablonen.html', templates=templates)


@platform_bp.route('/emailsjablonen/<int:template_id>/wijzig', methods=['GET', 'POST'])
@login_required
@platform_admin_required
def emailsjablonen_wijzigen(template_id):
    tpl = db.get_or_404(EmailTemplate, template_id)

    if request.method == 'POST':
        onderwerp = request.form.get('onderwerp', '').strip()
        inhoud = request.form.get('inhoud', '').strip()

        if not onderwerp or not inhoud:
            flash('Onderwerp en inhoud zijn verplicht.', 'danger')
            return render_template('platform/emailsjabloon_form.html', template=tpl)

        tpl.onderwerp = onderwerp
        tpl.inhoud = inhoud
        tpl.gewijzigd_op = datetime.now(timezone.utc)
        db.session.commit()
        flash(f'E-mailsjabloon "{tpl.naam}" succesvol opgeslagen.', 'success')
        return redirect(url_for('platform.emailsjablonen'))

    # Voorbeeldcontext voor de live preview
    sample_context = {
        'naam': 'Jan Janssens',
        'activiteit': 'Digidokter Sessie',
        'datum': datetime.now().strftime('%d-%m-%Y'),
        'uur_van': '09:30',
        'uur_tot': '11:30',
        'locatie': 'Bibliotheek Hoofdfiliaal',
        'omschrijving_blok': '\nOmschrijving: Vrije inloop voor digitale vragen en ondersteuning bij eBox en Itsme.\n',
        'link': request.host_url.rstrip('/') + '/evaluaties/invullen/voorbeeld-token-12345'
    }
    preview_onderwerp, preview_inhoud = tpl.render(sample_context)

    return render_template(
        'platform/emailsjabloon_form.html',
        template=tpl,
        preview_onderwerp=preview_onderwerp,
        preview_inhoud=preview_inhoud,
        vandaag_str=sample_context['datum']
    )


@platform_bp.route('/emailsjablonen/<int:template_id>/herstel', methods=['POST'])
@login_required
@platform_admin_required
def emailsjablonen_herstellen(template_id):
    tpl = db.get_or_404(EmailTemplate, template_id)
    defaults = EmailTemplate.get_default_templates()

    if tpl.sleutel in defaults:
        default_data = defaults[tpl.sleutel]
        tpl.onderwerp = default_data['onderwerp']
        tpl.inhoud = default_data['inhoud']
        tpl.gewijzigd_op = datetime.now(timezone.utc)
        db.session.commit()
        flash(f'Sjabloon "{tpl.naam}" is hersteld naar de standaardtekst.', 'info')
    else:
        flash(f'Geen standaardwaarden gevonden voor sjabloon "{tpl.naam}".', 'warning')

    return redirect(url_for('platform.emailsjablonen_wijzigen', template_id=tpl.id))

