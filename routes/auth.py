"""Authenticatie routes: login, logout, wachtwoord wijzigen."""
from datetime import datetime, timezone
from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from extensions import db
from models.user import User

auth_bp = Blueprint('auth', __name__)


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
def login():
    if current_user.is_authenticated:
        return redirect(url_for('reg.lijst'))

    if request.method == 'POST':
        gebruikersnaam = request.form.get('gebruikersnaam', '').strip().lower()
        wachtwoord = request.form.get('wachtwoord', '')

        gebruiker = User.query.filter_by(gebruikersnaam=gebruikersnaam).first()

        if not gebruiker or not check_password_hash(gebruiker.wachtwoord_hash, wachtwoord):
            flash('Ongeldige gebruikersnaam of wachtwoord.', 'danger')
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

        next_page = request.args.get('next')
        return redirect(next_page or url_for('reg.lijst'))

    return render_template('auth/login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('U bent uitgelogd.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/wachtwoord', methods=['GET', 'POST'])
@login_required
def wachtwoord_wijzigen():
    if request.method == 'POST':
        huidig = request.form.get('huidig_wachtwoord', '')
        nieuw = request.form.get('nieuw_wachtwoord', '')
        bevestig = request.form.get('bevestig_wachtwoord', '')

        # Controleer huidig wachtwoord (tenzij verplichte reset)
        if not current_user.moet_wachtwoord_wijzigen:
            if not check_password_hash(current_user.wachtwoord_hash, huidig):
                flash('Huidig wachtwoord is onjuist.', 'danger')
                return render_template('auth/change_password.html')

        if nieuw != bevestig:
            flash('De nieuwe wachtwoorden komen niet overeen.', 'danger')
            return render_template('auth/change_password.html')

        fouten = _valideer_wachtwoord(nieuw)
        if fouten:
            for f in fouten:
                flash(f, 'danger')
            return render_template('auth/change_password.html')

        current_user.wachtwoord_hash = generate_password_hash(nieuw)
        current_user.moet_wachtwoord_wijzigen = False
        db.session.commit()
        flash('Wachtwoord succesvol gewijzigd.', 'success')
        return redirect(url_for('reg.lijst'))

    return render_template('auth/change_password.html')