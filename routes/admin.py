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
from models.herkomst import Herkomst
from models.gender_identity import GenderIdentity
from models.functie import Functie, user_functies
from models.registration import Registration
from utils.decorators import admin_required, platform_admin_required

admin_bp = Blueprint('admin', __name__, url_prefix='/beheer')


# ─── Gebruikers ─────────────────────────────────────────────────────────────

@admin_bp.route('/gebruikers')
@login_required
@admin_required
def gebruikers():
    from utils.tenant import get_huidige_organisatie_id
    from models.organisatie import UserOrganisatie
    from sqlalchemy.orm import joinedload
    org_id = get_huidige_organisatie_id()

    sort_by = request.args.get('sort_by', 'naam').strip()
    direction = request.args.get('direction', 'asc').strip()
    status_filter = request.args.get('status', 'alle').strip().lower()
    if status_filter not in ('actief', 'inactief', 'alle'):
        status_filter = 'alle'

    query = (
        UserOrganisatie.query
        .options(joinedload(UserOrganisatie.user))
        .join(User, UserOrganisatie.user_id == User.id)
        .filter(UserOrganisatie.organisatie_id == org_id)
    )

    if status_filter == 'actief':
        query = query.filter(UserOrganisatie.actief == True)
    elif status_filter == 'inactief':
        query = query.filter(UserOrganisatie.actief == False)

    if sort_by == 'email':
        order_col = User.email.desc() if direction == 'desc' else User.email.asc()
    elif sort_by == 'rol':
        order_col = UserOrganisatie.rol.desc() if direction == 'desc' else UserOrganisatie.rol.asc()
    elif sort_by == 'status':
        order_col = UserOrganisatie.actief.desc() if direction == 'desc' else UserOrganisatie.actief.asc()
    elif sort_by == 'laatste_login':
        order_col = User.laatste_login.desc() if direction == 'desc' else User.laatste_login.asc()
    else:  # sort_by == 'naam'
        order_col = User.naam.desc() if direction == 'desc' else User.naam.asc()

    memberships = query.order_by(order_col).all()

    # Efficiënte SQL telling van digidokters gekoppeld aan gebruikers
    digidokter_counts = dict(
        db.session.query(Digidokter.user_id, db.func.count(Digidokter.id))
        .filter(Digidokter.user_id.isnot(None))
        .group_by(Digidokter.user_id)
        .all()
    )

    return render_template(
        'admin/users.html',
        memberships=memberships,
        digidokter_counts=digidokter_counts,
        sort_by=sort_by,
        direction=direction,
        status_filter=status_filter,
        org_id=org_id
    )


@admin_bp.route('/gebruikers/nieuw', methods=['GET', 'POST'])
@login_required
@admin_required
def gebruiker_nieuw():
    from utils.tenant import get_huidige_organisatie_id
    from models.organisatie import UserOrganisatie
    org_id = get_huidige_organisatie_id()

    beschikbare_functies = Functie.query.filter_by(organisatie_id=org_id, actief=True).order_by(Functie.volgorde).all()

    if request.method == 'POST':
        naam = request.form.get('naam', '').strip()
        email_raw = request.form.get('email', '').strip().lower()
        email = email_raw if email_raw and email_raw not in ('none', 'null', 'undefined', 'n/a', '') else None
        telefoonnummer = request.form.get('telefoonnummer', '').strip() or None
        rol = request.form.get('rol', 'medewerker')
        tijdelijk_ww = request.form.get('wachtwoord', '').strip()
        functie_ids = [int(x) for x in request.form.getlist('functie_ids') if x.isdigit()]

        if rol == 'platformbeheerder' and current_user.rol != 'platformbeheerder':
            flash('U bent niet gemachtigd om de platformbeheerder rol toe te kennen.', 'danger')
            return render_template('admin/user_form.html', actie='Nieuw', user=None, membership=None, form_data=request.form, beschikbare_functies=beschikbare_functies)

        if not naam or not email or not tijdelijk_ww:
            flash('Naam, e-mailadres en wachtwoord zijn verplicht.', 'danger')
            return render_template('admin/user_form.html', actie='Nieuw', user=None, membership=None, form_data=request.form, beschikbare_functies=beschikbare_functies)

        # Check of gebruiker al bestaat globally op e-mailadres
        user = User.query.filter(db.func.lower(User.email) == email).first()
        if user:
            uo_existing = UserOrganisatie.query.filter_by(user_id=user.id, organisatie_id=org_id).first()
            if uo_existing:
                flash('Er bestaat al een gebruiker met dit e-mailadres in deze organisatie.', 'danger')
                return render_template('admin/user_form.html', actie='Nieuw', user=None, membership=None, form_data=request.form, beschikbare_functies=beschikbare_functies)
            
            uo = UserOrganisatie(
                user_id=user.id,
                organisatie_id=org_id,
                rol='beheerder' if rol == 'platformbeheerder' else rol,
                actief=request.form.get('actief') == 'on' if 'actief' in request.form else True
            )
            db.session.add(uo)
            if telefoonnummer and not user.telefoonnummer:
                user.telefoonnummer = telefoonnummer
            
            # Geselecteerde functies koppelen
            if functie_ids:
                gekozen = Functie.query.filter(Functie.organisatie_id == org_id, Functie.id.in_(functie_ids)).all()
                for fn in gekozen:
                    if fn not in user.functies:
                        user.functies.append(fn)

            # Voeg ook toe als Digidokter
            existing_dd = Digidokter.query.filter_by(organisatie_id=org_id, naam=user.naam).first()
            if not existing_dd:
                max_volgorde = db.session.query(db.func.max(Digidokter.volgorde)).filter_by(organisatie_id=org_id).scalar() or 0
                dd = Digidokter(naam=user.naam, actief=True, volgorde=max_volgorde + 1, organisatie_id=org_id)
                db.session.add(dd)
                
            db.session.commit()
            flash(f'Bestaande gebruiker {user.naam} ({user.email}) gekoppeld aan de organisatie.', 'success')
            return redirect(url_for('admin.gebruikers'))

        user = User(
            naam=naam,
            email=email,
            telefoonnummer=telefoonnummer,
            wachtwoord_hash=generate_password_hash(tijdelijk_ww),
            rol=rol,
            actief=True,
            moet_wachtwoord_wijzigen=True,
        )
        db.session.add(user)
        db.session.flush()

        # Geselecteerde functies koppelen
        if functie_ids:
            gekozen = Functie.query.filter(Functie.organisatie_id == org_id, Functie.id.in_(functie_ids)).all()
            for fn in gekozen:
                user.functies.append(fn)

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

    return render_template('admin/user_form.html', actie='Nieuw', user=None, membership=None, beschikbare_functies=beschikbare_functies)


