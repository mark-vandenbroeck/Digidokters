"""Beheer routes: gebruikers, digidokters, leeftijdscategorieën, toestellen, activiteitstypes, locaties."""
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from extensions import db, limiter
from models.user import User
from models.digidokter import Digidokter
from models.age_category import AgeCategory
from models.device import Device
from models.activity_type import ActivityType
from models.location import Location
from utils.decorators import admin_required

admin_bp = Blueprint('admin', __name__, url_prefix='/beheer')


# ─── Gebruikers ─────────────────────────────────────────────────────────────

@admin_bp.route('/gebruikers')
@login_required
@admin_required
def gebruikers():
    from utils.tenant import get_huidige_organisatie_id
    from models.organisatie import UserOrganisatie
    org_id = get_huidige_organisatie_id()
    memberships = UserOrganisatie.query.filter_by(organisatie_id=org_id).all()
    memberships = sorted(memberships, key=lambda x: x.user.naam.lower())
    return render_template('admin/users.html', memberships=memberships)


@admin_bp.route('/gebruikers/nieuw', methods=['GET', 'POST'])
@login_required
@admin_required
def gebruiker_nieuw():
    from utils.tenant import get_huidige_organisatie_id
    from models.organisatie import UserOrganisatie
    org_id = get_huidige_organisatie_id()

    if request.method == 'POST':
        naam = request.form.get('naam', '').strip()
        email_raw = request.form.get('email', '').strip().lower()
        email = email_raw if email_raw and email_raw not in ('none', 'null', 'undefined', 'n/a', '') else None
        rol = request.form.get('rol', 'medewerker')
        tijdelijk_ww = request.form.get('wachtwoord', '').strip()

        if rol == 'platformbeheerder' and current_user.rol != 'platformbeheerder':
            flash('U bent niet gemachtigd om de platformbeheerder rol toe te kennen.', 'danger')
            return render_template('admin/user_form.html', actie='Nieuw', user=None, membership=None, form_data=request.form)

        if not naam or not tijdelijk_ww:
            flash('Naam en wachtwoord zijn verplicht.', 'danger')
            return render_template('admin/user_form.html', actie='Nieuw', user=None, membership=None)

        # Check of gebruiker al bestaat globally
        user = User.query.filter(db.func.lower(User.naam) == naam.lower()).first()
        if user:
            uo_existing = UserOrganisatie.query.filter_by(user_id=user.id, organisatie_id=org_id).first()
            if uo_existing:
                flash('Er bestaat al een gebruiker met deze naam in deze organisatie.', 'danger')
                return render_template('admin/user_form.html', actie='Nieuw', user=None, membership=None, form_data=request.form)
            
            uo = UserOrganisatie(
                user_id=user.id,
                organisatie_id=org_id,
                rol='beheerder' if rol == 'platformbeheerder' else rol,
                actief=request.form.get('actief') == 'on' if 'actief' in request.form else True
            )
            db.session.add(uo)
            
            # Voeg ook toe als Digidokter
            existing_dd = Digidokter.query.filter_by(organisatie_id=org_id, naam=user.naam).first()
            if not existing_dd:
                max_volgorde = db.session.query(db.func.max(Digidokter.volgorde)).filter_by(organisatie_id=org_id).scalar() or 0
                dd = Digidokter(naam=user.naam, actief=True, volgorde=max_volgorde + 1, organisatie_id=org_id)
                db.session.add(dd)
                
            db.session.commit()
            flash(f'Bestaande gebruiker {user.naam} gekoppeld aan de organisatie.', 'success')
            return redirect(url_for('admin.gebruikers'))

        if email and User.query.filter(db.func.lower(User.email) == email).first():
            flash('Dit e-mailadres is al in gebruik.', 'danger')
            return render_template('admin/user_form.html', actie='Nieuw', user=None, membership=None, form_data=request.form)

        user = User(
            naam=naam,
            email=email,
            wachtwoord_hash=generate_password_hash(tijdelijk_ww),
            rol=rol,
            actief=True,
            moet_wachtwoord_wijzigen=True,
        )
        db.session.add(user)
        db.session.flush()

        uo = UserOrganisatie(
            user_id=user.id,
            organisatie_id=org_id,
            rol='beheerder' if rol == 'platformbeheerder' else rol,
            actief=request.form.get('actief') == 'on' if 'actief' in request.form else True
        )
        db.session.add(uo)
        
        # Voeg ook toe als Digidokter
        existing_dd = Digidokter.query.filter_by(organisatie_id=org_id, naam=user.naam).first()
        if not existing_dd:
            max_volgorde = db.session.query(db.func.max(Digidokter.volgorde)).filter_by(organisatie_id=org_id).scalar() or 0
            dd = Digidokter(naam=user.naam, actief=True, volgorde=max_volgorde + 1, organisatie_id=org_id)
            db.session.add(dd)
            
        db.session.commit()
        
        if user.email:
            from utils.mail import stuur_welkomst_email
            success, msg = stuur_welkomst_email(user.email, user.naam, tijdelijk_ww)
            if success:
                flash(f'Gebruiker {naam} aangemaakt. Welkomstmail succesvol verzonden naar {user.email}.', 'success')
            else:
                flash(f'Gebruiker {naam} aangemaakt, maar fout bij verzenden welkomstmail: {msg}', 'warning')
        else:
            flash(f'Gebruiker {naam} aangemaakt. Tijdelijk wachtwoord: {tijdelijk_ww}', 'success')
            
        return redirect(url_for('admin.gebruikers'))

    return render_template('admin/user_form.html', actie='Nieuw', user=None, membership=None)


