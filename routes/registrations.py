"""Registraties routes: lijst, toevoegen, bekijken, wijzigen."""
from datetime import date
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from extensions import db
from models.registration import Registration
from models.digidokter import Digidokter
from models.age_category import AgeCategory
from models.device import Device
from models.herkomst import Herkomst
from sqlalchemy.orm import joinedload
from utils.decorators import writer_required

reg_bp = Blueprint('reg', __name__)

PAGINA_GROOTTE = 20


def _keuzelijsten():
    """Haal actieve keuzelijsten op voor formulieren."""
    from utils.tenant import filter_op_organisatie
    return {
        'digidokters': filter_op_organisatie(Digidokter.query.filter_by(actief=True), Digidokter).order_by(Digidokter.volgorde, Digidokter.naam).all(),
        'leeftijdscategorieën': filter_op_organisatie(AgeCategory.query.filter_by(actief=True), AgeCategory).order_by(AgeCategory.volgorde, AgeCategory.naam).all(),
        'toestellen': filter_op_organisatie(Device.query.filter_by(actief=True), Device).order_by(Device.volgorde, Device.naam).all(),
        'herkomsten': filter_op_organisatie(Herkomst.query.filter_by(actief=True), Herkomst).order_by(Herkomst.volgorde, Herkomst.naam).all(),
    }


@reg_bp.route('/')
@login_required
def index():
    return redirect(url_for('reg.lijst'))