@admin_bp.route('/gebruikers/<int:user_id>/wijzig', methods=['GET', 'POST'])
@login_required
@admin_required
def gebruiker_wijzigen(user_id):
    from utils.tenant import get_huidige_organisatie_id
    from models.organisatie import UserOrganisatie
    org_id = get_huidige_organisatie_id()
    
    user = db.get_or_404(User, user_id)
    membership = UserOrganisatie.query.filter_by(user_id=user.id, organisatie_id=org_id).first_or_404()
    beschikbare_functies = Functie.query.filter_by(organisatie_id=org_id).order_by(Functie.volgorde).all()

    if request.method == 'POST':
        rol = request.form.get('rol', membership.rol)
        if rol == 'platformbeheerder' and current_user.rol != 'platformbeheerder':
            flash('U bent niet gemachtigd om de platformbeheerder rol toe te kennen.', 'danger')
            return render_template('admin/user_form.html', actie='Wijzigen', user=user, membership=membership, form_data=request.form, beschikbare_functies=beschikbare_functies)

        naam_in = request.form.get('naam', user.naam).strip()
        email_raw = request.form.get('email', '').strip().lower()
        email_in = email_raw if email_raw and email_raw not in ('none', 'null', 'undefined', 'n/a', '') else None
        telefoonnummer_in = request.form.get('telefoonnummer', '').strip() or None
        functie_ids = [int(x) for x in request.form.getlist('functie_ids') if x.isdigit()]

        # Controleer unieke naam
        if naam_in != user.naam:
            bestaande_naam = User.query.filter(db.func.lower(User.naam) == naam_in.lower(), User.id != user.id).first()
            if bestaande_naam:
                flash(f'Gebruikersnaam {naam_in} is al in gebruik.', 'danger')
                return render_template('admin/user_form.html', actie='Wijzigen', user=user, membership=membership, form_data=request.form, beschikbare_functies=beschikbare_functies)

        # Controleer unieke email
        if email_in and email_in != user.email:
            bestaande_email = User.query.filter(db.func.lower(User.email) == email_in, User.id != user.id).first()
            if bestaande_email:
                flash(f'Het e-mailadres {email_in} is al in gebruik door {bestaande_email.naam}.', 'danger')
                return render_template('admin/user_form.html', actie='Wijzigen', user=user, membership=membership, form_data=request.form, beschikbare_functies=beschikbare_functies)

        user.naam = naam_in
        user.email = email_in
        user.telefoonnummer = telefoonnummer_in
        user.rol = rol
        membership.rol = 'beheerder' if rol == 'platformbeheerder' else rol
        
        # Functies bijwerken voor deze organisatie
        user.functies = [f for f in user.functies if f.organisatie_id != org_id]
        if functie_ids:
            gekozen = Functie.query.filter(Functie.organisatie_id == org_id, Functie.id.in_(functie_ids)).all()
            user.functies.extend(gekozen)

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
            return render_template('admin/user_form.html', actie='Wijzigen', user=user, membership=membership, form_data=request.form, beschikbare_functies=beschikbare_functies)

    return render_template('admin/user_form.html', actie='Wijzigen', user=user, membership=membership, beschikbare_functies=beschikbare_functies)


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


@admin_bp.route('/gebruikers/<int:user_id>/verwijderen', methods=['POST'])
@login_required
@admin_required
def gebruiker_verwijderen(user_id):
    from utils.tenant import get_huidige_organisatie_id
    from models.organisatie import UserOrganisatie
    from models.registration import Registration
    org_id = get_huidige_organisatie_id()

    user = db.get_or_404(User, user_id)
    if user.id == current_user.id:
        flash('U kunt uw eigen account niet verwijderen.', 'danger')
        return redirect(url_for('admin.gebruikers'))

    if user.id == 1:
        flash('De hoofdbeheerder kan niet worden verwijderd.', 'danger')
        return redirect(url_for('admin.gebruikers'))

    # GDPR-01: Controleer of de gebruiker behoort tot de huidige organisatie
    membership = UserOrganisatie.query.filter_by(user_id=user.id, organisatie_id=org_id).first_or_404()

    # Controleer of er een Digidokter gekoppeld is aan dit gebruikersaccount
    dd_count = Digidokter.query.filter_by(user_id=user.id).count()
    if dd_count > 0:
        flash(f'Gebruiker {user.naam} ({user.email}) kan niet worden verwijderd omdat er nog een Digidokter aan dit account is gekoppeld. Verwijder of ontkoppel eerst de Digidokter.', 'danger')
        return redirect(url_for('admin.gebruikers'))

    naam = user.naam

    # Indien de gebruiker ook actief is in andere organisaties: verbreek uitsluitend de koppeling met deze organisatie
    other_links_count = UserOrganisatie.query.filter(
        UserOrganisatie.user_id == user.id,
        UserOrganisatie.organisatie_id != org_id
    ).count()

    if other_links_count > 0:
        db.session.delete(membership)
        db.session.commit()
        flash(f'Gebruiker {naam} is ontkoppeld van deze organisatie. Het gebruikersaccount blijft behouden voor andere organisaties.', 'info')
        return redirect(url_for('admin.gebruikers'))

    # Gebruiker is exclusief aan deze organisatie gekoppeld: voer volledige gegevenswissing uit (Recht op vergetelheid)
    # 1. Re-attribueer mappen en documenten naar de uitvoerende beheerder zodat organisatie-kennis bewaard blijft
    from models.document import Folder, Document
    Folder.query.filter_by(aangemaakt_door_id=user.id).update({'aangemaakt_door_id': current_user.id})
    Document.query.filter_by(aangemaakt_door_id=user.id).update({'aangemaakt_door_id': current_user.id})
    Document.query.filter_by(gewijzigd_door_id=user.id).update({'gewijzigd_door_id': current_user.id})

    # 2. Anonimiseer evaluatieresponses
    from models.evaluation import EvaluationResponse
    EvaluationResponse.query.filter_by(user_id=user.id).update({'user_id': None})

    # 3. Anonimiseer registratie auteur veld
    Registration.query.filter_by(aangemaakt_door_id=user.id).update({'aangemaakt_door_id': None})

    # 4. Opschonen van feedback items, stemmen en reacties van deze gebruiker
    from models.feedback import FeedbackItem, FeedbackVote, FeedbackComment
    FeedbackVote.query.filter_by(user_id=user.id).delete()
    FeedbackComment.query.filter_by(user_id=user.id).delete()
    fb_user_items = FeedbackItem.query.filter_by(user_id=user.id).all()
    if fb_user_items:
        fb_ids = [f.id for f in fb_user_items]
        FeedbackVote.query.filter(FeedbackVote.feedback_id.in_(fb_ids)).delete(synchronize_session=False)
        FeedbackComment.query.filter(FeedbackComment.feedback_id.in_(fb_ids)).delete(synchronize_session=False)
        FeedbackItem.query.filter(FeedbackItem.id.in_(fb_ids)).delete(synchronize_session=False)
    FeedbackItem.query.filter_by(afgesloten_door_id=user.id).update({'afgesloten_door_id': None})

    # 5. Verwijder lidmaatschap en gebruiker
    db.session.delete(membership)
    db.session.delete(user)
    db.session.commit()

    flash(f'Gebruiker {naam} is succesvol verwijderd.', 'success')
    return redirect(url_for('admin.gebruikers'))


