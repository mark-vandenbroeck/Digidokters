"""Beheer routes: gebruikers, digidokters, leeftijdscategorieën, toestellen."""
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required
from werkzeug.security import generate_password_hash
from extensions import db
from models.user import User
from models.digidokter import Digidokter
from models.age_category import AgeCategory
from models.device import Device
from utils.decorators import admin_required

admin_bp = Blueprint('admin', __name__, url_prefix='/beheer')


# ─── Gebruikers ─────────────────────────────────────────────────────────────

@admin_bp.route('/gebruikers')
@login_required
@admin_required
def gebruikers():
    users = User.query.order_by(User.naam).all()
    return render_template('admin/users.html', users=users)


@admin_bp.route('/gebruikers/nieuw', methods=['GET', 'POST'])
@login_required
@admin_required
def gebruiker_nieuw():
    if request.method == 'POST':
        naam = request.form.get('naam', '').strip()
        email = request.form.get('email', '').strip().lower() or None
        rol = request.form.get('rol', 'medewerker')
        tijdelijk_ww = request.form.get('wachtwoord', '').strip()

        if not naam or not tijdelijk_ww:
            flash('Naam en wachtwoord zijn verplicht.', 'danger')
            return render_template('admin/user_form.html', actie='Nieuw', user=None)

        if User.query.filter(db.func.lower(User.naam) == naam.lower()).first():
            flash('Er bestaat al een gebruiker met deze naam. Gebruik een unieke naam (bv. met achternaam).', 'danger')
            return render_template('admin/user_form.html', actie='Nieuw', user=None,
                                   form_data=request.form)

        if email and User.query.filter_by(email=email).first():
            flash('Dit e-mailadres is al in gebruik.', 'danger')
            return render_template('admin/user_form.html', actie='Nieuw', user=None,
                                   form_data=request.form)

        user = User(
            naam=naam,
            email=email,
            wachtwoord_hash=generate_password_hash(tijdelijk_ww),
            rol=rol,
            actief=request.form.get('actief') == 'on',
            moet_wachtwoord_wijzigen=True,
        )
        db.session.add(user)
        db.session.commit()
        flash(f'Gebruiker {naam} aangemaakt. Tijdelijk wachtwoord: {tijdelijk_ww}', 'success')
        return redirect(url_for('admin.gebruikers'))

    return render_template('admin/user_form.html', actie='Nieuw', user=None)


@admin_bp.route('/gebruikers/<int:user_id>/wijzig', methods=['GET', 'POST'])
@login_required
@admin_required
def gebruiker_wijzigen(user_id):
    user = db.get_or_404(User, user_id)

    if request.method == 'POST':
        user.naam = request.form.get('naam', user.naam).strip()
        user.email = request.form.get('email', '').strip().lower() or None
        user.rol = request.form.get('rol', user.rol)
        if user.id != 1:  # Bescherm de eerste beheerder tegen zelf-deactivatie via het formulier
            user.actief = request.form.get('actief') == 'on'
        nieuw_ww = request.form.get('wachtwoord', '').strip()
        if nieuw_ww:
            user.wachtwoord_hash = generate_password_hash(nieuw_ww)
            user.moet_wachtwoord_wijzigen = True
        db.session.commit()
        flash(f'Gebruiker {user.naam} bijgewerkt.', 'success')
        return redirect(url_for('admin.gebruikers'))

    return render_template('admin/user_form.html', actie='Wijzigen', user=user)


@admin_bp.route('/gebruikers/<int:user_id>/toggle')
@login_required
@admin_required
def gebruiker_toggle(user_id):
    user = db.get_or_404(User, user_id)
    if user.id == 1:  # Bescherm de eerste beheerder
        flash('De eerste beheerder kan niet worden gedeactiveerd.', 'warning')
        return redirect(url_for('admin.gebruikers'))
    user.actief = not user.actief
    db.session.commit()
    status = 'geactiveerd' if user.actief else 'gedeactiveerd'
    flash(f'Gebruiker {user.naam} {status}.', 'info')
    return redirect(url_for('admin.gebruikers'))


# ─── Generieke beheer helper ─────────────────────────────────────────────────

def _beheer_lijst(model, template, naam_veld='naam'):
    items = model.query.order_by(getattr(model, 'volgorde'), getattr(model, naam_veld)).all()
    return render_template(template, items=items)


