from datetime import datetime, timezone
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from extensions import db
from models.organisatie import Organisatie, UserOrganisatie
from models.user import User
from utils.decorators import platform_admin_required

platform_bp = Blueprint('platform', __name__, url_prefix='/platform')

@platform_bp.route('/dashboard')
@login_required
@platform_admin_required
def dashboard():
    total_orgs = Organisatie.query.count()
    active_orgs = Organisatie.query.filter_by(actief=True).count()
    total_users = User.query.count()
    total_links = UserOrganisatie.query.count()
    return render_template(
        'platform/dashboard.html',
        total_orgs=total_orgs,
        active_orgs=active_orgs,
        total_users=total_users,
        total_links=total_links
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
    all_orgs = Organisatie.query.order_by(Organisatie.naam).all()
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