# ─── Generieke beheer helper ─────────────────────────────────────────────────

def _beheer_lijst(model, template, naam_veld='naam'):
    from utils.tenant import filter_op_organisatie, get_huidige_organisatie_id
    from utils.stamgegevens import get_usage_counts
    org_id = get_huidige_organisatie_id()
    status_filter = request.args.get('status', 'alle').strip().lower()
    if status_filter not in ('actief', 'inactief', 'alle'):
        status_filter = 'alle'

    query = filter_op_organisatie(model.query, model)
    if status_filter == 'actief':
        query = query.filter(model.actief == True)
    elif status_filter == 'inactief':
        query = query.filter(model.actief == False)

    items = query.order_by(getattr(model, 'volgorde'), getattr(model, naam_veld)).all()
    usage_counts = get_usage_counts(model, org_id)
    return render_template(template, items=items, usage_counts=usage_counts, status_filter=status_filter)


def _beheer_toggle(model, item_id, redirect_endpoint):
    from utils.tenant import get_huidige_organisatie_id
    from utils.stamgegevens import toggle_stamgegeven_status
    org_id = get_huidige_organisatie_id()
    naam, actief = toggle_stamgegeven_status(model, item_id, org_id)
    status_msg = 'geactiveerd' if actief else 'gedeactiveerd'
    flash(f'{naam} {status_msg}.', 'info')
    status_param = request.args.get('status')
    if status_param and status_param in ('actief', 'inactief', 'alle'):
        return redirect(url_for(redirect_endpoint, status=status_param))
    return redirect(url_for(redirect_endpoint))


def _beheer_volgorde(model, item_id, richting, redirect_endpoint):
    """Verplaats een item omhoog of omlaag in de volgorde."""
    from utils.tenant import get_huidige_organisatie_id
    from utils.stamgegevens import wijzig_stamgegeven_volgorde
    org_id = get_huidige_organisatie_id()
    wijzig_stamgegeven_volgorde(model, item_id, richting, org_id)
    status_param = request.args.get('status')
    if status_param and status_param in ('actief', 'inactief', 'alle'):
        return redirect(url_for(redirect_endpoint, status=status_param))
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
    from models.organisatie import UserOrganisatie
    from models.user import User
    org_id = get_huidige_organisatie_id()

    org_users = UserOrganisatie.query.filter_by(organisatie_id=org_id).all()
    beschikbare_gebruikers = [uo.user for uo in org_users if uo.user]

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        actief = request.form.get('actief') == 'on'

        if not email:
            flash('E-mailadres is verplicht.', 'danger')
            return render_template('admin/digidokter_form.html', actie='Nieuw', item=None, gebruikers=beschikbare_gebruikers, form_data=request.form)

        user = User.query.filter(db.func.lower(User.email) == email).first()
        if not user:
            flash(f'Er bestaat geen gebruiker met e-mailadres "{email}". Maak deze gebruiker eerst aan in Gebruikersbeheer.', 'danger')
            return render_template('admin/digidokter_form.html', actie='Nieuw', item=None, gebruikers=beschikbare_gebruikers, form_data=request.form)

        uo = UserOrganisatie.query.filter_by(user_id=user.id, organisatie_id=org_id).first()
        if not uo:
            flash(f'Gebruiker {user.naam} ({user.email}) is nog niet gekoppeld aan deze organisatie.', 'danger')
            return render_template('admin/digidokter_form.html', actie='Nieuw', item=None, gebruikers=beschikbare_gebruikers, form_data=request.form)

        naam_invoer = request.form.get('naam', '').strip()
        naam = naam_invoer if naam_invoer else user.naam

        bestaande_dd = Digidokter.query.filter(
            Digidokter.organisatie_id == org_id,
            db.or_(
                Digidokter.user_id == user.id,
                db.func.lower(Digidokter.naam) == db.func.lower(naam)
            )
        ).first()
        if bestaande_dd:
            flash(f'Er bestaat in deze organisatie al een Digidokter genaamd "{naam}" of gekoppeld aan e-mailadres {user.email}.', 'danger')
            return render_template('admin/digidokter_form.html', actie='Nieuw', item=None, gebruikers=beschikbare_gebruikers, form_data=request.form)

        max_volgorde = db.session.query(db.func.max(Digidokter.volgorde)).filter(Digidokter.organisatie_id == org_id).scalar() or 0
        dd = Digidokter(
            naam=naam,
            user_id=user.id,
            volgorde=max_volgorde + 1,
            organisatie_id=org_id,
            actief=actief
        )
        db.session.add(dd)
        db.session.commit()
        flash(f'Digidokter {naam} ({user.email}) succesvol toegevoegd.', 'success')
        return redirect(url_for('admin.digidokters'))

    return render_template('admin/digidokter_form.html', actie='Nieuw', item=None, gebruikers=beschikbare_gebruikers)


