from datetime import date
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, session
from flask_login import login_required, current_user
from sqlalchemy.orm import joinedload
from extensions import db
from models.registration import Registration
from models.digidokter import Digidokter
from models.age_category import AgeCategory
from models.device import Device
from models.herkomst import Herkomst
from models.gender_identity import GenderIdentity
from models.location import Location
from utils.decorators import writer_required
from utils.helpers import safe_int, safe_date, safe_str
from utils.tenant import filter_op_organisatie

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
        'genderidentiteiten': filter_op_organisatie(GenderIdentity.query.filter_by(actief=True), GenderIdentity).order_by(GenderIdentity.volgorde, GenderIdentity.naam).all(),
        'consultatie_locaties': filter_op_organisatie(Location.query.filter_by(actief=True, gebruikt_voor_consultaties=True), Location).order_by(Location.volgorde, Location.naam).all(),
    }


@reg_bp.route('/')
@login_required
def index():
    return redirect(url_for('reg.lijst'))


@reg_bp.route('/registraties')
@login_required
def lijst():
    pagina = safe_int(request.args.get('pagina'), default=1) or 1
    zoek = safe_str(request.args.get('zoek'))
    filter_digidokter = safe_int(request.args.get('digidokter'), default=0) or 0
    filter_locatie = safe_int(request.args.get('locatie'), default=0) or 0
    filter_toestel = safe_int(request.args.get('toestel')) or safe_int(request.args.get('toesteltype'), default=0) or 0
    filter_leeftijd = safe_int(request.args.get('leeftijd')) or safe_int(request.args.get('leeftijdscategorie'), default=0) or 0
    filter_geslacht = safe_str(request.args.get('geslacht')).lower()
    filter_datum_van = safe_str(request.args.get('datum_van'))
    filter_datum_tot = safe_str(request.args.get('datum_tot'))
    sort_by = safe_str(request.args.get('sort_by'), default='datum') or 'datum'
    direction = safe_str(request.args.get('direction'), default='desc') or 'desc'

    from utils.tenant import filter_op_organisatie
    query = (
        filter_op_organisatie(Registration.query, Registration)
        .options(
            joinedload(Registration.digidokter),
            joinedload(Registration.leeftijdscategorie).joinedload(AgeCategory.mapped_to),
            joinedload(Registration.toestel).joinedload(Device.mapped_to),
            joinedload(Registration.herkomst),
            joinedload(Registration.locatie)
        )
    )

    if zoek:
        query = query.filter(
            db.or_(
                Registration.client.ilike(f'%{zoek}%'),
                Registration.onderwerp.ilike(f'%{zoek}%'),
                Registration.registratienummer.ilike(f'%{zoek}%'),
                Registration.herkomst.has(Herkomst.naam.ilike(f'%{zoek}%')),
                Registration.locatie.has(Location.naam.ilike(f'%{zoek}%')),
            )
        )
    if filter_digidokter:
        query = query.filter(Registration.digidokter_id == filter_digidokter)
    if filter_locatie:
        query = query.filter(Registration.locatie_id == filter_locatie)
    if filter_toestel:
        mapped_toestel_ids = [t.id for t in Device.query.filter_by(mapped_to_id=filter_toestel).all()]
        query = query.filter(Registration.toestel_id.in_([filter_toestel] + mapped_toestel_ids))
    if filter_leeftijd:
        mapped_leeftijd_ids = [c.id for c in AgeCategory.query.filter_by(mapped_to_id=filter_leeftijd).all()]
        query = query.filter(Registration.leeftijdscategorie_id.in_([filter_leeftijd] + mapped_leeftijd_ids))
    if filter_geslacht in ('onbekend', 'geen'):
        query = query.filter(
            db.or_(
                Registration.gender_identity_id.is_(None),
                Registration.gender_identity.has(db.func.lower(GenderIdentity.naam) == 'onbekend')
            )
        )
    elif filter_geslacht:
        if filter_geslacht.isdigit():
            query = query.filter(Registration.gender_identity_id == int(filter_geslacht))
        else:
            query = query.filter(
                Registration.gender_identity.has(db.func.lower(GenderIdentity.naam) == filter_geslacht.lower())
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
    elif sort_by == 'locatie':
        query = query.outerjoin(Location, Registration.locatie_id == Location.id)
        order_col = Location.naam.desc() if direction == 'desc' else Location.naam.asc()
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
        filter_locatie=filter_locatie,
        filter_toestel=filter_toestel,
        filter_leeftijd=filter_leeftijd,
        filter_geslacht=filter_geslacht,
        filter_datum_van=filter_datum_van,
        filter_datum_tot=filter_datum_tot,
        digidokters=keuzes['digidokters'],
        consultatie_locaties=keuzes['consultatie_locaties'],
        toestellen=keuzes['toestellen'],
        leeftijdscategorieën=keuzes['leeftijdscategorieën'],
        genderidentiteiten=keuzes['genderidentiteiten'],
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
                
        gender_identity_id = None
        if geslacht:
            geldige_genders = {g.naam.lower(): g for g in filter_op_organisatie(GenderIdentity.query, GenderIdentity).all()}
            if geslacht.isdigit() and int(geslacht) in [g.id for g in geldige_genders.values()]:
                gender_identity_id = int(geslacht)
            elif geslacht.lower() in geldige_genders:
                gender_identity_id = geldige_genders[geslacht.lower()].id
            else:
                fouten.append('Ongeldige genderidentiteit geselecteerd.')

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

        consultatie_locaties = keuzes['consultatie_locaties']
        locatie_id = None
        if len(consultatie_locaties) > 1:
            locatie_id = request.form.get('locatie_id', 0, type=int) or None
            if not locatie_id:
                fouten.append('Locatie is verplicht.')
            else:
                loc = db.session.get(Location, locatie_id)
                if not loc or loc.organisatie_id != org_id:
                    fouten.append('Ongeldige locatie geselecteerd.')
        elif len(consultatie_locaties) == 1:
            locatie_id = consultatie_locaties[0].id
        else:
            locatie_id = None

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
            gender_identity_id=gender_identity_id,
            onderwerp=onderwerp,
            leeftijdscategorie_id=leeftijdscategorie_id,
            toestel_id=toestel_id,
            locatie_id=locatie_id,
            aangemaakt_door_id=current_user.id,
            organisatie_id=org_id,
        )
        set_organisatie_id_op_model(reg)
        try:
            db.session.add(reg)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Fout bij toevoegen registratie: {e}")
            flash('Er is een fout opgetreden bij het opslaan van de registratie.', 'danger')
            return render_template('registrations/add.html', **keuzes, datum_vandaag=datum_str,
                                   form_data=request.form, default_digidokter_id=default_digidokter_id)

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