@admin_bp.route('/gebruikers/<int:user_id>/wijzig', methods=['GET', 'POST'])
@login_required
@admin_required
def gebruiker_wijzigen(user_id):
    from utils.tenant import get_huidige_organisatie_id
    from models.organisatie import UserOrganisatie
    org_id = get_huidige_organisatie_id()
    
    user = db.get_or_404(User, user_id)
    membership = UserOrganisatie.query.filter_by(user_id=user.id, organisatie_id=org_id).first_or_404()

    if request.method == 'POST':
        rol = request.form.get('rol', membership.rol)
        if rol == 'platformbeheerder' and current_user.rol != 'platformbeheerder':
            flash('U bent niet gemachtigd om de platformbeheerder rol toe te kennen.', 'danger')
            return render_template('admin/user_form.html', actie='Wijzigen', user=user, membership=membership, form_data=request.form)

        naam_in = request.form.get('naam', user.naam).strip()
        email_raw = request.form.get('email', '').strip().lower()
        email_in = email_raw if email_raw and email_raw not in ('none', 'null', 'undefined', 'n/a', '') else None

        # Controleer unieke naam
        if naam_in != user.naam:
            bestaande_naam = User.query.filter(db.func.lower(User.naam) == naam_in.lower(), User.id != user.id).first()
            if bestaande_naam:
                flash(f'Gebruikersnaam {naam_in} is al in gebruik.', 'danger')
                return render_template('admin/user_form.html', actie='Wijzigen', user=user, membership=membership, form_data=request.form)

        # Controleer unieke email
        if email_in and email_in != user.email:
            bestaande_email = User.query.filter(db.func.lower(User.email) == email_in, User.id != user.id).first()
            if bestaande_email:
                flash(f'Het e-mailadres {email_in} is al in gebruik door {bestaande_email.naam}.', 'danger')
                return render_template('admin/user_form.html', actie='Wijzigen', user=user, membership=membership, form_data=request.form)

        user.naam = naam_in
        user.email = email_in
        user.rol = rol
        membership.rol = 'beheerder' if rol == 'platformbeheerder' else rol
        
        if user.id != 1:
            membership.actief = request.form.get('actief') == 'on'
            
        nieuw_ww = request.form.get('wachtwoord', '').strip()
        if nieuw_ww:
            user.wachtwoord_hash = generate_password_hash(nieuw_ww)
            user.moet_wachtwoord_wijzigen = True
        else:
            user.moet_wachtwoord_wijzigen = request.form.get('moet_wachtwoord_wijzigen') == 'on'
            
        try:
            db.session.commit()
            flash(f'Gebruiker {user.naam} bijgewerkt.', 'success')
            return redirect(url_for('admin.gebruikers'))
        except Exception as e:
            db.session.rollback()
            flash(f'Fout bij opslaan van gebruiker: {str(e)}', 'danger')
            return render_template('admin/user_form.html', actie='Wijzigen', user=user, membership=membership, form_data=request.form)

    return render_template('admin/user_form.html', actie='Wijzigen', user=user, membership=membership)


@admin_bp.route('/gebruikers/<int:user_id>/toggle')
@login_required
@admin_required
def gebruiker_toggle(user_id):
    from utils.tenant import get_huidige_organisatie_id
    from models.organisatie import UserOrganisatie
    org_id = get_huidige_organisatie_id()
    
    user = db.get_or_404(User, user_id)
    if user.id == 1:
        flash('De eerste beheerder kan niet worden gedeactiveerd.', 'warning')
        return redirect(url_for('admin.gebruikers'))
        
    membership = UserOrganisatie.query.filter_by(user_id=user.id, organisatie_id=org_id).first_or_404()
    membership.actief = not membership.actief
    db.session.commit()
    status = 'geactiveerd' if membership.actief else 'gedeactiveerd'
    flash(f'Gebruiker {user.naam} {status}.', 'info')
    return redirect(url_for('admin.gebruikers'))


# ─── Generieke beheer helper ─────────────────────────────────────────────────

def _beheer_lijst(model, template, naam_veld='naam'):
    from utils.tenant import filter_op_organisatie
    items = filter_op_organisatie(model.query, model).order_by(getattr(model, 'volgorde'), getattr(model, naam_veld)).all()
    return render_template(template, items=items)