@admin_bp.route('/digidokters/<int:item_id>/wijzig', methods=['GET', 'POST'])
@login_required
@admin_required
def digidokter_wijzigen(item_id):
    from utils.tenant import get_huidige_organisatie_id
    from models.organisatie import UserOrganisatie
    from models.user import User
    org_id = get_huidige_organisatie_id()
    item = db.get_or_404(Digidokter, item_id)
    
    if item.organisatie_id != org_id:
        from flask import abort
        abort(403)

    org_users = UserOrganisatie.query.filter_by(organisatie_id=org_id).all()
    beschikbare_gebruikers = [uo.user for uo in org_users if uo.user]
        
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        actief = request.form.get('actief') == 'on'
        naam_invoer = request.form.get('naam', '').strip()
        doel_naam = naam_invoer if naam_invoer else item.naam

        if not email:
            flash('E-mailadres is verplicht.', 'danger')
            return render_template('admin/digidokter_form.html', actie='Wijzigen', item=item, gebruikers=beschikbare_gebruikers, form_data=request.form)

        user = User.query.filter(db.func.lower(User.email) == email).first()
        if not user:
            flash(f'Er bestaat geen gebruiker met e-mailadres "{email}". Maak deze gebruiker eerst aan in Gebruikersbeheer.', 'danger')
            return render_template('admin/digidokter_form.html', actie='Wijzigen', item=item, gebruikers=beschikbare_gebruikers, form_data=request.form)

        uo = UserOrganisatie.query.filter_by(user_id=user.id, organisatie_id=org_id).first()
        if not uo:
            flash(f'Gebruiker {user.naam} ({user.email}) is niet gekoppeld aan deze organisatie.', 'danger')
            return render_template('admin/digidokter_form.html', actie='Wijzigen', item=item, gebruikers=beschikbare_gebruikers, form_data=request.form)

        bestaande_dd = Digidokter.query.filter(
            Digidokter.organisatie_id == org_id,
            Digidokter.id != item.id,
            db.or_(
                Digidokter.user_id == user.id,
                db.func.lower(Digidokter.naam) == db.func.lower(doel_naam)
            )
        ).first()
        if bestaande_dd:
            flash(f'Er bestaat in deze organisatie al een andere Digidokter genaamd "{doel_naam}" of gekoppeld aan e-mailadres {user.email}.', 'danger')
            return render_template('admin/digidokter_form.html', actie='Wijzigen', item=item, gebruikers=beschikbare_gebruikers, form_data=request.form)

        item.user_id = user.id
        item.naam = doel_naam
        item.actief = actief
        db.session.commit()
        flash(f'Digidokter {item.naam} bijgewerkt.', 'success')
        return redirect(url_for('admin.digidokters'))

    return render_template('admin/digidokter_form.html', actie='Wijzigen', item=item, gebruikers=beschikbare_gebruikers)


@admin_bp.route('/digidokters/<int:item_id>/toggle')
@login_required
@admin_required
def digidokter_toggle(item_id):
    return _beheer_toggle(Digidokter, item_id, 'admin.digidokters')


@admin_bp.route('/digidokters/<int:item_id>/verwijderen', methods=['POST'])
@login_required
@admin_required
def digidokter_verwijderen(item_id):
    from utils.tenant import get_huidige_organisatie_id
    org_id = get_huidige_organisatie_id()
    dd = db.get_or_404(Digidokter, item_id)

    if dd.organisatie_id != org_id:
        from flask import abort
        abort(403)

    if len(dd.registraties) > 0:
        flash(f'Digidokter {dd.naam} kan niet worden verwijderd omdat er nog {len(dd.registraties)} registratie(s) op zijn/haar naam staan. U kunt de status wel op gedeactiveerd zetten.', 'warning')
        return redirect(url_for('admin.digidokters'))

    naam = dd.naam
    db.session.delete(dd)
    db.session.commit()
    flash(f'Digidokter {naam} is succesvol verwijderd.', 'success')
    return redirect(url_for('admin.digidokters'))


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
    actieve_items = AgeCategory.query.filter_by(organisatie_id=org_id, actief=True).order_by(AgeCategory.volgorde, AgeCategory.naam).all()

    if request.method == 'POST':
        naam = request.form.get('naam', '').strip()
        if not naam:
            flash('Naam is verplicht.', 'danger')
            return render_template('admin/item_form.html', titel='Leeftijdscategorie', actie='Nieuw',
                                   item=None, terug_url=url_for('admin.leeftijdscategorieën'),
                                   actieve_items=actieve_items, toon_mapping=True)
        max_volgorde = db.session.query(db.func.max(AgeCategory.volgorde)).filter(AgeCategory.organisatie_id == org_id).scalar() or 0
        is_actief = request.form.get('actief') == 'on' if 'actief' in request.form else True
        mapped_to_id = request.form.get('mapped_to_id', type=int) or None if not is_actief else None
        if mapped_to_id:
            target = db.session.get(AgeCategory, mapped_to_id)
            if not target or target.organisatie_id != org_id or not target.actief:
                mapped_to_id = None
        db.session.add(AgeCategory(naam=naam, volgorde=max_volgorde + 1, organisatie_id=org_id,
                                   actief=is_actief, mapped_to_id=mapped_to_id))
        db.session.commit()
        flash(f'Leeftijdscategorie {naam} toegevoegd.', 'success')
        return redirect(url_for('admin.leeftijdscategorieën'))
    return render_template('admin/item_form.html', titel='Leeftijdscategorie', actie='Nieuw',
                           item=None, terug_url=url_for('admin.leeftijdscategorieën'),
                           actieve_items=actieve_items, toon_mapping=True)


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
        
    actieve_items = AgeCategory.query.filter_by(organisatie_id=org_id, actief=True).filter(AgeCategory.id != item_id).order_by(AgeCategory.volgorde, AgeCategory.naam).all()

    if request.method == 'POST':
        item.naam = request.form.get('naam', item.naam).strip()
        item.actief = request.form.get('actief') == 'on'
        if item.actief:
            item.mapped_to_id = None
        else:
            mapped_to_id = request.form.get('mapped_to_id', type=int) or None
            if mapped_to_id and mapped_to_id != item.id:
                target = db.session.get(AgeCategory, mapped_to_id)
                if target and target.organisatie_id == org_id and target.actief:
                    item.mapped_to_id = mapped_to_id
                else:
                    item.mapped_to_id = None
            else:
                item.mapped_to_id = None
        db.session.commit()
        flash(f'{item.naam} bijgewerkt.', 'success')
        return redirect(url_for('admin.leeftijdscategorieën'))
    return render_template('admin/item_form.html', titel='Leeftijdscategorie', actie='Wijzigen',
                           item=item, terug_url=url_for('admin.leeftijdscategorieën'),
                           actieve_items=actieve_items, toon_mapping=True)


@admin_bp.route('/leeftijdscategorieën/<int:item_id>/toggle')
@login_required
@admin_required
def leeftijdscategorie_toggle(item_id):
    return _beheer_toggle(AgeCategory, item_id, 'admin.leeftijdscategorieën')