@reg_bp.route('/registraties')
@login_required
def lijst():
    pagina = request.args.get('pagina', 1, type=int)
    zoek = request.args.get('zoek', '').strip()
    filter_digidokter = request.args.get('digidokter', 0, type=int)
    filter_toestel = request.args.get('toestel', type=int) or request.args.get('toesteltype', 0, type=int)
    filter_leeftijd = request.args.get('leeftijd', type=int) or request.args.get('leeftijdscategorie', 0, type=int)
    filter_geslacht = request.args.get('geslacht', '').strip().lower()
    filter_datum_van = request.args.get('datum_van', '')
    filter_datum_tot = request.args.get('datum_tot', '')
    sort_by = request.args.get('sort_by', 'datum').strip()
    direction = request.args.get('direction', 'desc').strip()

    from utils.tenant import filter_op_organisatie
    query = (
        filter_op_organisatie(Registration.query, Registration)
        .options(
            joinedload(Registration.digidokter),
            joinedload(Registration.leeftijdscategorie).joinedload(AgeCategory.mapped_to),
            joinedload(Registration.toestel).joinedload(Device.mapped_to),
            joinedload(Registration.herkomst)
        )
    )

    if zoek:
        query = query.filter(
            db.or_(
                Registration.client.ilike(f'%{zoek}%'),
                Registration.onderwerp.ilike(f'%{zoek}%'),
                Registration.registratienummer.ilike(f'%{zoek}%'),
                Registration.herkomst.has(Herkomst.naam.ilike(f'%{zoek}%')),
            )
        )
    if filter_digidokter:
        query = query.filter(Registration.digidokter_id == filter_digidokter)
    if filter_toestel:
        mapped_toestel_ids = [t.id for t in Device.query.filter_by(mapped_to_id=filter_toestel).all()]
        query = query.filter(Registration.toestel_id.in_([filter_toestel] + mapped_toestel_ids))
    if filter_leeftijd:
        mapped_leeftijd_ids = [c.id for c in AgeCategory.query.filter_by(mapped_to_id=filter_leeftijd).all()]
        query = query.filter(Registration.leeftijdscategorie_id.in_([filter_leeftijd] + mapped_leeftijd_ids))
    if filter_geslacht in ('man', 'vrouw'):
        query = query.filter(Registration.geslacht == filter_geslacht)
    elif filter_geslacht in ('onbekend', 'geen'):
        query = query.filter(
            db.or_(
                Registration.geslacht.is_(None),
                Registration.geslacht == '',
                Registration.geslacht == 'onbekend'
            )
        )
    if filter_datum_van:
        try:
            query = query.filter(Registration.datum >= date.fromisoformat(filter_datum_van))
        except ValueError:
            pass
    if filter_datum_tot:
        try:
            query = query.filter(Registration.datum <= date.fromisoformat(filter_datum_tot))
        except ValueError:
            pass

    # Sortering toepassen
    if sort_by == 'nummer':
        order_col = Registration.registratienummer.desc() if direction == 'desc' else Registration.registratienummer.asc()
        query = query.order_by(order_col)
    elif sort_by == 'client':
        order_col = Registration.client.desc() if direction == 'desc' else Registration.client.asc()
        query = query.order_by(order_col)
    elif sort_by == 'digidokter':
        query = query.outerjoin(Digidokter, Registration.digidokter_id == Digidokter.id)
        order_col = Digidokter.naam.desc() if direction == 'desc' else Digidokter.naam.asc()
        query = query.order_by(order_col)
    elif sort_by == 'leeftijd':
        from sqlalchemy.orm import aliased
        MappedAgeCategory = aliased(AgeCategory)
        query = query.outerjoin(AgeCategory, Registration.leeftijdscategorie_id == AgeCategory.id)\
                     .outerjoin(MappedAgeCategory, AgeCategory.mapped_to_id == MappedAgeCategory.id)
        effective_volgorde = db.func.coalesce(MappedAgeCategory.volgorde, AgeCategory.volgorde)
        effective_naam = db.func.coalesce(MappedAgeCategory.naam, AgeCategory.naam)
        if direction == 'desc':
            query = query.order_by(effective_volgorde.desc(), effective_naam.desc())
        else:
            query = query.order_by(effective_volgorde.asc(), effective_naam.asc())
    elif sort_by == 'toestel':
        from sqlalchemy.orm import aliased
        MappedDevice = aliased(Device)
        query = query.outerjoin(Device, Registration.toestel_id == Device.id)\
                     .outerjoin(MappedDevice, Device.mapped_to_id == MappedDevice.id)
        effective_naam = db.func.coalesce(MappedDevice.naam, Device.naam)
        order_col = effective_naam.desc() if direction == 'desc' else effective_naam.asc()
        query = query.order_by(order_col)
    elif sort_by == 'nieuw':
        order_col = Registration.nieuwe_klant.desc() if direction == 'desc' else Registration.nieuwe_klant.asc()
        query = query.order_by(order_col)
    else:  # sort_by == 'datum'
        if direction == 'asc':
            query = query.order_by(Registration.datum.asc(), Registration.id.asc())
        else:
            query = query.order_by(Registration.datum.desc(), Registration.id.desc())

    paginatie = query.paginate(page=pagina, per_page=PAGINA_GROOTTE, error_out=False)
    keuzes = _keuzelijsten()

    return render_template(
        'registrations/list.html',
        registraties=paginatie.items,
        paginatie=paginatie,
        zoek=zoek,
        filter_digidokter=filter_digidokter,
        filter_toestel=filter_toestel,
        filter_leeftijd=filter_leeftijd,
        filter_geslacht=filter_geslacht,
        filter_datum_van=filter_datum_van,
        filter_datum_tot=filter_datum_tot,
        digidokters=keuzes['digidokters'],
        toestellen=keuzes['toestellen'],
        leeftijdscategorieën=keuzes['leeftijdscategorieën'],
        sort_by=sort_by,
        direction=direction,
    )