def _beheer_toggle(model, item_id, redirect_endpoint):
    item = db.get_or_404(model, item_id)
    item.actief = not item.actief
    db.session.commit()
    status = 'geactiveerd' if item.actief else 'gedeactiveerd'
    flash(f'{item.naam} {status}.', 'info')
    return redirect(url_for(redirect_endpoint))


def _beheer_volgorde(model, item_id, richting, redirect_endpoint):
    """Verplaats een item omhoog of omlaag in de volgorde."""
    item = db.get_or_404(model, item_id)
    alle = model.query.order_by(model.volgorde, model.naam).all()
    idx = next((i for i, x in enumerate(alle) if x.id == item_id), None)
    if idx is None:
        return redirect(url_for(redirect_endpoint))

    if richting == 'omhoog' and idx > 0:
        buurman = alle[idx - 1]
        item.volgorde, buurman.volgorde = buurman.volgorde, item.volgorde
        if item.volgorde == buurman.volgorde:
            item.volgorde = max(0, buurman.volgorde - 1)
    elif richting == 'omlaag' and idx < len(alle) - 1:
        buurman = alle[idx + 1]
        item.volgorde, buurman.volgorde = buurman.volgorde, item.volgorde
        if item.volgorde == buurman.volgorde:
            item.volgorde = buurman.volgorde + 1

    # Herbereken volgordes
    for i, x in enumerate(model.query.order_by(model.volgorde, model.naam).all()):
        x.volgorde = i
    db.session.commit()
    return redirect(url_for(redirect_endpoint))


# ─── Digidokters ─────────────────────────────────────────────────────────────

@admin_bp.route('/digidokters')
@login_required
@admin_required
def digidokters():
    items = Digidokter.query.order_by(Digidokter.volgorde, Digidokter.naam).all()
    return render_template('admin/digidokters.html', items=items)


@admin_bp.route('/digidokters/nieuw', methods=['GET', 'POST'])
@login_required
@admin_required
def digidokter_nieuw():
    if request.method == 'POST':
        naam = request.form.get('naam', '').strip()
        if not naam:
            flash('Naam is verplicht.', 'danger')
            return render_template('admin/item_form.html', titel='Digidokter', actie='Nieuw',
                                   item=None, terug_url=url_for('admin.digidokters'))
        max_volgorde = db.session.query(db.func.max(Digidokter.volgorde)).scalar() or 0
        db.session.add(Digidokter(naam=naam, volgorde=max_volgorde + 1,
                                  actief=request.form.get('actief') == 'on' if 'actief' in request.form else True))
        db.session.commit()
        flash(f'Digidokter {naam} toegevoegd.', 'success')
        return redirect(url_for('admin.digidokters'))
    return render_template('admin/item_form.html', titel='Digidokter', actie='Nieuw',
                           item=None, terug_url=url_for('admin.digidokters'))


@admin_bp.route('/digidokters/<int:item_id>/wijzig', methods=['GET', 'POST'])
@login_required
@admin_required
def digidokter_wijzigen(item_id):
    item = db.get_or_404(Digidokter, item_id)
    if request.method == 'POST':
        item.naam = request.form.get('naam', item.naam).strip()
        item.actief = request.form.get('actief') == 'on'
        db.session.commit()
        flash(f'{item.naam} bijgewerkt.', 'success')
        return redirect(url_for('admin.digidokters'))
    return render_template('admin/item_form.html', titel='Digidokter', actie='Wijzigen',
                           item=item, terug_url=url_for('admin.digidokters'))


@admin_bp.route('/digidokters/<int:item_id>/toggle')
@login_required
@admin_required
def digidokter_toggle(item_id):
    return _beheer_toggle(Digidokter, item_id, 'admin.digidokters')


@admin_bp.route('/digidokters/<int:item_id>/volgorde/<richting>')
@login_required
@admin_required
def digidokter_volgorde(item_id, richting):
    return _beheer_volgorde(Digidokter, item_id, richting, 'admin.digidokters')


# ─── Leeftijdscategorieën ────────────────────────────────────────────────────

@admin_bp.route('/leeftijdscategorieën')
@login_required
@admin_required
def leeftijdscategorieën():
    items = AgeCategory.query.order_by(AgeCategory.volgorde, AgeCategory.naam).all()
    return render_template('admin/age_categories.html', items=items)