@admin_bp.route('/leeftijdscategorieën/<int:item_id>/verwijderen', methods=['POST'])
@login_required
@admin_required
def leeftijdscategorie_verwijderen(item_id):
    from utils.tenant import get_huidige_organisatie_id
    from models.registration import Registration
    org_id = get_huidige_organisatie_id()
    item = db.get_or_404(AgeCategory, item_id)

    if item.organisatie_id != org_id:
        from flask import abort
        abort(403)

    count = Registration.query.filter_by(leeftijdscategorie_id=item.id).count()
    if count > 0:
        flash(f'Leeftijdscategorie "{item.naam}" kan niet worden verwijderd omdat er nog {count} registratie(s) aan gekoppeld zijn. U kunt de status wel op gedeactiveerd zetten.', 'warning')
        return redirect(url_for('admin.leeftijdscategorieën'))

    naam = item.naam
    db.session.delete(item)
    db.session.commit()
    flash(f'Leeftijdscategorie "{naam}" is succesvol verwijderd.', 'success')
    return redirect(url_for('admin.leeftijdscategorieën'))


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
    actieve_items = Device.query.filter_by(organisatie_id=org_id, actief=True).order_by(Device.volgorde, Device.naam).all()

    if request.method == 'POST':
        naam = request.form.get('naam', '').strip()
        if not naam:
            flash('Naam is verplicht.', 'danger')
            return render_template('admin/item_form.html', titel='Toestel', actie='Nieuw',
                                   item=None, terug_url=url_for('admin.toestellen'),
                                   actieve_items=actieve_items, toon_mapping=True)
        max_volgorde = db.session.query(db.func.max(Device.volgorde)).filter(Device.organisatie_id == org_id).scalar() or 0
        is_actief = request.form.get('actief') == 'on' if 'actief' in request.form else True
        mapped_to_id = request.form.get('mapped_to_id', type=int) or None if not is_actief else None
        if mapped_to_id:
            target = db.session.get(Device, mapped_to_id)
            if not target or target.organisatie_id != org_id or not target.actief:
                mapped_to_id = None
        db.session.add(Device(naam=naam, volgorde=max_volgorde + 1, organisatie_id=org_id,
                              actief=is_actief, mapped_to_id=mapped_to_id))
        db.session.commit()
        flash(f'Toestel {naam} toegevoegd.', 'success')
        return redirect(url_for('admin.toestellen'))
    return render_template('admin/item_form.html', titel='Toestel', actie='Nieuw',
                           item=None, terug_url=url_for('admin.toestellen'),
                           actieve_items=actieve_items, toon_mapping=True)


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
        
    actieve_items = Device.query.filter_by(organisatie_id=org_id, actief=True).filter(Device.id != item_id).order_by(Device.volgorde, Device.naam).all()

    if request.method == 'POST':
        item.naam = request.form.get('naam', item.naam).strip()
        item.actief = request.form.get('actief') == 'on'
        if item.actief:
            item.mapped_to_id = None
        else:
            mapped_to_id = request.form.get('mapped_to_id', type=int) or None
            if mapped_to_id and mapped_to_id != item.id:
                target = db.session.get(Device, mapped_to_id)
                if target and target.organisatie_id == org_id and target.actief:
                    item.mapped_to_id = mapped_to_id
                else:
                    item.mapped_to_id = None
            else:
                item.mapped_to_id = None
        db.session.commit()
        flash(f'{item.naam} bijgewerkt.', 'success')
        return redirect(url_for('admin.toestellen'))
    return render_template('admin/item_form.html', titel='Toestel', actie='Wijzigen',
                           item=item, terug_url=url_for('admin.toestellen'),
                           actieve_items=actieve_items, toon_mapping=True)



@admin_bp.route('/toestellen/<int:item_id>/toggle')
@login_required
@admin_required
def toestel_toggle(item_id):
    return _beheer_toggle(Device, item_id, 'admin.toestellen')


@admin_bp.route('/toestellen/<int:item_id>/verwijderen', methods=['POST'])
@login_required
@admin_required
def toestel_verwijderen(item_id):
    from utils.tenant import get_huidige_organisatie_id
    from models.registration import Registration
    org_id = get_huidige_organisatie_id()
    item = db.get_or_404(Device, item_id)

    if item.organisatie_id != org_id:
        from flask import abort
        abort(403)

    count = Registration.query.filter_by(toestel_id=item.id).count()
    if count > 0:
        flash(f'Toestel "{item.naam}" kan niet worden verwijderd omdat er nog {count} registratie(s) aan gekoppeld zijn. U kunt de status wel op gedeactiveerd zetten.', 'warning')
        return redirect(url_for('admin.toestellen'))

    naam = item.naam
    db.session.delete(item)
    db.session.commit()
    flash(f'Toestel "{naam}" is succesvol verwijderd.', 'success')
    return redirect(url_for('admin.toestellen'))


@admin_bp.route('/toestellen/<int:item_id>/volgorde/<richting>')
@login_required
@admin_required
def toestel_volgorde(item_id, richting):
    return _beheer_volgorde(Device, item_id, richting, 'admin.toestellen')


# ─── Herkomsten ──────────────────────────────────────────────────────────────

@admin_bp.route('/herkomsten')
@login_required
@admin_required
def herkomsten():
    return _beheer_lijst(Herkomst, 'admin/herkomsten.html')


@admin_bp.route('/herkomsten/nieuw', methods=['GET', 'POST'])
@login_required
@admin_required
def herkomst_nieuw():
    from utils.tenant import get_huidige_organisatie_id
    org_id = get_huidige_organisatie_id()

    if request.method == 'POST':
        naam = request.form.get('naam', '').strip()
        if not naam:
            flash('Naam is verplicht.', 'danger')
            return render_template('admin/item_form.html', titel='Herkomst', actie='Nieuw',
                                   item=None, terug_url=url_for('admin.herkomsten'))
        max_volgorde = db.session.query(db.func.max(Herkomst.volgorde)).filter(Herkomst.organisatie_id == org_id).scalar() or 0
        db.session.add(Herkomst(naam=naam, volgorde=max_volgorde + 1, organisatie_id=org_id,
                               actief=request.form.get('actief') == 'on' if 'actief' in request.form else True))
        db.session.commit()
        flash(f'Herkomst {naam} toegevoegd.', 'success')
        return redirect(url_for('admin.herkomsten'))
    return render_template('admin/item_form.html', titel='Herkomst', actie='Nieuw',
                           item=None, terug_url=url_for('admin.herkomsten'))