def _beheer_toggle(model, item_id, redirect_endpoint):
    from utils.tenant import get_huidige_organisatie_id
    org_id = get_huidige_organisatie_id()
    item = db.get_or_404(model, item_id)
    if item.organisatie_id != org_id:
        from flask import abort
        abort(403)
    item.actief = not item.actief
    db.session.commit()
    status = 'geactiveerd' if item.actief else 'gedeactiveerd'
    flash(f'{item.naam} {status}.', 'info')
    return redirect(url_for(redirect_endpoint))


def _beheer_volgorde(model, item_id, richting, redirect_endpoint):
    """Verplaats een item omhoog of omlaag in de volgorde."""
    from utils.tenant import get_huidige_organisatie_id, filter_op_organisatie
    org_id = get_huidige_organisatie_id()
    item = db.get_or_404(model, item_id)
    if item.organisatie_id != org_id:
        from flask import abort
        abort(403)
        
    alle = filter_op_organisatie(model.query, model).order_by(model.volgorde, model.naam).all()
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
    for i, x in enumerate(filter_op_organisatie(model.query, model).order_by(model.volgorde, model.naam).all()):
        x.volgorde = i
    db.session.commit()
    return redirect(url_for(redirect_endpoint))


# ─── Digidokters ─────────────────────────────────────────────────────────────

@admin_bp.route('/digidokters')
@login_required
@admin_required
def digidokters():
    return _beheer_lijst(Digidokter, 'admin/digidokters.html')


@admin_bp.route('/digidokters/nieuw', methods=['GET', 'POST'])
@login_required
@admin_required
def digidokter_nieuw():
    from utils.tenant import get_huidige_organisatie_id
    org_id = get_huidige_organisatie_id()

    if request.method == 'POST':
        naam = request.form.get('naam', '').strip()
        if not naam:
            flash('Naam is verplicht.', 'danger')
            return render_template('admin/item_form.html', titel='Digidokter', actie='Nieuw',
                                   item=None, terug_url=url_for('admin.digidokters'))
        max_volgorde = db.session.query(db.func.max(Digidokter.volgorde)).filter(Digidokter.organisatie_id == org_id).scalar() or 0
        db.session.add(Digidokter(naam=naam, volgorde=max_volgorde + 1, organisatie_id=org_id,
                                  actief=request.form.get('actief') == 'on'))
        db.session.commit()
        flash(f'Digidokter {naam} toegevoegd.', 'success')
        return redirect(url_for('admin.digidokters'))
    return render_template('admin/item_form.html', titel='Digidokter', actie='Nieuw',
                           item=None, terug_url=url_for('admin.digidokters'))


@admin_bp.route('/digidokters/<int:item_id>/wijzig', methods=['GET', 'POST'])
@login_required
@admin_required
def digidokter_wijzigen(item_id):
    from utils.tenant import get_huidige_organisatie_id
    org_id = get_huidige_organisatie_id()
    item = db.get_or_404(Digidokter, item_id)
    
    if item.organisatie_id != org_id:
        from flask import abort
        abort(403)
        
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
    return _beheer_lijst(AgeCategory, 'admin/age_categories.html')