@reg_bp.route('/registraties/nieuw', methods=['GET', 'POST'])
@login_required
@writer_required
def nieuw():
    from utils.tenant import get_huidige_organisatie_id
    org_id = get_huidige_organisatie_id()
    keuzes = _keuzelijsten()

    # Bepaal standaard digidokter op basis van de ingelogde gebruiker
    default_digidokter_id = None
    if current_user.is_authenticated:
        dd_match = Digidokter.query.filter_by(
            user_id=current_user.id,
            organisatie_id=org_id,
            actief=True
        ).first()
        if not dd_match:
            dd_match = Digidokter.query.filter(
                db.func.lower(Digidokter.naam) == db.func.lower(current_user.naam),
                Digidokter.organisatie_id == org_id,
                Digidokter.actief == True
            ).first()
        if dd_match:
            default_digidokter_id = dd_match.id

    if request.method == 'POST':
        datum_str = request.form.get('datum', str(date.today()))
        try:
            datum = date.fromisoformat(datum_str)
        except ValueError:
            flash('Ongeldige datum.', 'danger')
            return render_template('registrations/add.html', **keuzes, datum_vandaag=str(date.today()),
                                   default_digidokter_id=default_digidokter_id)

        client = request.form.get('client', '').strip()
        digidokter_id = request.form.get('digidokter_id', 0, type=int)
        nieuwe_klant = request.form.get('nieuwe_klant') == 'ja'
        herkomst_id = request.form.get('herkomst_id', 0, type=int) or None
        geslacht = request.form.get('geslacht', '').strip() or None
        onderwerp = request.form.get('onderwerp', '').strip()
        leeftijdscategorie_id = request.form.get('leeftijdscategorie_id', 0, type=int)
        toestel_id = request.form.get('toestel_id', 0, type=int)

        # Verplichte velden en cross-tenant validatie
        from utils.tenant import get_huidige_organisatie_id, set_organisatie_id_op_model
        org_id = get_huidige_organisatie_id()

        fouten = []
        if not client:
            fouten.append('Naam van de bezoeker is verplicht.')
        
        if not digidokter_id:
            fouten.append('Digidokter is verplicht.')
        else:
            dd = db.session.get(Digidokter, digidokter_id)
            if not dd or dd.organisatie_id != org_id:
                fouten.append('Ongeldige digidokter geselecteerd.')
                
        if geslacht and geslacht not in ('man', 'vrouw'):
            fouten.append('Ongeldig geslacht geselecteerd.')

        if herkomst_id:
            h = db.session.get(Herkomst, herkomst_id)
            if not h or h.organisatie_id != org_id:
                fouten.append('Ongeldige herkomst geselecteerd.')

        if not onderwerp:
            fouten.append('Onderwerp is verplicht.')
            
        if not leeftijdscategorie_id:
            fouten.append('Leeftijdscategorie is verplicht.')
        else:
            ac = db.session.get(AgeCategory, leeftijdscategorie_id)
            if not ac or ac.organisatie_id != org_id:
                fouten.append('Ongeldige leeftijdscategorie geselecteerd.')
                
        if not toestel_id:
            fouten.append('Toestel is verplicht.')
        else:
            dev = db.session.get(Device, toestel_id)
            if not dev or dev.organisatie_id != org_id:
                fouten.append('Ongeldig toestel geselecteerd.')

        if fouten:
            for f in fouten:
                flash(f, 'danger')
            return render_template('registrations/add.html', **keuzes, datum_vandaag=datum_str,
                                   form_data=request.form, default_digidokter_id=default_digidokter_id)

        reg = Registration(
            registratienummer=Registration.genereer_registratienummer(org_id, datum.year),
            datum=datum,
            client=client,
            digidokter_id=digidokter_id,
            nieuwe_klant=nieuwe_klant,
            herkomst_id=herkomst_id,
            geslacht=geslacht,
            onderwerp=onderwerp,
            leeftijdscategorie_id=leeftijdscategorie_id,
            toestel_id=toestel_id,
            aangemaakt_door_id=current_user.id,
        )
        set_organisatie_id_op_model(reg)
        db.session.add(reg)
        db.session.commit()

        # Start asynchrone AI-vraagclassificatie op de achtergrond
        try:
            from utils.ai_classifier import trigger_asynchrone_classificatie
            trigger_asynchrone_classificatie(reg.id)
        except Exception:
            pass

        flash(f'Registratie {reg.registratienummer} succesvol toegevoegd.', 'success')
        return redirect(url_for('reg.lijst'))

    return render_template('registrations/add.html', **keuzes, datum_vandaag=str(date.today()),
                           default_digidokter_id=default_digidokter_id)


@reg_bp.route('/registraties/<int:reg_id>')
@login_required
def bekijken(reg_id):
    from utils.tenant import get_huidige_organisatie_id
    reg = db.get_or_404(Registration, reg_id)
    if reg.organisatie_id != get_huidige_organisatie_id():
        from flask import abort
        abort(403)
    return render_template('registrations/view.html', reg=reg)