@reg_bp.route('/registraties/snel', methods=['GET', 'POST'])
@login_required
@writer_required
def snel():
    from utils.tenant import get_huidige_organisatie_id, set_organisatie_id_op_model, filter_op_organisatie
    org_id = get_huidige_organisatie_id()
    keuzes = _keuzelijsten()

    # Bereken default digidokter (eerst uit sessie, anders ingelogde gebruiker)
    sessie_digidokter_id = session.get('snelle_reg_digidokter_id')
    default_digidokter_id = None
    if sessie_digidokter_id:
        dd_chk = Digidokter.query.filter_by(id=sessie_digidokter_id, organisatie_id=org_id, actief=True).first()
        if dd_chk:
            default_digidokter_id = dd_chk.id

    if not default_digidokter_id and current_user.is_authenticated:
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

    # Bereken default locatie (eerst uit sessie, anders eerste consultatielocatie indien beschikbaar)
    sessie_locatie_id = session.get('snelle_reg_locatie_id')
    default_locatie_id = None
    if sessie_locatie_id:
        loc_chk = Location.query.filter_by(id=sessie_locatie_id, organisatie_id=org_id, actief=True).first()
        if loc_chk:
            default_locatie_id = loc_chk.id
    if not default_locatie_id and keuzes['consultatie_locaties']:
        default_locatie_id = keuzes['consultatie_locaties'][0].id

    # Datum
    sessie_datum = session.get('snelle_reg_datum', str(date.today()))

    # Aantal registraties vandaag voor deze organisatie
    vandaag_telling = filter_op_organisatie(Registration.query, Registration).filter(Registration.datum == date.today()).count()

    if request.method == 'POST':
        datum_str = request.form.get('datum', str(date.today()))
        try:
            datum = date.fromisoformat(datum_str)
        except ValueError:
            datum = date.today()
            datum_str = str(date.today())

        client = request.form.get('client', '').strip()
        digidokter_id = request.form.get('digidokter_id', 0, type=int)
        nieuwe_klant = request.form.get('nieuwe_klant') == 'ja'
        herkomst_id = request.form.get('herkomst_id', 0, type=int) or None
        geslacht = request.form.get('geslacht', '').strip() or None
        onderwerp = request.form.get('onderwerp', '').strip()
        leeftijdscategorie_id = request.form.get('leeftijdscategorie_id', 0, type=int)
        toestel_id = request.form.get('toestel_id', 0, type=int)
        locatie_id = request.form.get('locatie_id', 0, type=int) or None
        actie = request.form.get('actie', 'volgende')  # 'volgende' of 'overzicht'

        # Sla sessievoorkeuren op
        if digidokter_id:
            session['snelle_reg_digidokter_id'] = digidokter_id
        if locatie_id:
            session['snelle_reg_locatie_id'] = locatie_id
        session['snelle_reg_datum'] = datum_str

        fouten = []
        if not client:
            fouten.append('Naam of initialen van de bezoeker is verplicht.')
        if not digidokter_id:
            fouten.append('Digidokter is verplicht.')
        else:
            dd = db.session.get(Digidokter, digidokter_id)
            if not dd or dd.organisatie_id != org_id:
                fouten.append('Ongeldige digidokter geselecteerd.')

        gender_identity_id = None
        if geslacht:
            geldige_genders = {g.naam.lower(): g for g in filter_op_organisatie(GenderIdentity.query, GenderIdentity).all()}
            if geslacht.isdigit() and int(geslacht) in [g.id for g in geldige_genders.values()]:
                gender_identity_id = int(geslacht)
            elif geslacht.lower() in geldige_genders:
                gender_identity_id = geldige_genders[geslacht.lower()].id
            else:
                fouten.append('Ongeldige genderidentiteit geselecteerd.')

        if herkomst_id:
            h = db.session.get(Herkomst, herkomst_id)
            if not h or h.organisatie_id != org_id:
                fouten.append('Ongeldige herkomst geselecteerd.')

        if not onderwerp:
            fouten.append('Onderwerp/vraag is verplicht.')

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

        consultatie_locaties = keuzes['consultatie_locaties']
        if consultatie_locaties and len(consultatie_locaties) > 1:
            if not locatie_id:
                fouten.append('Locatie is verplicht.')
            else:
                loc = db.session.get(Location, locatie_id)
                if not loc or loc.organisatie_id != org_id:
                    fouten.append('Ongeldige locatie geselecteerd.')
        elif len(consultatie_locaties) == 1:
            locatie_id = consultatie_locaties[0].id
        else:
            locatie_id = None

        if fouten:
            for f in fouten:
                flash(f, 'danger')
            return render_template(
                'registrations/quick.html',
                **keuzes,
                datum_vandaag=datum_str,
                default_digidokter_id=digidokter_id or default_digidokter_id,
                default_locatie_id=locatie_id or default_locatie_id,
                vandaag_telling=vandaag_telling,
                form_data=request.form
            )

        reg = Registration(
            registratienummer=Registration.genereer_registratienummer(org_id, datum.year),
            datum=datum,
            client=client,
            digidokter_id=digidokter_id,
            nieuwe_klant=nieuwe_klant,
            herkomst_id=herkomst_id,
            gender_identity_id=gender_identity_id,
            onderwerp=onderwerp,
            leeftijdscategorie_id=leeftijdscategorie_id,
            toestel_id=toestel_id,
            locatie_id=locatie_id,
            aangemaakt_door_id=current_user.id,
            organisatie_id=org_id,
        )
        set_organisatie_id_op_model(reg)
        try:
            db.session.add(reg)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Fout bij toevoegen snelle registratie: {e}")
            flash('Er is een fout opgetreden bij het opslaan van de registratie.', 'danger')
            return render_template(
                'registrations/quick.html',
                **keuzes,
                datum_vandaag=datum_str,
                default_digidokter_id=digidokter_id or default_digidokter_id,
                default_locatie_id=locatie_id or default_locatie_id,
                vandaag_telling=vandaag_telling,
                form_data=request.form
            )

        # Start asynchrone AI-vraagclassificatie op de achtergrond
        try:
            from utils.ai_classifier import trigger_asynchrone_classificatie
            trigger_asynchrone_classificatie(reg.id)
        except Exception:
            pass

        flash(f'⚡ Registratie {reg.registratienummer} ({reg.client}) succesvol opgeslagen!', 'success')
        
        if actie == 'overzicht':
            return redirect(url_for('reg.lijst'))
        
        return redirect(url_for('reg.snel'))

    return render_template(
        'registrations/quick.html',
        **keuzes,
        datum_vandaag=sessie_datum,
        default_digidokter_id=default_digidokter_id,
        default_locatie_id=default_locatie_id,
        vandaag_telling=vandaag_telling
    )


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
                
        gender_identity_id = None
        if geslacht:
            geldige_genders = {g.naam.lower(): g for g in filter_op_organisatie(GenderIdentity.query, GenderIdentity).all()}
            if geslacht.isdigit() and int(geslacht) in [g.id for g in geldige_genders.values()]:
                gender_identity_id = int(geslacht)
            elif geslacht.lower() in geldige_genders:
                gender_identity_id = geldige_genders[geslacht.lower()].id
            else:
                fouten.append('Ongeldige genderidentiteit geselecteerd.')

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

        consultatie_locaties = keuzes['consultatie_locaties']
        locatie_id = reg.locatie_id
        if len(consultatie_locaties) > 1:
            locatie_id = request.form.get('locatie_id', 0, type=int) or None
            if not locatie_id:
                fouten.append('Locatie is verplicht.')
            else:
                loc = db.session.get(Location, locatie_id)
                if not loc or loc.organisatie_id != org_id:
                    fouten.append('Ongeldige locatie geselecteerd.')
        elif len(consultatie_locaties) == 1:
            if not reg.locatie_id:
                locatie_id = consultatie_locaties[0].id

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
        reg.gender_identity_id = gender_identity_id
        reg.onderwerp = onderwerp
        reg.leeftijdscategorie_id = leeftijdscategorie_id
        reg.toestel_id = toestel_id
        reg.locatie_id = locatie_id

        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Fout bij bijwerken registratie {reg.id}: {e}")
            flash('Er is een fout opgetreden bij het bijwerken van de registratie.', 'danger')
            return render_template('registrations/edit.html', reg=reg, **keuzes)

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

    reg_nummer = reg.registratienummer
    try:
        db.session.delete(reg)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Fout bij verwijderen registratie {reg_id}: {e}")
        flash('Er is een fout opgetreden bij het verwijderen van de registratie.', 'danger')
        return redirect(url_for('reg.lijst'))
    
    # GDPR: Verwijder ook alle audit logs die gekoppeld zijn aan deze registratie
    try:
        from models.audit import AuditLog
        AuditLog.query.filter_by(tabel='registrations', record_id=reg_id).delete()
        db.session.commit()
    except Exception as e:
        # Mocht de audit log opschoning mislukken, loggen we het maar blokkeren we de redirects niet
        current_app.logger.error(f"Fout bij het opschonen van audit logs voor registratie {reg_id}: {str(e)}")

    flash(f'Registratie {reg_nummer} is succesvol verwijderd.', 'success')
    return redirect(url_for('reg.lijst'))
