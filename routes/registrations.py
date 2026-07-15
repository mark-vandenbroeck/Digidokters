"""Registraties routes: lijst, toevoegen, bekijken, wijzigen."""
from datetime import date
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from extensions import db
from models.registration import Registration
from models.digidokter import Digidokter
from models.age_category import AgeCategory
from models.device import Device

reg_bp = Blueprint('reg', __name__)

PAGINA_GROOTTE = 20


def _keuzelijsten():
    """Haal actieve keuzelijsten op voor formulieren."""
    from utils.tenant import filter_op_organisatie
    return {
        'digidokters': filter_op_organisatie(Digidokter.query.filter_by(actief=True), Digidokter).order_by(Digidokter.volgorde, Digidokter.naam).all(),
        'leeftijdscategorieën': filter_op_organisatie(AgeCategory.query.filter_by(actief=True), AgeCategory).order_by(AgeCategory.volgorde, AgeCategory.naam).all(),
        'toestellen': filter_op_organisatie(Device.query.filter_by(actief=True), Device).order_by(Device.volgorde, Device.naam).all(),
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
    filter_datum_van = request.args.get('datum_van', '')
    filter_datum_tot = request.args.get('datum_tot', '')

    from utils.tenant import filter_op_organisatie
    query = filter_op_organisatie(Registration.query, Registration).order_by(Registration.datum.desc(), Registration.id.desc())

    if zoek:
        query = query.filter(
            db.or_(
                Registration.client.ilike(f'%{zoek}%'),
                Registration.onderwerp.ilike(f'%{zoek}%'),
                Registration.herkomst.ilike(f'%{zoek}%'),
                Registration.registratienummer.ilike(f'%{zoek}%'),
            )
        )
    if filter_digidokter:
        query = query.filter(Registration.digidokter_id == filter_digidokter)
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

    paginatie = query.paginate(page=pagina, per_page=PAGINA_GROOTTE, error_out=False)
    digidokters = filter_op_organisatie(Digidokter.query.filter_by(actief=True), Digidokter).order_by(Digidokter.naam).all()

    return render_template(
        'registrations/list.html',
        registraties=paginatie.items,
        paginatie=paginatie,
        zoek=zoek,
        filter_digidokter=filter_digidokter,
        filter_datum_van=filter_datum_van,
        filter_datum_tot=filter_datum_tot,
        digidokters=digidokters,
    )


@reg_bp.route('/registraties/nieuw', methods=['GET', 'POST'])
@login_required
def nieuw():
    keuzes = _keuzelijsten()

    if request.method == 'POST':
        datum_str = request.form.get('datum', str(date.today()))
        try:
            datum = date.fromisoformat(datum_str)
        except ValueError:
            flash('Ongeldige datum.', 'danger')
            return render_template('registrations/add.html', **keuzes, datum_vandaag=str(date.today()))

        client = request.form.get('client', '').strip()
        digidokter_id = request.form.get('digidokter_id', 0, type=int)
        nieuwe_klant = request.form.get('nieuwe_klant') == 'ja'
        herkomst = request.form.get('herkomst', '').strip()
        geslacht = request.form.get('geslacht', '').strip() or None
        onderwerp = request.form.get('onderwerp', '').strip()
        leeftijdscategorie_id = request.form.get('leeftijdscategorie_id', 0, type=int)
        toestel_id = request.form.get('toestel_id', 0, type=int)

        # Verplichte velden en cross-tenant validatie
        from utils.tenant import get_huidige_organisatie_id, set_organisatie_id_op_model
        org_id = get_huidige_organisatie_id()

        fouten = []
        if not client:
            fouten.append('Cliëntnaam is verplicht.')
        
        if not digidokter_id:
            fouten.append('Digidokter is verplicht.')
        else:
            dd = db.session.get(Digidokter, digidokter_id)
            if not dd or dd.organisatie_id != org_id:
                fouten.append('Ongeldige digidokter geselecteerd.')
                
        if geslacht and geslacht not in ('man', 'vrouw'):
            fouten.append('Ongeldig geslacht geselecteerd.')

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
                                   form_data=request.form)

        reg = Registration(
            registratienummer=Registration.genereer_registratienummer(org_id, datum.year),
            datum=datum,
            client=client,
            digidokter_id=digidokter_id,
            nieuwe_klant=nieuwe_klant,
            herkomst=herkomst,
            geslacht=geslacht,
            onderwerp=onderwerp,
            leeftijdscategorie_id=leeftijdscategorie_id,
            toestel_id=toestel_id,
            aangemaakt_door_id=current_user.id,
        )
        set_organisatie_id_op_model(reg)
        db.session.add(reg)
        db.session.commit()
        flash(f'Registratie {reg.registratienummer} succesvol toegevoegd.', 'success')
        return redirect(url_for('reg.lijst'))

    return render_template('registrations/add.html', **keuzes, datum_vandaag=str(date.today()))


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
        herkomst = request.form.get('herkomst', '').strip()
        geslacht = request.form.get('geslacht', '').strip() or None
        onderwerp = request.form.get('onderwerp', '').strip()
        leeftijdscategorie_id = request.form.get('leeftijdscategorie_id', 0, type=int)
        toestel_id = request.form.get('toestel_id', 0, type=int)

        # Verplichte velden en cross-tenant validatie
        fouten = []
        if not client:
            fouten.append('Cliëntnaam is verplicht.')
        
        if not digidokter_id:
            fouten.append('Digidokter is verplicht.')
        else:
            dd = db.session.get(Digidokter, digidokter_id)
            if not dd or dd.organisatie_id != org_id:
                fouten.append('Ongeldige digidokter geselecteerd.')
                
        if geslacht and geslacht not in ('man', 'vrouw'):
            fouten.append('Ongeldig geslacht geselecteerd.')

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

        reg.datum = datum
        reg.client = client
        reg.digidokter_id = digidokter_id
        reg.nieuwe_klant = nieuwe_klant
        reg.herkomst = herkomst
        reg.geslacht = geslacht
        reg.onderwerp = onderwerp
        reg.leeftijdscategorie_id = leeftijdscategorie_id
        reg.toestel_id = toestel_id
        db.session.commit()
        flash(f'Registratie {reg.registratienummer} succesvol bijgewerkt.', 'success')
        return redirect(url_for('reg.bekijken', reg_id=reg.id))

    return render_template('registrations/edit.html', reg=reg, **keuzes)