@admin_bp.route('/leeftijdscategorieën/nieuw', methods=['GET', 'POST'])
@login_required
@admin_required
def leeftijdscategorie_nieuw():
    if request.method == 'POST':
        naam = request.form.get('naam', '').strip()
        if not naam:
            flash('Naam is verplicht.', 'danger')
            return render_template('admin/item_form.html', titel='Leeftijdscategorie', actie='Nieuw',
                                   item=None, terug_url=url_for('admin.leeftijdscategorieën'))
        max_volgorde = db.session.query(db.func.max(AgeCategory.volgorde)).scalar() or 0
        db.session.add(AgeCategory(naam=naam, volgorde=max_volgorde + 1,
                                   actief=request.form.get('actief') == 'on' if 'actief' in request.form else True))
        db.session.commit()
        flash(f'Leeftijdscategorie {naam} toegevoegd.', 'success')
        return redirect(url_for('admin.leeftijdscategorieën'))
    return render_template('admin/item_form.html', titel='Leeftijdscategorie', actie='Nieuw',
                           item=None, terug_url=url_for('admin.leeftijdscategorieën'))


@admin_bp.route('/leeftijdscategorieën/<int:item_id>/wijzig', methods=['GET', 'POST'])
@login_required
@admin_required
def leeftijdscategorie_wijzigen(item_id):
    item = db.get_or_404(AgeCategory, item_id)
    if request.method == 'POST':
        item.naam = request.form.get('naam', item.naam).strip()
        item.actief = request.form.get('actief') == 'on'
        db.session.commit()
        flash(f'{item.naam} bijgewerkt.', 'success')
        return redirect(url_for('admin.leeftijdscategorieën'))
    return render_template('admin/item_form.html', titel='Leeftijdscategorie', actie='Wijzigen',
                           item=item, terug_url=url_for('admin.leeftijdscategorieën'))


@admin_bp.route('/leeftijdscategorieën/<int:item_id>/toggle')
@login_required
@admin_required
def leeftijdscategorie_toggle(item_id):
    return _beheer_toggle(AgeCategory, item_id, 'admin.leeftijdscategorieën')


@admin_bp.route('/leeftijdscategorieën/<int:item_id>/volgorde/<richting>')
@login_required
@admin_required
def leeftijdscategorie_volgorde(item_id, richting):
    return _beheer_volgorde(AgeCategory, item_id, richting, 'admin.leeftijdscategorieën')


# ─── Toestellen ──────────────────────────────────────────────────────────────

@admin_bp.route('/toestellen')
@login_required
@admin_required
def toestellen():
    items = Device.query.order_by(Device.volgorde, Device.naam).all()
    return render_template('admin/devices.html', items=items)


@admin_bp.route('/toestellen/nieuw', methods=['GET', 'POST'])
@login_required
@admin_required
def toestel_nieuw():
    if request.method == 'POST':
        naam = request.form.get('naam', '').strip()
        if not naam:
            flash('Naam is verplicht.', 'danger')
            return render_template('admin/item_form.html', titel='Toestel', actie='Nieuw',
                                   item=None, terug_url=url_for('admin.toestellen'))
        max_volgorde = db.session.query(db.func.max(Device.volgorde)).scalar() or 0
        db.session.add(Device(naam=naam, volgorde=max_volgorde + 1,
                              actief=request.form.get('actief') == 'on' if 'actief' in request.form else True))
        db.session.commit()
        flash(f'Toestel {naam} toegevoegd.', 'success')
        return redirect(url_for('admin.toestellen'))
    return render_template('admin/item_form.html', titel='Toestel', actie='Nieuw',
                           item=None, terug_url=url_for('admin.toestellen'))


@admin_bp.route('/toestellen/<int:item_id>/wijzig', methods=['GET', 'POST'])
@login_required
@admin_required
def toestel_wijzigen(item_id):
    item = db.get_or_404(Device, item_id)
    if request.method == 'POST':
        item.naam = request.form.get('naam', item.naam).strip()
        item.actief = request.form.get('actief') == 'on'
        db.session.commit()
        flash(f'{item.naam} bijgewerkt.', 'success')
        return redirect(url_for('admin.toestellen'))
    return render_template('admin/item_form.html', titel='Toestel', actie='Wijzigen',
                           item=item, terug_url=url_for('admin.toestellen'))


@admin_bp.route('/toestellen/<int:item_id>/toggle')
@login_required
@admin_required
def toestel_toggle(item_id):
    return _beheer_toggle(Device, item_id, 'admin.toestellen')


@admin_bp.route('/toestellen/<int:item_id>/volgorde/<richting>')
@login_required
@admin_required
def toestel_volgorde(item_id, richting):
    return _beheer_volgorde(Device, item_id, richting, 'admin.toestellen')