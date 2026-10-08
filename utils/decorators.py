"""Decorators voor toegangsbeheer."""
from functools import wraps
from flask import flash, redirect, url_for, session
from flask_login import current_user
from models.constants import ROLE_PLATFORMBEHEERDER, ACCESS_WRITE
from utils.permissions import has_permission, require_permission, permission_required, can_read, can_write, get_user_permissions_voor_organisatie


def admin_required(f):
    """Decorator: vereist beheerdersrechten (schrijfrechten op gebruikersbeheer) binnen de actieve organisatie."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        
        if current_user.rol == ROLE_PLATFORMBEHEERDER:
            return f(*args, **kwargs)

        org_id = session.get('organisatie_id')
        if not org_id:
            return redirect(url_for('auth.select_org'))
            
        # Dynamische check op 'gebruikers' bewerkrechten
        if has_permission('gebruikers', 'write', user=current_user, org_id=org_id):
            return f(*args, **kwargs)

        flash('U heeft geen toegang tot deze pagina.', 'danger')
        return redirect(url_for('reg.lijst'))
    return decorated_function


def actief_required(f):
    """Decorator: vereist dat de gebruiker actief is."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.is_authenticated and not current_user.actief:
            flash('Uw account is gedeactiveerd. Contacteer de beheerder.', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


def platform_admin_required(f):
    """Decorator: vereist de globale rol 'platformbeheerder'."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        if current_user.rol != ROLE_PLATFORMBEHEERDER:
            flash('U heeft geen toegang tot deze pagina.', 'danger')
            return redirect(url_for('reg.lijst'))
        return f(*args, **kwargs)
    return decorated_function


def writer_required(f):
    """Decorator: vereist dat de gebruiker schrijfrechten heeft binnen de actieve organisatie."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        
        if current_user.rol == ROLE_PLATFORMBEHEERDER:
            return f(*args, **kwargs)

        org_id = session.get('organisatie_id')
        if not org_id:
            return redirect(url_for('auth.select_org'))
            
        uo = next((x for x in current_user.user_organisaties if x.organisatie_id == org_id and x.actief and x.organisatie.actief), None)
        if not uo:
            flash('U heeft geen toegang tot deze organisatie.', 'danger')
            return redirect(url_for('reg.lijst'))

        # Controleer of de gebruiker ten minste één schrijfrecht heeft (geen pure lezer)
        perms = get_user_permissions_voor_organisatie(current_user, org_id)
        has_any_write = any(lvl == ACCESS_WRITE for lvl in perms.values())
        if not has_any_write:
            flash('U heeft geen schrijfrechten voor deze organisatie.', 'danger')
            return redirect(url_for('reg.lijst'))
        return f(*args, **kwargs)
    return decorated_function