@reg_bp.route('/registraties/<int:reg_id>/wijzig', methods=['GET', 'POST'])
@login_required
@writer_required
def wijzigen(reg_id):
    from utils.tenant import get_huidige_organisatie_id
    org_id = get_huidige_organisatie_id()
    reg = db.get_or_404(Registration, reg_id)
    
    if reg.organisatie_id != org_id:
        from flask import abort
        abort(403)
        
    keuzes = _keuzelijsten()

    if request.method == 'POST':
        datum_str = request.form.get('datum', str(reg.datum))
        try:
            datum = date.fromisoformat(datum_str)
        except ValueError:
            flash('Ongeldige datum.', 'danger')
            return render_template('registrations/edit.html', reg=reg, **keuzes)

        client = request.form.get('client', '').strip()
        digidokter_id = request.form.get('digidokter_id', 0, type=int)
        nieuwe_klant = request.form.get('nieuwe_klant') == 'ja'
        herkomst_id = request.form.get('herkomst_id', 0, type=int) or None
        geslacht = request.form.get('geslacht', '').strip() or None
        onderwerp = request.form.get('onderwerp', '').strip()
        leeftijdscategorie_id = request.form.get('leeftijdscategorie_id', 0, type=int)
        toestel_id = request.form.get('toestel_id', 0, type=int)

        # Verplichte velden en cross-tenant validatie
        fouten = []
        if not client:
            fouten.append('Naam van de bezoeker is verplicht.')
        
        if not digidokter_id:
            fouten.append('Digidokter is verplicht.')
        else:
            dd = db.session.get(Digidokter, digidokter_id)
            if not dd or dd.organisatie_id != org_id:
                fouten.append('Ongeldige digidokter geselecteerd.')
                
        if geslacht and geslacht not in ('man', 'vrouw'):
            fouten.append('Ongeldig geslacht geselecteerd.')

        if herkomst_id:
            h = db.session.get(Herkomst, herkomst_id)
            if not h or h.organisatie_id != org_id:
                fouten.append('Ongeldige herkomst geselecteerd.')

        if not onderwerp:
            fouten.append('Onderwerp is verplicht.')
            
        if not leeftijdscategorie_id:
            fouten.append('Leeftijdscategorie is verplicht.')
        else:
            ac = db.session.get(AgeCategory, leeftijdscategorie_id)
            if not ac or ac.organisatie_id != org_id:
                fouten.append('Ongeldige leeftijdscategorie geselecteerd.')
                
        if not toestel_id:
            fouten.append('Toestel is verplicht.')
        else:
            dev = db.session.get(Device, toestel_id)
            if not dev or dev.organisatie_id != org_id:
                fouten.append('Ongeldig toestel geselecteerd.')

        if fouten:
            for f in fouten:
                flash(f, 'danger')
            return render_template('registrations/edit.html', reg=reg, **keuzes)

        oude_onderwerp = reg.onderwerp
        reg.datum = datum
        reg.client = client
        reg.digidokter_id = digidokter_id
        reg.nieuwe_klant = nieuwe_klant
        reg.herkomst_id = herkomst_id
        reg.geslacht = geslacht
        reg.onderwerp = onderwerp
        reg.leeftijdscategorie_id = leeftijdscategorie_id
        reg.toestel_id = toestel_id
        db.session.commit()

        # Indien onderwerp gewijzigd of nog niet geclassificeerd, heranalyseer asynchroon
        if onderwerp != oude_onderwerp or not reg.classification:
            try:
                from utils.ai_classifier import trigger_asynchrone_classificatie
                trigger_asynchrone_classificatie(reg.id)
            except Exception:
                pass

        flash(f'Registratie {reg.registratienummer} succesvol bijgewerkt.', 'success')
        return redirect(url_for('reg.bekijken', reg_id=reg.id))

    return render_template('registrations/edit.html', reg=reg, **keuzes)


@reg_bp.route('/registraties/<int:reg_id>/verwijder', methods=['POST'])
@login_required
@writer_required
def verwijderen(reg_id):
    from flask import abort
    from utils.tenant import get_huidige_organisatie_id
    org_id = get_huidige_organisatie_id()
    reg = db.get_or_404(Registration, reg_id)

    if reg.organisatie_id != org_id:
        abort(403)

    db.session.delete(reg)
    db.session.commit()
    
    # GDPR: Verwijder ook alle audit logs die gekoppeld zijn aan deze registratie
    try:
        from models.audit import AuditLog
        AuditLog.query.filter_by(tabel='registrations', record_id=reg_id).delete()
        db.session.commit()
    except Exception as e:
        # Mocht de audit log opschoning mislukken, loggen we het maar blokkeren we de redirects niet
        current_app.logger.error(f"Fout bij het opschonen van audit logs voor registratie {reg_id}: {str(e)}")

    flash(f'Registratie {reg.registratienummer} is succesvol verwijderd.', 'success')
    return redirect(url_for('reg.lijst'))
