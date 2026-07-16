"""Authenticatie routes: login, logout, wachtwoord wijzigen."""
import re
from datetime import datetime, timezone
from urllib.parse import urlparse
from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from extensions import db, limiter
from models.user import User

auth_bp = Blueprint('auth', __name__)


def _is_veilige_redirect(url: str) -> bool:
    """Controleer of url een relatief pad binnen deze app is (geen open redirect)."""
    if not url:
        return False
    parsed = urlparse(url)
    return (
        parsed.scheme == ''
        and parsed.netloc == ''
        and url.startswith('/')
        and not url.startswith('//')
    )


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
        naam = request.form.get('naam', '').strip()
        wachtwoord = request.form.get('wachtwoord', '')

        gebruiker = User.query.filter(db.func.lower(User.naam) == naam.lower()).first()

        if not gebruiker or not check_password_hash(gebruiker.wachtwoord_hash, wachtwoord):
            flash('Ongeldige naam of wachtwoord.', 'danger')
            return render_template('auth/login.html')

        if not gebruiker.actief:
            flash('Uw account is gedeactiveerd. Contacteer de beheerder.', 'danger')
            return render_template('auth/login.html')

        login_user(gebruiker, remember=request.form.get('onthoud') == 'on')
        gebruiker.laatste_login = datetime.now(timezone.utc)
        db.session.commit()

        # Verplicht wachtwoord wijzigen
        if gebruiker.moet_wachtwoord_wijzigen:
            flash('Welkom! Gelieve uw tijdelijk wachtwoord te wijzigen.', 'info')
            return redirect(url_for('auth.wachtwoord_wijzigen'))

        # Organisatie context instellen
        if gebruiker.rol == 'platformbeheerder':
            flash(f'Welkom, platformbeheerder {gebruiker.naam}!', 'success')
            return redirect(url_for('platform.dashboard'))

        active_memberships = [uo for uo in gebruiker.user_organisaties if uo.actief and uo.organisatie.actief]
        if not active_memberships:
            logout_user()
            flash('Uw account is niet gekoppeld aan een actieve organisatie. Contacteer de beheerder.', 'danger')
            return redirect(url_for('auth.login'))

        if len(active_memberships) == 1:
            session['organisatie_id'] = active_memberships[0].organisatie_id
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
def wachtwoord_wijzigen():
    if request.method == 'POST':
        huidig = request.form.get('huidig_wachtwoord', '')
        nieuw = request.form.get('nieuw_wachtwoord', '')
        bevestig = request.form.get('bevestig_wachtwoord', '')
        email = request.form.get('email', '').strip().lower() or None

        wachtwoord_verplicht = current_user.moet_wachtwoord_wijzigen
        wachtwoord_gewijzigd = wachtwoord_verplicht or nieuw or bevestig

        # Controleer huidig wachtwoord (tenzij verplichte reset). Nodig zodra
        # er iets wijzigt (wachtwoord én/of e-mailadres), als beveiliging tegen
        # account-overname via een losstaande sessie.
        if not wachtwoord_verplicht:
            if not check_password_hash(current_user.wachtwoord_hash, huidig):
                flash('Huidig wachtwoord is onjuist.', 'danger')
                return render_template('auth/change_password.html', form_data=request.form)

        # E-mailadres valideren
        if email and not _EMAIL_REGEX.match(email):
            flash('Voer een geldig e-mailadres in.', 'danger')
            return render_template('auth/change_password.html', form_data=request.form)

        if email and User.query.filter(User.email == email, User.id != current_user.id).first():
            flash('Dit e-mailadres is al in gebruik door een andere gebruiker.', 'danger')
            return render_template('auth/change_password.html', form_data=request.form)

        # Wachtwoord valideren (alleen als er effectief een nieuw wachtwoord is opgegeven)
        if wachtwoord_gewijzigd:
            if nieuw != bevestig:
                flash('De nieuwe wachtwoorden komen niet overeen.', 'danger')
                return render_template('auth/change_password.html', form_data=request.form)

            fouten = _valideer_wachtwoord(nieuw)
            if fouten:
                for f in fouten:
                    flash(f, 'danger')
                return render_template('auth/change_password.html', form_data=request.form)

            current_user.wachtwoord_hash = generate_password_hash(nieuw)
            current_user.moet_wachtwoord_wijzigen = False

        current_user.email = email
        db.session.commit()

        if wachtwoord_gewijzigd:
            flash('Wachtwoord succesvol gewijzigd.', 'success')
        else:
            flash('Gegevens succesvol bijgewerkt.', 'success')
        return redirect(url_for('reg.lijst'))

    return render_template('auth/change_password.html')


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
        memberships = [uo for uo in current_user.user_organisaties if uo.actief and uo.organisatie.actief]
    
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
            return redirect(url_for('reg.lijst'))
        else:
            flash('Ongeldige organisatie selectie.', 'danger')
            
    return render_template('auth/select_org.html', memberships=memberships)


@auth_bp.route('/switch-organisatie', methods=['POST'])
@login_required
def switch_organisatie():
    org_id = request.form.get('organisatie_id', type=int)
    if current_user.rol == 'platformbeheerder':
        from models.organisatie import Organisatie
        org = Organisatie.query.filter_by(id=org_id, actief=True).first()
        if org:
            session['organisatie_id'] = org_id
            flash(f'Gewisseld naar organisatie: {org.naam}', 'success')
        else:
            flash('Ongeldige organisatie.', 'danger')
    else:
        active_memberships = [uo for uo in current_user.user_organisaties if uo.actief and uo.organisatie.actief]
        membership = next((uo for uo in active_memberships if uo.organisatie_id == org_id), None)
        if membership:
            session['organisatie_id'] = org_id
            flash(f'Gewisseld naar organisatie: {membership.organisatie.naam}', 'success')
        else:
            flash('U heeft geen toegang tot deze organisatie.', 'danger')
        
    return redirect(url_for('reg.lijst'))