@admin_bp.route('/herkomsten/<int:item_id>/wijzig', methods=['GET', 'POST'])
@login_required
@admin_required
def herkomst_wijzigen(item_id):
    from utils.tenant import get_huidige_organisatie_id
    org_id = get_huidige_organisatie_id()
    item = db.get_or_404(Herkomst, item_id)
    
    if item.organisatie_id != org_id:
        from flask import abort
        abort(403)
        
    if request.method == 'POST':
        item.naam = request.form.get('naam', item.naam).strip()
        item.actief = request.form.get('actief') == 'on'
        db.session.commit()
        flash(f'{item.naam} bijgewerkt.', 'success')
        return redirect(url_for('admin.herkomsten'))
    return render_template('admin/item_form.html', titel='Herkomst', actie='Wijzigen',
                           item=item, terug_url=url_for('admin.herkomsten'))


@admin_bp.route('/herkomsten/<int:item_id>/toggle')
@login_required
@admin_required
def herkomst_toggle(item_id):
    return _beheer_toggle(Herkomst, item_id, 'admin.herkomsten')


@admin_bp.route('/herkomsten/<int:item_id>/verwijderen', methods=['POST'])
@login_required
@admin_required
def herkomst_verwijderen(item_id):
    from utils.tenant import get_huidige_organisatie_id
    from models.registration import Registration
    org_id = get_huidige_organisatie_id()
    item = db.get_or_404(Herkomst, item_id)

    if item.organisatie_id != org_id:
        from flask import abort
        abort(403)

    count = Registration.query.filter_by(herkomst_id=item.id).count()
    if count > 0:
        flash(f'Herkomst "{item.naam}" kan niet worden verwijderd omdat er nog {count} registratie(s) aan gekoppeld zijn. U kunt de status wel op gedeactiveerd zetten.', 'warning')
        return redirect(url_for('admin.herkomsten'))

    naam = item.naam
    db.session.delete(item)
    db.session.commit()
    flash(f'Herkomst "{naam}" is succesvol verwijderd.', 'success')
    return redirect(url_for('admin.herkomsten'))


@admin_bp.route('/herkomsten/<int:item_id>/volgorde/<richting>')
@login_required
@admin_required
def herkomst_volgorde(item_id, richting):
    return _beheer_volgorde(Herkomst, item_id, richting, 'admin.herkomsten')


# ─── Genderidentiteiten ──────────────────────────────────────────────────────

@admin_bp.route('/genderidentiteiten')
@login_required
@admin_required
def genderidentiteiten():
    return _beheer_lijst(GenderIdentity, 'admin/genderidentiteiten.html')


@admin_bp.route('/genderidentiteiten/nieuw', methods=['GET', 'POST'])
@login_required
@admin_required
def genderidentiteit_nieuw():
    from utils.tenant import get_huidige_organisatie_id
    org_id = get_huidige_organisatie_id()

    if request.method == 'POST':
        naam = request.form.get('naam', '').strip()
        if not naam:
            flash('Omschrijving / naam is verplicht.', 'danger')
            return render_template('admin/item_form.html', titel='Genderidentiteit', actie='Nieuw',
                                   item=None, terug_url=url_for('admin.genderidentiteiten'))
        max_volgorde = db.session.query(db.func.max(GenderIdentity.volgorde)).filter(GenderIdentity.organisatie_id == org_id).scalar() or 0
        db.session.add(GenderIdentity(naam=naam, volgorde=max_volgorde + 1, organisatie_id=org_id,
                                     actief=request.form.get('actief') == 'on' if 'actief' in request.form else True))
        db.session.commit()
        flash(f'Genderidentiteit {naam} toegevoegd.', 'success')
        return redirect(url_for('admin.genderidentiteiten'))
    return render_template('admin/item_form.html', titel='Genderidentiteit', actie='Nieuw',
                           item=None, terug_url=url_for('admin.genderidentiteiten'))


@admin_bp.route('/genderidentiteiten/<int:item_id>/wijzig', methods=['GET', 'POST'])
@login_required
@admin_required
def genderidentiteit_wijzigen(item_id):
    from utils.tenant import get_huidige_organisatie_id
    org_id = get_huidige_organisatie_id()
    item = db.get_or_404(GenderIdentity, item_id)
    
    if item.organisatie_id != org_id:
        from flask import abort
        abort(403)
        
    if request.method == 'POST':
        item.naam = request.form.get('naam', item.naam).strip()
        item.actief = request.form.get('actief') == 'on'
        db.session.commit()
        flash(f'Genderidentiteit {item.naam} bijgewerkt.', 'success')
        return redirect(url_for('admin.genderidentiteiten'))
    return render_template('admin/item_form.html', titel='Genderidentiteit', actie='Wijzigen',
                           item=item, terug_url=url_for('admin.genderidentiteiten'))


@admin_bp.route('/genderidentiteiten/<int:item_id>/toggle')
@login_required
@admin_required
def genderidentiteit_toggle(item_id):
    return _beheer_toggle(GenderIdentity, item_id, 'admin.genderidentiteiten')


@admin_bp.route('/genderidentiteiten/<int:item_id>/verwijderen', methods=['POST'])
@login_required
@admin_required
def genderidentiteit_verwijderen(item_id):
    from utils.tenant import get_huidige_organisatie_id
    org_id = get_huidige_organisatie_id()
    item = db.get_or_404(GenderIdentity, item_id)

    if item.organisatie_id != org_id:
        from flask import abort
        abort(403)

    count = (
        Registration.query
        .filter(Registration.organisatie_id == org_id)
        .filter(Registration.gender_identity_id == item.id)
        .count()
    )
    if count > 0:
        flash(f'Genderidentiteit "{item.naam}" kan niet worden verwijderd omdat er nog {count} registratie(s) aan gekoppeld zijn. U kunt de status wel op gedeactiveerd zetten.', 'warning')
        return redirect(url_for('admin.genderidentiteiten'))

    naam = item.naam
    db.session.delete(item)
    db.session.commit()
    flash(f'Genderidentiteit "{naam}" is succesvol verwijderd.', 'success')
    return redirect(url_for('admin.genderidentiteiten'))


@admin_bp.route('/genderidentiteiten/<int:item_id>/volgorde/<richting>')
@login_required
@admin_required
def genderidentiteit_volgorde(item_id, richting):
    return _beheer_volgorde(GenderIdentity, item_id, richting, 'admin.genderidentiteiten')