@admin_bp.route('/leeftijdscategorieën/nieuw', methods=['GET', 'POST'])
@login_required
@admin_required
def leeftijdscategorie_nieuw():
    from utils.tenant import get_huidige_organisatie_id
    org_id = get_huidige_organisatie_id()

    if request.method == 'POST':
        naam = request.form.get('naam', '').strip()
        if not naam:
            flash('Naam is verplicht.', 'danger')
            return render_template('admin/item_form.html', titel='Leeftijdscategorie', actie='Nieuw',
                                   item=None, terug_url=url_for('admin.leeftijdscategorieën'))
        max_volgorde = db.session.query(db.func.max(AgeCategory.volgorde)).filter(AgeCategory.organisatie_id == org_id).scalar() or 0
        db.session.add(AgeCategory(naam=naam, volgorde=max_volgorde + 1, organisatie_id=org_id,
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
    from utils.tenant import get_huidige_organisatie_id
    org_id = get_huidige_organisatie_id()
    item = db.get_or_404(AgeCategory, item_id)
    
    if item.organisatie_id != org_id:
        from flask import abort
        abort(403)
        
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
    return _beheer_lijst(Device, 'admin/devices.html')


@admin_bp.route('/toestellen/nieuw', methods=['GET', 'POST'])
@login_required
@admin_required
def toestel_nieuw():
    from utils.tenant import get_huidige_organisatie_id
    org_id = get_huidige_organisatie_id()

    if request.method == 'POST':
        naam = request.form.get('naam', '').strip()
        if not naam:
            flash('Naam is verplicht.', 'danger')
            return render_template('admin/item_form.html', titel='Toestel', actie='Nieuw',
                                   item=None, terug_url=url_for('admin.toestellen'))
        max_volgorde = db.session.query(db.func.max(Device.volgorde)).filter(Device.organisatie_id == org_id).scalar() or 0
        db.session.add(Device(naam=naam, volgorde=max_volgorde + 1, organisatie_id=org_id,
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
    from utils.tenant import get_huidige_organisatie_id
    org_id = get_huidige_organisatie_id()
    item = db.get_or_404(Device, item_id)
    
    if item.organisatie_id != org_id:
        from flask import abort
        abort(403)
        
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


@admin_bp.route('/backup')
@login_required
@admin_required
@limiter.limit("5 per minute; 20 per hour")
def backup():
    import json
    from datetime import datetime
    from flask import Response
    from models.organisatie import Organisatie, UserOrganisatie
    from models.user import User
    from models.digidokter import Digidokter
    from models.age_category import AgeCategory
    from models.device import Device
    from models.registration import Registration
    from utils.tenant import get_huidige_organisatie_id
    
    org_id = get_huidige_organisatie_id()
    org = db.session.get(Organisatie, org_id)
    
    # 1. Fetch data
    users_data = []
    memberships = UserOrganisatie.query.filter_by(organisatie_id=org_id).all()
    for m in memberships:
        users_data.append({
            'naam': m.user.naam,
            'email': m.user.email,
            'wachtwoord_hash': m.user.wachtwoord_hash,
            'rol': m.user.rol,
            'actief': m.user.actief,
            'membership_rol': m.rol,
            'membership_actief': m.actief
        })
        
    digidokters_data = []
    for d in Digidokter.query.filter_by(organisatie_id=org_id).all():
        digidokters_data.append({
            'naam': d.naam,
            'actief': d.actief,
            'volgorde': d.volgorde
        })
        
    age_cats_data = []
    for c in AgeCategory.query.filter_by(organisatie_id=org_id).all():
        age_cats_data.append({
            'naam': c.naam,
            'actief': c.actief,
            'volgorde': c.volgorde
        })
        
    devices_data = []
    for t in Device.query.filter_by(organisatie_id=org_id).all():
        devices_data.append({
            'naam': t.naam,
            'actief': t.actief,
            'volgorde': t.volgorde
        })
        
    registrations_data = []
    for r in Registration.query.filter_by(organisatie_id=org_id).all():
        registrations_data.append({
            'registratienummer': r.registratienummer,
            'datum': r.datum.isoformat() if r.datum else None,
            'client': r.client,
            'nieuwe_klant': r.nieuwe_klant,
            'herkomst': r.herkomst,
            'geslacht': r.geslacht,
            'onderwerp': r.onderwerp,
            'digidokter_naam': r.digidokter.naam if r.digidokter else '',
            'leeftijdscategorie_naam': r.leeftijdscategorie.naam if r.leeftijdscategorie else '',
            'toestel_naam': r.toestel.naam if r.toestel else '',
            'aangemaakt_door_naam': r.aangemaakt_door_user.naam if r.aangemaakt_door_user else '',
            'aangemaakt_op': r.aangemaakt_op.isoformat() if r.aangemaakt_op else None,
            'gewijzigd_op': r.gewijzigd_op.isoformat() if r.gewijzigd_op else None
        })
        
    activity_types_data = []
    for at in ActivityType.query.filter_by(organisatie_id=org_id).all():
        activity_types_data.append({
            'naam': at.naam,
            'actief': at.actief,
            'volgorde': at.volgorde
        })

    locations_data = []
    for l in Location.query.filter_by(organisatie_id=org_id).all():
        locations_data.append({
            'naam': l.naam,
            'actief': l.actief,
            'volgorde': l.volgorde
        })

    agenda_items_data = []
    from models.agenda import AgendaItem
    for item in AgendaItem.query.filter_by(organisatie_id=org_id).all():
        agenda_items_data.append({
            'datum': item.datum.isoformat() if item.datum else None,
            'uur_van': item.uur_van,
            'uur_tot': item.uur_tot,
            'type_naam': item.type.naam,
            'locatie_naam': item.locatie.naam,
            'omschrijving': item.omschrijving,
            'digidokter_namen': [dd.naam for dd in item.digidokters]
        })

    backup_dict = {
        'organisatie': {
            'naam': org.naam,
            'slug': org.slug
        },
        'users': users_data,
        'digidokters': digidokters_data,
        'age_categories': age_cats_data,
        'devices': devices_data,
        'activity_types': activity_types_data,
        'locations': locations_data,
        'registrations': registrations_data,
        'agenda_items': agenda_items_data
    }
    
    json_bytes = json.dumps(backup_dict, indent=2, ensure_ascii=False).encode('utf-8')
    date_str = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"backup_{org.slug}_{date_str}.json"
    
    return Response(
        json_bytes,
        mimetype="application/json",
        headers={"Content-disposition": f"attachment; filename={filename}"}
    )


@admin_bp.route('/restore', methods=['GET', 'POST'])
@login_required
@admin_required
@limiter.limit("5 per minute; 20 per hour")
def restore():
    from utils.tenant import get_huidige_organisatie_id
    from models.organisatie import Organisatie, UserOrganisatie
    from models.user import User
    from models.digidokter import Digidokter
    from models.age_category import AgeCategory
    from models.device import Device
    from models.registration import Registration
    from models.activity_type import ActivityType
    from models.location import Location
    import json
    from datetime import datetime, timezone
    
    org_id = get_huidige_organisatie_id()
    
    if request.method == 'POST':
        file = request.files.get('backup_file')
        if not file or file.filename == '':
            flash('Gelieve een geldig JSON-bestand te selecteren.', 'danger')
            return redirect(url_for('admin.restore'))
            
        try:
            data = json.load(file)
        except Exception as e:
            flash(f'Fout bij het lezen van het JSON-bestand: {str(e)}', 'danger')
            return redirect(url_for('admin.restore'))
            
        # Validatie van structuur
        required_keys = ['organisatie', 'users', 'digidokters', 'age_categories', 'devices', 'registrations']
        if not all(k in data for k in required_keys):
            flash('Ongeldig backup-bestand. Het bestand mist vereiste datablokken.', 'danger')
            return redirect(url_for('admin.restore'))
            
        try:
            with db.session.begin_nested():
                # 1. Verwijder bestaande organisatiegegevens
                from models.agenda import AgendaItem
                Registration.query.filter_by(organisatie_id=org_id).delete()
                AgendaItem.query.filter_by(organisatie_id=org_id).delete()
                Digidokter.query.filter_by(organisatie_id=org_id).delete()
                AgeCategory.query.filter_by(organisatie_id=org_id).delete()
                Device.query.filter_by(organisatie_id=org_id).delete()
                ActivityType.query.filter_by(organisatie_id=org_id).delete()
                Location.query.filter_by(organisatie_id=org_id).delete()
                
                # 2. Bewaar de huidige ingelogde user
                huidige_user_id = current_user.id
                
                # Verwijder alle lidmaatschappen behalve de actieve hersteller
                UserOrganisatie.query.filter(
                    UserOrganisatie.organisatie_id == org_id,
                    UserOrganisatie.user_id != huidige_user_id
                ).delete()
                
                # 3. Herstel digidokters
                digidokters_map = {}
                for d_data in data['digidokters']:
                    d = Digidokter(
                        naam=d_data['naam'],
                        actief=d_data['actief'],
                        volgorde=d_data['volgorde'],
                        organisatie_id=org_id
                    )
                    db.session.add(d)
                    db.session.flush()
                    digidokters_map[d.naam] = d.id
                    
                # 4. Herstel leeftijdscategorieën
                age_cats_map = {}
                for c_data in data['age_categories']:
                    c = AgeCategory(
                        naam=c_data['naam'],
                        actief=c_data['actief'],
                        volgorde=c_data['volgorde'],
                        organisatie_id=org_id
                    )
                    db.session.add(c)
                    db.session.flush()
                    age_cats_map[c.naam] = c.id
                    
                # 5. Herstel toestellen
                devices_map = {}
                for t_data in data['devices']:
                    t = Device(
                        naam=t_data['naam'],
                        actief=t_data['actief'],
                        volgorde=t_data['volgorde'],
                        organisatie_id=org_id
                    )
                    db.session.add(t)
                    db.session.flush()
                    devices_map[t.naam] = t.id
                    
                # 6. Herstel gebruikers & lidmaatschappen
                users_map = {}
                for u_data in data['users']:
                    u = User.query.filter(db.func.lower(User.naam) == u_data['naam'].lower()).first()
                    if not u:
                        u = User(
                            naam=u_data['naam'],
                            email=u_data['email'],
                            wachtwoord_hash=u_data['wachtwoord_hash'],
                            rol=u_data['rol'],
                            actief=u_data['actief'],
                            moet_wachtwoord_wijzigen=False
                        )
                        db.session.add(u)
                        db.session.flush()
                    
                    users_map[u.naam] = u.id
                    
                    uo = UserOrganisatie.query.filter_by(user_id=u.id, organisatie_id=org_id).first()
                    if not uo:
                        uo = UserOrganisatie(
                            user_id=u.id,
                            organisatie_id=org_id,
                            rol=u_data['membership_rol'],
                            actief=u_data['membership_actief']
                        )
                        db.session.add(uo)
                    else:
                        uo.rol = u_data['membership_rol']
                        uo.actief = u_data['membership_actief']
                
                # Zorg dat de actieve hersteller nog lid blijft
                uo_hersteller = UserOrganisatie.query.filter_by(user_id=huidige_user_id, organisatie_id=org_id).first()
                if not uo_hersteller:
                    uo_hersteller = UserOrganisatie(
                        user_id=huidige_user_id,
                        organisatie_id=org_id,
                        rol='beheerder',
                        actief=True
                    )
                    db.session.add(uo_hersteller)
                else:
                    uo_hersteller.rol = 'beheerder'
                    uo_hersteller.actief = True
                
                # 7. Herstel registraties
                for r_data in data['registrations']:
                    d_id = digidokters_map.get(r_data['digidokter_naam'])
                    c_id = age_cats_map.get(r_data['leeftijdscategorie_naam'])
                    t_id = devices_map.get(r_data['toestel_naam'])
                    creator_id = users_map.get(r_data['aangemaakt_door_naam'], huidige_user_id)
                    
                    if not d_id:
                        d_id = list(digidokters_map.values())[0] if digidokters_map else None
                    if not c_id:
                        c_id = list(age_cats_map.values())[0] if age_cats_map else None
                    if not t_id:
                        t_id = list(devices_map.values())[0] if devices_map else None
                        
                    from datetime import datetime as dt
                    reg_datum = dt.fromisoformat(r_data['datum']).date() if r_data.get('datum') else None
                    created_at = dt.fromisoformat(r_data['aangemaakt_op']) if r_data.get('aangemaakt_op') else datetime.now(timezone.utc)
                    modified_at = dt.fromisoformat(r_data['gewijzigd_op']) if r_data.get('gewijzigd_op') else datetime.now(timezone.utc)
                    
                    r = Registration(
                        registratienummer=r_data['registratienummer'],
                        datum=reg_datum,
                        client=r_data['client'],
                        nieuwe_klant=r_data['nieuwe_klant'],
                        herkomst=r_data.get('herkomst'),
                        geslacht=r_data.get('geslacht'),
                        onderwerp=r_data['onderwerp'],
                        digidokter_id=d_id,
                        leeftijdscategorie_id=c_id,
                        toestel_id=t_id,
                        aangemaakt_door_id=creator_id,
                        aangemaakt_op=created_at,
                        gewijzigd_op=modified_at,
                        organisatie_id=org_id
                    )
                    db.session.add(r)

                # 8. Herstel activiteitstypes
                activity_types_map = {}
                if 'activity_types' in data:
                    for at_data in data['activity_types']:
                        at = ActivityType(
                            naam=at_data['naam'],
                            actief=at_data['actief'],
                            volgorde=at_data['volgorde'],
                            organisatie_id=org_id
                        )
                        db.session.add(at)
                        db.session.flush()
                        activity_types_map[at.naam] = at.id
                else:
                    for i, name in enumerate(['Digidokters', 'Digicafé', 'Lunchvergadering']):
                        at = ActivityType(naam=name, actief=True, volgorde=i, organisatie_id=org_id)
                        db.session.add(at)
                        db.session.flush()
                        activity_types_map[name] = at.id

                # 9. Herstel locaties
                locations_map = {}
                if 'locations' in data:
                    for l_data in data['locations']:
                        l = Location(
                            naam=l_data['naam'],
                            actief=l_data['actief'],
                            volgorde=l_data['volgorde'],
                            organisatie_id=org_id
                        )
                        db.session.add(l)
                        db.session.flush()
                        locations_map[l.naam] = l.id
                else:
                    for i, name in enumerate(['Bib Londerzeel', 'Buurttafel', 'Brouwerij De Palm']):
                        l = Location(naam=name, actief=True, volgorde=i, organisatie_id=org_id)
                        db.session.add(l)
                        db.session.flush()
                        locations_map[name] = l.id

                # 10. Herstel agenda-items
                if 'agenda_items' in data:
                    for item_data in data['agenda_items']:
                        from datetime import datetime as dt
                        datum = dt.fromisoformat(item_data['datum']).date() if item_data.get('datum') else None
                        
                        type_id = activity_types_map.get(item_data['type_name'])
                        locatie_id = locations_map.get(item_data['locatie_name'])
                        
                        if not type_id:
                            type_id = list(activity_types_map.values())[0] if activity_types_map else None
                        if not locatie_id:
                            locatie_id = list(locations_map.values())[0] if locations_map else None
                            
                        item = AgendaItem(
                            datum=datum,
                            uur_van=item_data['uur_van'],
                            uur_tot=item_data['uur_tot'],
                            type_id=type_id,
                            locatie_id=locatie_id,
                            omschrijving=item_data.get('omschrijving'),
                            organisatie_id=org_id
                        )
                        
                        selected_dds = []
                        for dd_name in item_data.get('digidokter_namen', []):
                            dd_id = digidokters_map.get(dd_name)
                            if dd_id:
                                d = db.session.get(Digidokter, dd_id)
                                if d:
                                    selected_dds.append(d)
                        item.digidokters = selected_dds
                        
                        db.session.add(item)
            db.session.commit()
            flash('De organisatie-data is succesvol hersteld.', 'success')
            return redirect(url_for('admin.gebruikers'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Fout tijdens het herstellen van de data: {str(e)}', 'danger')
            return redirect(url_for('admin.restore'))
            
    return render_template('admin/restore.html')


# ─── Activiteitstypes ───────────────────────────────────────────────────────

@admin_bp.route('/activiteitstypes')
@login_required
@admin_required
def activiteitstypes():
    from utils.tenant import filter_op_organisatie
    items = filter_op_organisatie(ActivityType.query, ActivityType).order_by(ActivityType.volgorde, ActivityType.naam).all()
    return render_template('admin/activiteitstypes.html', items=items)


@admin_bp.route('/activiteitstypes/nieuw', methods=['GET', 'POST'])
@login_required
@admin_required
def activiteitstype_nieuw():
    from utils.tenant import get_huidige_organisatie_id, set_organisatie_id_op_model
    org_id = get_huidige_organisatie_id()
    
    if request.method == 'POST':
        naam = request.form.get('naam', '').strip()
        if not naam:
            flash('Naam is verplicht.', 'danger')
            return render_template('admin/item_form.html', titel='Activiteitstype', actie='Toevoegen', item=None, terug_url=url_for('admin.activiteitstypes'))
            
        existing = ActivityType.query.filter_by(organisatie_id=org_id, naam=naam).first()
        if existing:
            flash('Dit activiteitstype bestaat al.', 'danger')
            return render_template('admin/item_form.html', titel='Activiteitstype', actie='Toevoegen', item=None, form_data=request.form, terug_url=url_for('admin.activiteitstypes'))
            
        max_volgorde = db.session.query(db.func.max(ActivityType.volgorde)).filter_by(organisatie_id=org_id).scalar() or 0
        actief = request.form.get('actief') == 'on' if 'actief' in request.form else True
        kleur = request.form.get('kleur', 'blue')
        item = ActivityType(naam=naam, actief=actief, kleur=kleur, volgorde=max_volgorde + 1)
        set_organisatie_id_op_model(item)
        db.session.add(item)
        db.session.commit()
        flash(f'Activiteitstype {naam} toegevoegd.', 'success')
        return redirect(url_for('admin.activiteitstypes'))
        
    return render_template('admin/item_form.html', titel='Activiteitstype', actie='Toevoegen', item=None, terug_url=url_for('admin.activiteitstypes'))


@admin_bp.route('/activiteitstypes/<int:item_id>/wijzig', methods=['GET', 'POST'])
@login_required
@admin_required
def activiteitstype_wijzigen(item_id):
    from utils.tenant import get_huidige_organisatie_id
    org_id = get_huidige_organisatie_id()
    item = db.get_or_404(ActivityType, item_id)
    
    if item.organisatie_id != org_id:
        from flask import abort
        abort(403)
        
    if request.method == 'POST':
        item.naam = request.form.get('naam', item.naam).strip()
        item.actief = request.form.get('actief') == 'on'
        item.kleur = request.form.get('kleur', 'blue')
        db.session.commit()
        flash(f'{item.naam} bijgewerkt.', 'success')
        return redirect(url_for('admin.activiteitstypes'))
    return render_template('admin/item_form.html', titel='Activiteitstype', actie='Wijzigen',
                           item=item, terug_url=url_for('admin.activiteitstypes'))



@admin_bp.route('/activiteitstypes/<int:item_id>/toggle')
@login_required
@admin_required
def activiteitstype_toggle(item_id):
    return _beheer_toggle(ActivityType, item_id, 'admin.activiteitstypes')


@admin_bp.route('/activiteitstypes/<int:item_id>/volgorde/<richting>')
@login_required
@admin_required
def activiteitstype_volgorde(item_id, richting):
    return _beheer_volgorde(ActivityType, item_id, richting, 'admin.activiteitstypes')


# ─── Locaties ───────────────────────────────────────────────────────────────

@admin_bp.route('/locaties')
@login_required
@admin_required
def locaties():
    from utils.tenant import filter_op_organisatie
    items = filter_op_organisatie(Location.query, Location).order_by(Location.volgorde, Location.naam).all()
    return render_template('admin/locaties.html', items=items)


@admin_bp.route('/locaties/nieuw', methods=['GET', 'POST'])
@login_required
@admin_required
def locatie_nieuw():
    from utils.tenant import get_huidige_organisatie_id, set_organisatie_id_op_model
    org_id = get_huidige_organisatie_id()
    
    if request.method == 'POST':
        naam = request.form.get('naam', '').strip()
        if not naam:
            flash('Naam is verplicht.', 'danger')
            return render_template('admin/item_form.html', titel='Locatie', actie='Toevoegen', item=None, terug_url=url_for('admin.locaties'))
            
        existing = Location.query.filter_by(organisatie_id=org_id, naam=naam).first()
        if existing:
            flash('Deze locatie bestaat al.', 'danger')
            return render_template('admin/item_form.html', titel='Locatie', actie='Toevoegen', item=None, form_data=request.form, terug_url=url_for('admin.locaties'))
            
        max_volgorde = db.session.query(db.func.max(Location.volgorde)).filter_by(organisatie_id=org_id).scalar() or 0
        item = Location(naam=naam, actief=True, volgorde=max_volgorde + 1)
        set_organisatie_id_op_model(item)
        db.session.add(item)
        db.session.commit()
        flash(f'Locatie {naam} toegevoegd.', 'success')
        return redirect(url_for('admin.locaties'))
        
    return render_template('admin/item_form.html', titel='Locatie', actie='Toevoegen', item=None, terug_url=url_for('admin.locaties'))


@admin_bp.route('/locaties/<int:item_id>/wijzig', methods=['GET', 'POST'])
@login_required
@admin_required
def locatie_wijzigen(item_id):
    from utils.tenant import get_huidige_organisatie_id
    org_id = get_huidige_organisatie_id()
    item = db.get_or_404(Location, item_id)
    
    if item.organisatie_id != org_id:
        from flask import abort
        abort(403)
        
    if request.method == 'POST':
        item.naam = request.form.get('naam', item.naam).strip()
        item.actief = request.form.get('actief') == 'on'
        db.session.commit()
        flash(f'{item.naam} bijgewerkt.', 'success')
        return redirect(url_for('admin.locaties'))
    return render_template('admin/item_form.html', titel='Locatie', actie='Wijzigen',
                           item=item, terug_url=url_for('admin.locaties'))


@admin_bp.route('/locaties/<int:item_id>/toggle')
@login_required
@admin_required
def locatie_toggle(item_id):
    return _beheer_toggle(Location, item_id, 'admin.locaties')


@admin_bp.route('/locaties/<int:item_id>/volgorde/<richting>')
@login_required
@admin_required
def locatie_volgorde(item_id, richting):
    return _beheer_volgorde(Location, item_id, richting, 'admin.locaties')


@admin_bp.route('/audit-log')
@login_required
@admin_required
def audit_log():
    from models.audit import AuditLog
    from models.organisatie import Organisatie
    from utils.tenant import get_huidige_organisatie_id
    from datetime import datetime, time
    
    org_id = get_huidige_organisatie_id()
    
    page = request.args.get('page', 1, type=int)
    datum_van_str = request.args.get('datum_van', '').strip()
    datum_tot_str = request.args.get('datum_tot', '').strip()
    gebruiker = request.args.get('gebruiker', '').strip()
    operatie = request.args.get('operatie', '').strip()
    tabel = request.args.get('tabel', '').strip()
    filter_org_id = request.args.get('filter_organisatie_id', None, type=int)
    toon_logins = request.args.get('toon_logins', '').strip().lower() == 'true'

    query = AuditLog.query
    
    # Multi-tenancy filter
    if current_user.rol == 'platformbeheerder':
        if filter_org_id:
            query = query.filter_by(organisatie_id=filter_org_id)
    else:
        query = query.filter_by(organisatie_id=org_id)
        
    # Filters
    if not toon_logins:
        pattern = '{"oude_waarden": {"laatste_login": %}, "nieuwe_waarden": {"laatste_login": %}}'
        query = query.filter(
            db.not_(
                db.and_(
                    AuditLog.tabel == 'users',
                    AuditLog.operatie == 'UPDATE',
                    AuditLog.details.like(pattern)
                )
            )
        )

    if datum_van_str:
        try:
            dt_van = datetime.strptime(datum_van_str, '%Y-%m-%d')
            query = query.filter(AuditLog.timestamp >= dt_van)
        except ValueError:
            pass
            
    if datum_tot_str:
        try:
            dt_tot = datetime.strptime(datum_tot_str, '%Y-%m-%d')
            dt_tot = datetime.combine(dt_tot, time.max)
            query = query.filter(AuditLog.timestamp <= dt_tot)
        except ValueError:
            pass
            
    if gebruiker:
        query = query.filter(AuditLog.gebruiker.ilike(f'%{gebruiker}%'))
        
    if operatie:
        query = query.filter_by(operatie=operatie)
        
    if tabel:
        query = query.filter(AuditLog.tabel.ilike(f'%{tabel}%'))
        
    # Sorteren op meest recent eerst
    query = query.order_by(AuditLog.timestamp.desc())
    
    # Paginatie
    pagination = query.paginate(page=page, per_page=50, error_out=False)
    logs = pagination.items
    
    import json
    for log in logs:
        try:
            log.parsed_details = json.loads(log.details) if log.details else {}
        except Exception:
            log.parsed_details = {}
    
    # Voor platformbeheerders, lijst met alle organisaties voor de filter-dropdown

    organisaties = []
    if current_user.rol == 'platformbeheerder':
        organisaties = Organisatie.query.order_by(Organisatie.naam).all()
        
    return render_template(
        'admin/audit_logs.html',
        logs=logs,
        pagination=pagination,
        organisaties=organisaties,
        datum_van=datum_van_str,
        datum_tot=datum_tot_str,
        gebruiker=gebruiker,
        operatie=operatie,
        tabel=tabel,
        filter_organisatie_id=filter_org_id,
        toon_logins=toon_logins
    )


@admin_bp.route('/audit-log/opschonen', methods=['POST'])
@login_required
@admin_required
def audit_log_opschonen():
    from models.audit import AuditLog
    from datetime import datetime, timedelta, timezone
    
    grens = datetime.now(timezone.utc) - timedelta(days=365)
    try:
        aantal = AuditLog.query.filter(AuditLog.timestamp < grens).delete()
        db.session.commit()
        flash(f'Succesvol {aantal} oude audit logs (ouder dan 365 dagen) verwijderd.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Fout bij het opschonen van audit logs: {str(e)}', 'danger')
        
    return redirect(url_for('admin.audit_log'))