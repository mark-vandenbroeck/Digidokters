"""Decorators voor toegangsbeheer."""
from functools import wraps
from flask import flash, redirect, url_for
from flask_login import current_user


def admin_required(f):
    """Decorator: vereist de rol 'beheerder'."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        if not current_user.is_beheerder():
            flash('U heeft geen toegang tot deze pagina.', 'danger')
            return redirect(url_for('reg.lijst'))
        return f(*args, **kwargs)
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
