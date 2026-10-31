"""Authenticatie routes: login, logout, wachtwoord wijzigen."""
import re
from datetime import datetime, timezone
from urllib.parse import urlparse
from flask import Blueprint, render_template, redirect, url_for, flash, request, session, current_app
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from extensions import db, limiter
from models.user import User
from utils.helpers import is_veilige_redirect

auth_bp = Blueprint('auth', __name__)

_is_veilige_redirect = is_veilige_redirect


def _valideer_wachtwoord(wachtwoord: str) -> list[str]:
    """Valideer wachtwoordsterkte. Geeft lijst van fouten terug (leeg = OK)."""
    fouten = []
    if len(wachtwoord) < 8:
        fouten.append('Het wachtwoord moet minstens 8 tekens bevatten.')
    if not any(c.isupper() for c in wachtwoord):
        fouten.append('Het wachtwoord moet minstens één hoofdletter bevatten.')
    if not any(c.isdigit() for c in wachtwoord):
        fouten.append('Het wachtwoord moet minstens één cijfer bevatten.')
    return fouten


@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute; 20 per hour", methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('reg.lijst'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        wachtwoord = request.form.get('wachtwoord', '')

        gebruiker = User.query.filter(db.func.lower(User.email) == email).first()

        if not gebruiker or not check_password_hash(gebruiker.wachtwoord_hash, wachtwoord):
            try:
                from utils.health import record_system_error
                record_system_error(
                    status_code=401,
                    type_fout='LoginFailed',
                    bericht=f'Mislukte inlogpoging voor e-mail: {email}',
                    endpoint='auth.login',
                    pad=request.path,
                    methode='POST',
                    ip_adres=request.remote_addr,
                    gebruiker=email,
                    organisatie_id=None
                )
            except Exception:
                pass
            flash('Ongeldig e-mailadres of wachtwoord.', 'danger')
            return render_template('auth/login.html')

        if not gebruiker.actief:
            try:
                from utils.health import record_system_error
                record_system_error(
                    status_code=403,
                    type_fout='AccountDisabled',
                    bericht=f'Inlogpoging op gedeactiveerd account: {email}',
                    endpoint='auth.login',
                    pad=request.path,
                    methode='POST',
                    ip_adres=request.remote_addr,
                    gebruiker=email,
                    organisatie_id=None
                )
            except Exception:
                pass
            flash('Uw account is gedeactiveerd. Contacteer de beheerder.', 'danger')
            return render_template('auth/login.html')

        login_user(gebruiker, remember=request.form.get('onthoud') == 'on')
        gebruiker.laatste_login = datetime.now(timezone.utc)
        db.session.commit()

        # Organisatie context instellen
        if gebruiker.rol == 'platformbeheerder':
            if gebruiker.moet_wachtwoord_wijzigen:
                flash('Welkom! Gelieve uw tijdelijk wachtwoord te wijzigen.', 'info')
                return redirect(url_for('auth.wachtwoord_wijzigen'))
            flash(f'Welkom, platformbeheerder {gebruiker.naam}!', 'success')
            return redirect(url_for('platform.dashboard'))

        active_memberships = [
            uo for uo in gebruiker.user_organisaties 
            if uo.actief and uo.organisatie and uo.organisatie.actief and uo.organisatie.slug != 'sjabloon'
        ]
        if not active_memberships:
            logout_user()
            flash('Uw account is niet gekoppeld aan een actieve organisatie. Contacteer de beheerder.', 'danger')
            return redirect(url_for('auth.login'))

        if len(active_memberships) == 1:
            session['organisatie_id'] = active_memberships[0].organisatie_id

        # Verplicht wachtwoord wijzigen bij eerste aanmelding
        if gebruiker.moet_wachtwoord_wijzigen:
            flash('Welkom! Gelieve uw tijdelijk wachtwoord te wijzigen.', 'info')
            return redirect(url_for('auth.wachtwoord_wijzigen'))

        if len(active_memberships) == 1:
            flash(f'Welkom! Ingelogd bij {active_memberships[0].organisatie.naam}.', 'success')
            next_page = request.args.get('next')
            if _is_veilige_redirect(next_page):
                return redirect(next_page)
            return redirect(url_for('reg.lijst'))
        else:
            next_page = request.args.get('next')
            return redirect(url_for('auth.select_org', next=next_page))

    return render_template('auth/login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('U bent uitgelogd.', 'info')
    return redirect(url_for('auth.login'))


_EMAIL_REGEX = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


@auth_bp.route('/wachtwoord', methods=['GET', 'POST'])
@login_required
@limiter.limit("10 per minute")
def wachtwoord_wijzigen():
    from utils.tenant import get_huidige_organisatie_id
    from models.functie import Functie
    org_id = get_huidige_organisatie_id()
    beschikbare_functies = (
        Functie.query.filter_by(organisatie_id=org_id, actief=True).order_by(Functie.volgorde, Functie.naam).all()
        if org_id else []
    )
    toegekende_functie_ids = [f.id for f in current_user.get_functies_voor_organisatie(org_id)] if org_id else []

    if request.method == 'POST':
        huidig = request.form.get('huidig_wachtwoord', '')
        nieuw = request.form.get('nieuw_wachtwoord', '')
        bevestig = request.form.get('bevestig_wachtwoord', '')
        email = request.form.get('email', '').strip().lower()

        telefoonnummer = request.form.get('telefoonnummer', '').strip() or None
        functie_ids = [int(x) for x in request.form.getlist('functie_ids') if x.isdigit()]

        # E-mail valideren als ingevuld
        if email and not _EMAIL_REGEX.match(email):
            flash('Ongeldig e-mailadres.', 'danger')
            return render_template('auth/change_password.html', form_data=request.form, beschikbare_functies=beschikbare_functies, toegekende_functie_ids=toegekende_functie_ids)

        # Wachtwoordwijziging is optioneel indien de gebruiker het niet MOET wijzigen
        wachtwoord_gewijzigd = False
        if huidig or nieuw or bevestig or current_user.moet_wachtwoord_wijzigen:
            wachtwoord_gewijzigd = True
            if not current_user.moet_wachtwoord_wijzigen:
                if not check_password_hash(current_user.wachtwoord_hash, huidig):
                    flash('Huidig wachtwoord is onjuist.', 'danger')
                    return render_template('auth/change_password.html', form_data=request.form, beschikbare_functies=beschikbare_functies, toegekende_functie_ids=toegekende_functie_ids)

        # Controleer of e-mail al door iemand anders gebruikt wordt
        if email and User.query.filter(User.email == email, User.id != current_user.id).first():
            flash('Dit e-mailadres is al in gebruik door een andere gebruiker.', 'danger')
            return render_template('auth/change_password.html', form_data=request.form, beschikbare_functies=beschikbare_functies, toegekende_functie_ids=toegekende_functie_ids)

        # Wachtwoord valideren (alleen als er effectief een nieuw wachtwoord is opgegeven)
        if wachtwoord_gewijzigd:
            if current_user.moet_wachtwoord_wijzigen and not nieuw:
                flash('Nieuw wachtwoord is verplicht.', 'danger')
                return render_template('auth/change_password.html', form_data=request.form, beschikbare_functies=beschikbare_functies, toegekende_functie_ids=toegekende_functie_ids)

            if nieuw != bevestig:
                flash('De nieuwe wachtwoorden komen niet overeen.', 'danger')
                return render_template('auth/change_password.html', form_data=request.form, beschikbare_functies=beschikbare_functies, toegekende_functie_ids=toegekende_functie_ids)

            fouten = _valideer_wachtwoord(nieuw)
            if fouten:
                for f in fouten:
                    flash(f, 'danger')
                return render_template('auth/change_password.html', form_data=request.form, beschikbare_functies=beschikbare_functies, toegekende_functie_ids=toegekende_functie_ids)

            current_user.wachtwoord_hash = generate_password_hash(nieuw)
            current_user.moet_wachtwoord_wijzigen = False

        current_user.email = email
        current_user.telefoonnummer = telefoonnummer

        if org_id:
            current_user.functies = [f for f in current_user.functies if f.organisatie_id != org_id]
            if functie_ids:
                gekozen = Functie.query.filter(Functie.organisatie_id == org_id, Functie.id.in_(functie_ids)).all()
                current_user.functies.extend(gekozen)

        db.session.commit()

        if not session.get('organisatie_id') and current_user.rol != 'platformbeheerder':
            active_memberships = [
                uo for uo in current_user.user_organisaties 
                if uo.actief and uo.organisatie and uo.organisatie.actief and uo.organisatie.slug != 'sjabloon'
            ]
            if len(active_memberships) == 1:
                session['organisatie_id'] = active_memberships[0].organisatie_id
            elif len(active_memberships) > 1:
                return redirect(url_for('auth.select_org'))

        if wachtwoord_gewijzigd:
            flash('Wachtwoord succesvol gewijzigd.', 'success')
        else:
            flash('Gegevens succesvol bijgewerkt.', 'success')
        return redirect(url_for('reg.lijst'))

    return render_template('auth/change_password.html', beschikbare_functies=beschikbare_functies, toegekende_functie_ids=toegekende_functie_ids)


@auth_bp.route('/select-organisatie', methods=['GET', 'POST'])
@login_required
def select_org():
    if current_user.rol == 'platformbeheerder':
        from models.organisatie import Organisatie
        active_orgs = Organisatie.query.filter_by(actief=True).all()
        class MockMembership:
            def __init__(self, org):
                self.organisatie_id = org.id
                self.organisatie = org
        memberships = [MockMembership(o) for o in active_orgs]
    else:
        memberships = [
            uo for uo in current_user.user_organisaties 
            if uo.actief and uo.organisatie.actief and uo.organisatie.slug != 'sjabloon'
        ]
    
    if not memberships:
        logout_user()
        flash('Er zijn geen actieve organisaties beschikbaar.', 'danger')
        return redirect(url_for('auth.login'))
        
    if request.method == 'POST':
        org_id = request.form.get('organisatie_id', type=int)
        membership = next((m for m in memberships if m.organisatie_id == org_id), None)
        if membership:
            session['organisatie_id'] = org_id
            flash(f'Ingelogd bij organisatie: {membership.organisatie.naam}', 'success')
            next_page = request.args.get('next')
            if _is_veilige_redirect(next_page):
                return redirect(next_page)
            if membership.organisatie.slug == 'sjabloon':
                return redirect(url_for('admin.leeftijdscategorieën'))
            return redirect(url_for('reg.lijst'))
        else:
            flash('Ongeldige organisatie selectie.', 'danger')
            
    return render_template('auth/select_org.html', memberships=memberships)



MENU_ENDPOINT_MAP = {
    # Platformbeheer
    'platform.dashboard': 'platform.dashboard',
    'platform.systeemmonitor': 'platform.systeemmonitor',
    'platform.organisaties': 'platform.organisaties',
    'platform.organisatie_nieuw': 'platform.organisaties',
    'platform.organisatie_wijzigen': 'platform.organisaties',
    'platform.organisatie_toggle': 'platform.organisaties',
    'platform.organisatie_verwijderen': 'platform.organisaties',
    'platform.koppelingen': 'platform.koppelingen',
    'platform.koppeling_toggle': 'platform.koppelingen',
    'platform.koppeling_verwijderen': 'platform.koppelingen',
    'platform.emailsjablonen': 'platform.emailsjablonen',
    'platform.emailsjablonen_wijzigen': 'platform.emailsjablonen',
    'platform.emailsjablonen_herstellen': 'platform.emailsjablonen',
    'platform.communicatie': 'platform.communicatie',
    'platform.communicatie_log_detail': 'platform.communicatie',
    'platform.vraagcategorieen': 'platform.vraagcategorieen',
    'platform.vraagcategorie_nieuw': 'platform.vraagcategorieen',
    'platform.vraagcategorie_wijzigen': 'platform.vraagcategorieen',
    'platform.vraagcategorie_toggle': 'platform.vraagcategorieen',
    'platform.vraagcategorie_volgorde': 'platform.vraagcategorieen',
    'platform.vraagcategorie_verwijderen': 'platform.vraagcategorieen',
    'platform.vraagclassificaties': 'platform.vraagclassificaties',
    'platform.vraagclassificatie_wijzigen': 'platform.vraagclassificaties',
    'platform.vraagclassificatie_heranalyse': 'platform.vraagclassificaties',
    'platform.vraagclassificaties_batch_analyse': 'platform.vraagclassificaties',
    'platform.vraagclassificaties_batch_status': 'platform.vraagclassificaties',
    'admin.audit_log': 'admin.audit_log',
    'admin.audit_log_opschonen': 'admin.audit_log',

    # Registraties
    'reg.lijst': 'reg.lijst',
    'reg.index': 'reg.lijst',
    'reg.bekijken': 'reg.lijst',
    'reg.wijzigen': 'reg.lijst',
    'reg.verwijderen': 'reg.lijst',
    'reg.nieuw': 'reg.lijst',
    'reg.snel': 'reg.snel',
    'agenda.lijst': 'agenda.lijst',
    'agenda.nieuw': 'agenda.lijst',
    'agenda.wijzigen': 'agenda.lijst',
    'agenda.verwijderen': 'agenda.lijst',
    'eval.resultaten': 'eval.resultaten',
    'eval.sessie_detail': 'eval.resultaten',
    'eval.reactie_bewerken': 'eval.resultaten',
    'eval.verstuur_uitnodigingen': 'eval.resultaten',
    'eval.verstuur_herinneringen': 'eval.resultaten',

    # Documentbeheer
    'doc.index': 'doc.index',
    'doc.bekijken': 'doc.index',
    'doc.bewerken': 'doc.index',
    'doc.download': 'doc.index',
    'doc.map_hernoemen': 'doc.index',
    'doc.map_toevoegen': 'doc.index',
    'doc.map_verwijderen': 'doc.index',
    'doc.overschrijven': 'doc.index',
    'doc.upload': 'doc.index',
    'doc.verwijderen': 'doc.index',

    # Beheer
    'admin.gebruikers': 'admin.gebruikers',
    'admin.gebruiker_nieuw': 'admin.gebruikers',
    'admin.gebruiker_wijzigen': 'admin.gebruikers',
    'admin.gebruiker_toggle': 'admin.gebruikers',
    'admin.gebruiker_verwijderen': 'admin.gebruikers',
    'admin.groepen_overzicht': 'admin.groepen_overzicht',
    'admin.groep_nieuw': 'admin.groepen_overzicht',
    'admin.groep_bewerken': 'admin.groepen_overzicht',
    'admin.groep_toggle': 'admin.groepen_overzicht',
    'admin.groep_verwijderen': 'admin.groepen_overzicht',
    'admin.digidokters': 'admin.digidokters',
    'admin.digidokter_nieuw': 'admin.digidokters',
    'admin.digidokter_wijzigen': 'admin.digidokters',
    'admin.digidokter_toggle': 'admin.digidokters',
    'admin.digidokter_volgorde': 'admin.digidokters',
    'admin.digidokter_verwijderen': 'admin.digidokters',
    'admin.communicatie': 'admin.communicatie',
    'admin.activiteitstypes': 'admin.activiteitstypes',
    'admin.activiteitstype_nieuw': 'admin.activiteitstypes',
    'admin.activiteitstype_wijzigen': 'admin.activiteitstypes',
    'admin.activiteitstype_toggle': 'admin.activiteitstypes',
    'admin.activiteitstype_volgorde': 'admin.activiteitstypes',
    'admin.activiteitstype_verwijderen': 'admin.activiteitstypes',
    'eval.overzicht': 'eval.overzicht',
    'eval.formulier_bewerken': 'eval.overzicht',
    'eval.vraag_bewerken': 'eval.overzicht',
    'eval.vraag_toevoegen': 'eval.overzicht',
    'eval.vraag_verwijderen': 'eval.overzicht',
    'eval.vraag_volgorde': 'eval.overzicht',
    'admin.locaties': 'admin.locaties',
    'admin.locatie_nieuw': 'admin.locaties',
    'admin.locatie_wijzigen': 'admin.locaties',
    'admin.locatie_toggle': 'admin.locaties',
    'admin.locatie_volgorde': 'admin.locaties',
    'admin.locatie_verwijderen': 'admin.locaties',
    'admin.leeftijdscategorieën': 'admin.leeftijdscategorieën',
    'admin.leeftijdscategorie_nieuw': 'admin.leeftijdscategorieën',
    'admin.leeftijdscategorie_wijzigen': 'admin.leeftijdscategorieën',
    'admin.leeftijdscategorie_toggle': 'admin.leeftijdscategorieën',
    'admin.leeftijdscategorie_volgorde': 'admin.leeftijdscategorieën',
    'admin.leeftijdscategorie_verwijderen': 'admin.leeftijdscategorieën',
    'admin.toestellen': 'admin.toestellen',
    'admin.toestel_nieuw': 'admin.toestellen',
    'admin.toestel_wijzigen': 'admin.toestellen',
    'admin.toestel_toggle': 'admin.toestellen',
    'admin.toestel_volgorde': 'admin.toestellen',
    'admin.toestel_verwijderen': 'admin.toestellen',
    'admin.herkomsten': 'admin.herkomsten',
    'admin.herkomst_nieuw': 'admin.herkomsten',
    'admin.herkomst_wijzigen': 'admin.herkomsten',
    'admin.herkomst_toggle': 'admin.herkomsten',
    'admin.herkomst_volgorde': 'admin.herkomsten',
    'admin.herkomst_verwijderen': 'admin.herkomsten',
    'admin.genderidentiteiten': 'admin.genderidentiteiten',
    'admin.genderidentiteit_nieuw': 'admin.genderidentiteiten',
    'admin.genderidentiteit_wijzigen': 'admin.genderidentiteiten',
    'admin.genderidentiteit_toggle': 'admin.genderidentiteiten',
    'admin.genderidentiteit_volgorde': 'admin.genderidentiteiten',
    'admin.genderidentiteit_verwijderen': 'admin.genderidentiteiten',
    'admin.functies': 'admin.functies',
    'admin.functie_nieuw': 'admin.functies',
    'admin.functie_wijzigen': 'admin.functies',
    'admin.functie_toggle': 'admin.functies',
    'admin.functie_volgorde': 'admin.functies',
    'admin.functie_verwijderen': 'admin.functies',
    'admin.resultaten': 'admin.resultaten',
    'admin.resultaat_nieuw': 'admin.resultaten',
    'admin.resultaat_wijzigen': 'admin.resultaten',
    'admin.resultaat_toggle': 'admin.resultaten',
    'admin.resultaat_volgorde': 'admin.resultaten',
    'admin.resultaat_verwijderen': 'admin.resultaten',
    'admin.emailsjablonen': 'admin.emailsjablonen',
    'admin.emailsjablonen_wijzigen': 'admin.emailsjablonen',
    'admin.emailsjablonen_herstellen': 'admin.emailsjablonen',
    'admin.backup': 'admin.backup',
    'admin.restore': 'admin.restore',

    # Data
    'ie.exporteer': 'ie.exporteer',
    'ie.importeer': 'ie.exporteer',
    'ie.import_log': 'ie.exporteer',
    'stats.overzicht': 'stats.overzicht',

    # Algemeen
    'app_docs.index': 'app_docs.index',
    'app_docs.bekijken': 'app_docs.index',
    'app_docs.bewerken': 'app_docs.index',
    'app_docs.download': 'app_docs.index',
    'app_docs.map_hernoemen': 'app_docs.index',
    'app_docs.map_toevoegen': 'app_docs.index',
    'app_docs.map_verwijderen': 'app_docs.index',
    'app_docs.overschrijven': 'app_docs.index',
    'app_docs.upload': 'app_docs.index',
    'app_docs.verwijderen': 'app_docs.index',
    'feedback.formulier': 'feedback.formulier',
    'feedback.nieuw': 'feedback.formulier',
    'feedback.lijst': 'feedback.lijst',
    'feedback.detail': 'feedback.lijst',
}


def _is_allowed_in_sjabloon(endpoint: str) -> bool:
    """Controleer of een endpoint is toegestaan binnen de sjabloon-organisatie."""
    allowed_sjabloon_prefixes = (
        'static', 'service_worker', 'ping', 'auth.', 'platform.', 'app_docs.', 'feedback.'
    )
    allowed_sjabloon_endpoints = (
        'admin.leeftijdscategorieën', 'admin.toestellen', 'admin.activiteitstypes',
        'admin.locaties', 'admin.herkomsten', 'admin.genderidentiteiten',
        'admin.functies', 'admin.groepen_overzicht', 'eval.overzicht'
    )
    return any(endpoint.startswith(p) for p in allowed_sjabloon_prefixes) or (endpoint in allowed_sjabloon_endpoints)


def _bepaal_switch_redirect_url(target_org, current_endpoint: str | None = None, next_url: str | None = None) -> str:
    """Bepaal de juiste redirect-URL bij het wisselen van organisatie, waarbij de menukeuze behouden blijft."""
    # Als next_url niet expliciet meegegeven is, probeer request.referrer
    if not next_url and request.referrer:
        parsed_ref = urlparse(request.referrer)
        if parsed_ref.netloc == request.host or not parsed_ref.netloc:
            ref_path = parsed_ref.path
            if parsed_ref.query:
                ref_path += f"?{parsed_ref.query}"
            if _is_veilige_redirect(ref_path):
                next_url = ref_path

    # Probeer endpoint te achterhalen uit next_url indien niet expliciet meegegeven
    if not current_endpoint and next_url and _is_veilige_redirect(next_url):
        try:
            adapter = current_app.url_map.bind('localhost')
            matched_endpoint, _ = adapter.match(urlparse(next_url).path, method='GET')
            current_endpoint = matched_endpoint
        except Exception:
            pass

    # Negeer auth endpoints
    if current_endpoint in ('auth.switch_organisatie', 'auth.login', 'auth.logout', 'auth.select_org'):
        current_endpoint = None
        next_url = None

    target_menu_endpoint = MENU_ENDPOINT_MAP.get(current_endpoint) if current_endpoint else None

    is_sjabloon = bool(target_org and getattr(target_org, 'slug', None) == 'sjabloon')

    if is_sjabloon:
        if target_menu_endpoint and _is_allowed_in_sjabloon(target_menu_endpoint):
            if current_endpoint == target_menu_endpoint and next_url and _is_veilige_redirect(next_url):
                return next_url
            try:
                return url_for(target_menu_endpoint)
            except Exception:
                pass
        return url_for('admin.leeftijdscategorieën')

    # Reguliere organisatie
    if target_menu_endpoint:
        if current_endpoint == target_menu_endpoint and next_url and _is_veilige_redirect(next_url):
            return next_url
        try:
            return url_for(target_menu_endpoint)
        except Exception:
            pass

    return url_for('reg.lijst')


@auth_bp.route('/switch-organisatie', methods=['POST'])
@login_required
def switch_organisatie():
    org_id = request.form.get('organisatie_id', type=int)
    current_endpoint = request.form.get('current_endpoint')
    next_url = request.form.get('next')
    target_org = None
    if current_user.rol == 'platformbeheerder':
        from models.organisatie import Organisatie
        org = Organisatie.query.filter_by(id=org_id, actief=True).first()
        if org:
            session['organisatie_id'] = org_id
            target_org = org
            flash(f'Gewisseld naar organisatie: {org.naam}', 'success')
        else:
            flash('Ongeldige organisatie.', 'danger')
    else:
        active_memberships = [
            uo for uo in current_user.user_organisaties 
            if uo.actief and uo.organisatie.actief and uo.organisatie.slug != 'sjabloon'
        ]
        membership = next((uo for uo in active_memberships if uo.organisatie_id == org_id), None)
        if membership:
            session['organisatie_id'] = org_id
            target_org = membership.organisatie
            flash(f'Gewisseld naar organisatie: {membership.organisatie.naam}', 'success')
        else:
            flash('U heeft geen toegang tot deze organisatie.', 'danger')
        
    return redirect(_bepaal_switch_redirect_url(target_org, current_endpoint=current_endpoint, next_url=next_url))


@auth_bp.route('/wachtwoord-vergeten', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def wachtwoord_vergeten():
    if current_user.is_authenticated:
        return redirect(url_for('reg.lijst'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        if not email:
            flash('Vul uw e-mailadres in.', 'danger')
            return render_template('auth/wachtwoord_vergeten.html')

        user = User.query.filter(db.func.lower(User.email) == email).first()

        if not user:
            flash('E-mailadres is niet bekend. Neem contact op met uw beheerder.', 'danger')
            return render_template('auth/wachtwoord_vergeten.html')

        if not user.actief:
            flash('Uw account is gedeactiveerd. Neem contact op met uw beheerder.', 'danger')
            return render_template('auth/wachtwoord_vergeten.html')

        # Code genereren
        import secrets
        from datetime import timedelta
        from utils.mail import verstuur_email
        from flask import current_app
 
        code = f"{secrets.randbelow(900000) + 100000:06d}"
        user.reset_code = code
        user.reset_code_verloopt_op = datetime.now(timezone.utc) + timedelta(minutes=30)
        user.reset_pogingen = 0
        db.session.commit()

        # E-mail versturen
        onderwerp = "Herstelcode wachtwoord Digidokters"
        vervaltijd_str = user.reset_code_verloopt_op.replace(tzinfo=timezone.utc).astimezone().strftime('%H:%M:%S')
        inhoud = (
            f"Beste {user.naam},\n\n"
            f"U heeft een verzoek ingediend om uw wachtwoord voor Digidokters te herstellen.\n"
            f"Gebruik de volgende 6-cijferige verificatiecode in de app:\n\n"
            f"   {code}\n\n"
            f"Deze code is 30 minuten geldig (tot {vervaltijd_str}).\n\n"
            f"Als u dit verzoek niet heeft ingediend, kunt u deze e-mail veilig negeren.\n\n"
            f"Met vriendelijke groet,\n"
            f"Digidokters Systeem"
        )
        
        try:
            verstuur_email(user.email, onderwerp, inhoud)
            session['reset_username'] = user.naam
            flash('Er is een herstelcode verstuurd naar uw e-mailadres.', 'success')
            return redirect(url_for('auth.wachtwoord_vergeten_verifieer'))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Fout bij het versturen van herstelcode-mail: {str(e)}")
            flash('Fout bij het versturen van de e-mail. Controleer de mailinstellingen of neem contact op met de beheerder.', 'danger')

    return render_template('auth/wachtwoord_vergeten.html')


@auth_bp.route('/wachtwoord-vergeten/verifieer', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def wachtwoord_vergeten_verifieer():
    if current_user.is_authenticated:
        return redirect(url_for('reg.lijst'))

    naam = session.get('reset_username')
    if not naam:
        flash('Start de wachtwoord vergeten procedure opnieuw.', 'warning')
        return redirect(url_for('auth.wachtwoord_vergeten'))

    if request.method == 'POST':
        code = request.form.get('code', '').strip()
        nieuw_wachtwoord = request.form.get('nieuw_wachtwoord', '')
        bevestig_wachtwoord = request.form.get('bevestig_wachtwoord', '')

        if not code or not nieuw_wachtwoord or not bevestig_wachtwoord:
            flash('Vul alle velden in.', 'danger')
            return render_template('auth/wachtwoord_vergeten_verifieer.html', naam=naam)

        if nieuw_wachtwoord != bevestig_wachtwoord:
            flash('De nieuwe wachtwoorden komen niet overeen.', 'danger')
            return render_template('auth/wachtwoord_vergeten_verifieer.html', naam=naam)

        user = User.query.filter_by(naam=naam).first()
        if not user:
            flash('Gebruiker niet gevonden.', 'danger')
            return redirect(url_for('auth.wachtwoord_vergeten'))

        # Code controleren
        if not user.reset_code_verloopt_op or user.reset_code_verloopt_op.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
            flash('De herstelcode is verlopen. Vraag een nieuwe code aan.', 'danger')
            return render_template('auth/wachtwoord_vergeten_verifieer.html', naam=naam)

        if not user.reset_code or user.reset_code != code:
            user.reset_pogingen += 1
            if user.reset_pogingen >= 5:
                user.reset_code = None
                user.reset_code_verloopt_op = None
                user.reset_pogingen = 0
                db.session.commit()
                session.pop('reset_username', None)
                flash('Te veel mislukte pogingen. Vraag een nieuwe code aan.', 'danger')
                return redirect(url_for('auth.wachtwoord_vergeten'))
            else:
                db.session.commit()
                resterend = 5 - user.reset_pogingen
                flash(f'Ongeldige herstelcode. Je hebt nog {resterend} pogingen over.', 'danger')
                return render_template('auth/wachtwoord_vergeten_verifieer.html', naam=naam)

        # Wachtwoord validatie
        fouten = _valideer_wachtwoord(nieuw_wachtwoord)
        if fouten:
            for f in fouten:
                flash(f, 'danger')
            return render_template('auth/wachtwoord_vergeten_verifieer.html', naam=naam)

        # Resetten van wachtwoord
        user.wachtwoord_hash = generate_password_hash(nieuw_wachtwoord)
        user.reset_code = None
        user.reset_code_verloopt_op = None
        user.reset_pogingen = 0
        user.moet_wachtwoord_wijzigen = False
        db.session.commit()

        session.pop('reset_username', None)
        flash('Uw wachtwoord is succesvol gewijzigd. U kunt nu inloggen.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/wachtwoord_vergeten_verifieer.html', naam=naam)