# ─── Functies ────────────────────────────────────────────────────────────────

@admin_bp.route('/functies')
@login_required
@admin_required
def functies():
    return _beheer_lijst(Functie, 'admin/functies.html')


@admin_bp.route('/functies/nieuw', methods=['GET', 'POST'])
@login_required
@admin_required
def functie_nieuw():
    from utils.tenant import get_huidige_organisatie_id
    org_id = get_huidige_organisatie_id()

    if request.method == 'POST':
        naam = request.form.get('naam', '').strip()
        if not naam:
            flash('Functienaam is verplicht.', 'danger')
            return render_template('admin/item_form.html', titel='Functie', actie='Nieuw',
                                   item=None, terug_url=url_for('admin.functies'))
        max_volgorde = db.session.query(db.func.max(Functie.volgorde)).filter(Functie.organisatie_id == org_id).scalar() or 0
        db.session.add(Functie(naam=naam, volgorde=max_volgorde + 1, organisatie_id=org_id,
                               actief=request.form.get('actief') == 'on' if 'actief' in request.form else True))
        db.session.commit()
        flash(f'Functie {naam} toegevoegd.', 'success')
        return redirect(url_for('admin.functies'))
    return render_template('admin/item_form.html', titel='Functie', actie='Nieuw',
                           item=None, terug_url=url_for('admin.functies'))


@admin_bp.route('/functies/<int:item_id>/wijzig', methods=['GET', 'POST'])
@login_required
@admin_required
def functie_wijzigen(item_id):
    from utils.tenant import get_huidige_organisatie_id
    org_id = get_huidige_organisatie_id()
    item = db.get_or_404(Functie, item_id)
    
    if item.organisatie_id != org_id:
        from flask import abort
        abort(403)
        
    if request.method == 'POST':
        item.naam = request.form.get('naam', item.naam).strip()
        item.actief = request.form.get('actief') == 'on'
        db.session.commit()
        flash(f'Functie {item.naam} bijgewerkt.', 'success')
        return redirect(url_for('admin.functies'))
    return render_template('admin/item_form.html', titel='Functie', actie='Wijzigen',
                           item=item, terug_url=url_for('admin.functies'))


@admin_bp.route('/functies/<int:item_id>/toggle')
@login_required
@admin_required
def functie_toggle(item_id):
    return _beheer_toggle(Functie, item_id, 'admin.functies')


@admin_bp.route('/functies/<int:item_id>/verwijderen', methods=['POST'])
@login_required
@admin_required
def functie_verwijderen(item_id):
    from utils.tenant import get_huidige_organisatie_id
    org_id = get_huidige_organisatie_id()
    item = db.get_or_404(Functie, item_id)

    if item.organisatie_id != org_id:
        from flask import abort
        abort(403)

    count = db.session.query(user_functies).filter_by(functie_id=item.id).count()
    if count > 0:
        flash(f'Functie "{item.naam}" kan niet worden verwijderd omdat deze nog is toegekend aan {count} gebruiker(s). U kunt de status wel op gedeactiveerd zetten.', 'warning')
        return redirect(url_for('admin.functies'))

    naam = item.naam
    db.session.delete(item)
    db.session.commit()
    flash(f'Functie "{naam}" is succesvol verwijderd.', 'success')
    return redirect(url_for('admin.functies'))


@admin_bp.route('/functies/<int:item_id>/volgorde/<richting>')
@login_required
@admin_required
def functie_volgorde(item_id, richting):
    return _beheer_volgorde(Functie, item_id, richting, 'admin.functies')


@admin_bp.route('/backup')
@login_required
@admin_required
@limiter.limit("5 per minute; 20 per hour")
def backup():
    import json
    from datetime import datetime
    from flask import Response
    from models.organisatie import Organisatie
    from utils.tenant import get_huidige_organisatie_id
    from utils.backup_handler import maak_backup

    org_id = get_huidige_organisatie_id()
    org = db.session.get(Organisatie, org_id)

    backup_dict = maak_backup(org_id)
    json_bytes = json.dumps(backup_dict, indent=2, ensure_ascii=False).encode('utf-8')
    date_str = datetime.now().strftime('%Y%m%d_%H%M%S')
    org_slug = org.slug if org else 'organisatie'
    filename = f"backup_{org_slug}_{date_str}.json"

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
    from utils.backup_handler import herstel_backup

    org_id = get_huidige_organisatie_id()

    if request.method == 'POST':
        file = request.files.get('backup_file')
        if not file or file.filename == '':
            flash('Gelieve een geldig JSON-bestand te selecteren.', 'danger')
            return redirect(url_for('admin.restore'))

        success, msg = herstel_backup(org_id, file, current_user.id)
        if success:
            flash(msg, 'success')
            return redirect(url_for('admin.gebruikers'))
        else:
            flash(msg, 'danger')
            return redirect(url_for('admin.restore'))

    return render_template('admin/restore.html')


# ─── Activiteitstypes ───────────────────────────────────────────────────────

@admin_bp.route('/activiteitstypes')
@login_required
@admin_required
def activiteitstypes():
    from utils.tenant import filter_op_organisatie, get_huidige_organisatie_id
    from models.agenda import AgendaItem
    from models.evaluation import EvaluationForm, EvaluationResponse
    org_id = get_huidige_organisatie_id()
    status_filter = request.args.get('status', 'alle').strip().lower()
    if status_filter not in ('actief', 'inactief', 'alle'):
        status_filter = 'alle'

    query = filter_op_organisatie(ActivityType.query, ActivityType)
    if status_filter == 'actief':
        query = query.filter(ActivityType.actief == True)
    elif status_filter == 'inactief':
        query = query.filter(ActivityType.actief == False)

    items = query.order_by(ActivityType.volgorde, ActivityType.naam).all()

    agenda_counts = dict(
        db.session.query(AgendaItem.type_id, db.func.count(AgendaItem.id))
        .filter_by(organisatie_id=org_id)
        .group_by(AgendaItem.type_id)
        .all()
    )
    eval_counts = dict(
        db.session.query(EvaluationForm.activity_type_id, db.func.count(EvaluationResponse.id))
        .join(EvaluationResponse, EvaluationResponse.form_id == EvaluationForm.id)
        .filter(EvaluationForm.organisatie_id == org_id)
        .group_by(EvaluationForm.activity_type_id)
        .all()
    )
    return render_template('admin/activiteitstypes.html', items=items, agenda_counts=agenda_counts, eval_counts=eval_counts, status_filter=status_filter)


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
        heeft_evaluatie = request.form.get('heeft_evaluatie') == 'on'
        kleur = request.form.get('kleur', 'blue')
        item = ActivityType(naam=naam, actief=actief, heeft_evaluatie=heeft_evaluatie, kleur=kleur, volgorde=max_volgorde + 1)
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
        item.heeft_evaluatie = request.form.get('heeft_evaluatie') == 'on'
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


@admin_bp.route('/activiteitstypes/<int:item_id>/verwijderen', methods=['POST'])
@login_required
@admin_required
def activiteitstype_verwijderen(item_id):
    from utils.tenant import get_huidige_organisatie_id
    from models.agenda import AgendaItem
    from models.evaluation import EvaluationForm, EvaluationResponse
    org_id = get_huidige_organisatie_id()
    item = db.get_or_404(ActivityType, item_id)

    if item.organisatie_id != org_id:
        from flask import abort
        abort(403)

    agenda_count = AgendaItem.query.filter_by(type_id=item.id).count()
    if agenda_count > 0:
        flash(f'Activiteitstype "{item.naam}" kan niet worden verwijderd omdat er nog {agenda_count} agenda-activiteit(en) aan gekoppeld zijn. U kunt de status wel op gedeactiveerd zetten.', 'warning')
        return redirect(url_for('admin.activiteitstypes'))

    eval_form = EvaluationForm.query.filter_by(activity_type_id=item.id, organisatie_id=org_id).first()
    if eval_form:
        resp_count = EvaluationResponse.query.filter_by(form_id=eval_form.id).count()
        if resp_count > 0:
            flash(f'Activiteitstype "{item.naam}" kan niet worden verwijderd omdat er al {resp_count} ingevulde evaluatie(s) aan gekoppeld zijn. U kunt de status wel op gedeactiveerd zetten.', 'warning')
            return redirect(url_for('admin.activiteitstypes'))
        # Als er een evaluatieformulier is zonder reacties: ruim het formulier en de vragen op
        db.session.delete(eval_form)
        db.session.flush()

    naam = item.naam
    db.session.delete(item)
    db.session.commit()
    flash(f'Activiteitstype "{naam}" is succesvol verwijderd.', 'success')
    return redirect(url_for('admin.activiteitstypes'))


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
    from utils.tenant import filter_op_organisatie, get_huidige_organisatie_id
    from models.agenda import AgendaItem
    org_id = get_huidige_organisatie_id()
    status_filter = request.args.get('status', 'alle').strip().lower()
    if status_filter not in ('actief', 'inactief', 'alle'):
        status_filter = 'alle'

    query = filter_op_organisatie(Location.query, Location)
    if status_filter == 'actief':
        query = query.filter(Location.actief == True)
    elif status_filter == 'inactief':
        query = query.filter(Location.actief == False)

    items = query.order_by(Location.volgorde, Location.naam).all()
    agenda_counts = dict(
        db.session.query(AgendaItem.locatie_id, db.func.count(AgendaItem.id))
        .filter_by(organisatie_id=org_id)
        .group_by(AgendaItem.locatie_id)
        .all()
    )
    reg_counts = dict(
        db.session.query(Registration.locatie_id, db.func.count(Registration.id))
        .filter_by(organisatie_id=org_id)
        .group_by(Registration.locatie_id)
        .all()
    )
    usage_counts = {}
    for lid in set(list(agenda_counts.keys()) + list(reg_counts.keys())):
        usage_counts[lid] = agenda_counts.get(lid, 0) + reg_counts.get(lid, 0)
    return render_template('admin/locaties.html', items=items, usage_counts=usage_counts, status_filter=status_filter)


@admin_bp.route('/locaties/nieuw', methods=['GET', 'POST'])
@login_required
@admin_required
def locatie_nieuw():
    from utils.tenant import get_huidige_organisatie_id, set_organisatie_id_op_model
    org_id = get_huidige_organisatie_id()
    
    if request.method == 'POST':
        naam = request.form.get('naam', '').strip()
        gebruikt_voor_consultaties = request.form.get('gebruikt_voor_consultaties') == 'on'
        if not naam:
            flash('Naam is verplicht.', 'danger')
            return render_template('admin/item_form.html', titel='Locatie', actie='Toevoegen', item=None, terug_url=url_for('admin.locaties'))
            
        existing = Location.query.filter_by(organisatie_id=org_id, naam=naam).first()
        if existing:
            flash('Deze locatie bestaat al.', 'danger')
            return render_template('admin/item_form.html', titel='Locatie', actie='Toevoegen', item=None, form_data=request.form, terug_url=url_for('admin.locaties'))
            
        max_volgorde = db.session.query(db.func.max(Location.volgorde)).filter_by(organisatie_id=org_id).scalar() or 0
        item = Location(naam=naam, actief=True, volgorde=max_volgorde + 1, gebruikt_voor_consultaties=gebruikt_voor_consultaties)
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
        item.gebruikt_voor_consultaties = request.form.get('gebruikt_voor_consultaties') == 'on'
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


@admin_bp.route('/locaties/<int:item_id>/verwijderen', methods=['POST'])
@login_required
@admin_required
def locatie_verwijderen(item_id):
    from utils.tenant import get_huidige_organisatie_id
    from models.agenda import AgendaItem
    org_id = get_huidige_organisatie_id()
    item = db.get_or_404(Location, item_id)

    if item.organisatie_id != org_id:
        from flask import abort
        abort(403)

    agenda_count = AgendaItem.query.filter_by(locatie_id=item.id).count()
    reg_count = Registration.query.filter_by(locatie_id=item.id).count()
    if agenda_count > 0 or reg_count > 0:
        redenen = []
        if reg_count > 0:
            redenen.append(f'{reg_count} consultatie-registratie(s)')
        if agenda_count > 0:
            redenen.append(f'{agenda_count} agenda-activiteit(en)')
        flash(f'Locatie "{item.naam}" kan niet worden verwijderd omdat er nog {" en ".join(redenen)} aan gekoppeld zijn. U kunt de status wel op gedeactiveerd zetten.', 'warning')
        return redirect(url_for('admin.locaties'))

    naam = item.naam
    db.session.delete(item)
    db.session.commit()
    flash(f'Locatie "{naam}" is succesvol verwijderd.', 'success')
    return redirect(url_for('admin.locaties'))


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
@platform_admin_required
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