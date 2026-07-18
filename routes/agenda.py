from datetime import date, datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from extensions import db
from models.agenda import AgendaItem
from models.activity_type import ActivityType
from models.location import Location
from models.digidokter import Digidokter
from utils.decorators import writer_required
from utils.tenant import get_huidige_organisatie_id, set_organisatie_id_op_model, filter_op_organisatie

agenda_bp = Blueprint('agenda', __name__)

def _keuzelijsten():
    """Haal actieve keuzelijsten op voor het agenda-formulier."""
    return {
        'types': filter_op_organisatie(ActivityType.query.filter_by(actief=True), ActivityType).order_by(ActivityType.volgorde, ActivityType.naam).all(),
        'locaties': filter_op_organisatie(Location.query.filter_by(actief=True), Location).order_by(Location.volgorde, Location.naam).all(),
        'digidokters': filter_op_organisatie(Digidokter.query.filter_by(actief=True), Digidokter).order_by(Digidokter.volgorde, Digidokter.naam).all(),
    }

@agenda_bp.route('/agenda')
@login_required
def lijst():
    org_id = get_huidige_organisatie_id()
    # Haal agenda-items op gesorteerd op datum en uur_van
    items = filter_op_organisatie(AgendaItem.query, AgendaItem).order_by(AgendaItem.datum.desc(), AgendaItem.uur_van.desc()).all()
    
    # We checken de rol van de actieve gebruiker om te bepalen of hij acties mag doen (nieuw/wijzig/verwijder)
    kan_schrijven = True
    if current_user.rol != 'platformbeheerder':
        uo = next((x for x in current_user.user_organisaties if x.organisatie_id == org_id and x.actief and x.organisatie.actief), None)
        if not uo or uo.rol == 'lezer':
            kan_schrijven = False

    return render_template('agenda/lijst.html', items=items, kan_schrijven=kan_schrijven)

@agenda_bp.route('/agenda/nieuw', methods=['GET', 'POST'])
@login_required
@writer_required
def nieuw():
    keuzes = _keuzelijsten()
    org_id = get_huidige_organisatie_id()

    if request.method == 'POST':
        datum_str = request.form.get('datum', '').strip()
        uur_van = request.form.get('uur_van', '').strip()
        uur_tot = request.form.get('uur_tot', '').strip()
        type_id = request.form.get('type_id', 0, type=int)
        locatie_id = request.form.get('locatie_id', 0, type=int)
        omschrijving = request.form.get('omschrijving', '').strip()
        digidokter_ids = request.form.getlist('digidokter_ids', type=int)

        fouten = []
        
        # Validatie datum
        datum = None
        if not datum_str:
            fouten.append('Datum is verplicht.')
        else:
            try:
                datum = date.fromisoformat(datum_str)
            except ValueError:
                fouten.append('Ongeldige datum.')

        # Validatie uren
        if not uur_van or not uur_tot:
            fouten.append('Uur van en tot zijn verplicht.')
        else:
            # Check HH:MM format
            import re
            time_pattern = re.compile(r'^([01]\d|2[0-3]):[0-5]\d$')
            if not time_pattern.match(uur_van) or not time_pattern.match(uur_tot):
                fouten.append('Tijdstip moet in HH:MM formaat zijn.')
            elif uur_van > uur_tot:
                fouten.append('Begintijd mag niet na eindtijd liggen.')

        # Validatie type en locatie
        if not type_id:
            fouten.append('Type activiteit is verplicht.')
        else:
            t = db.session.get(ActivityType, type_id)
            if not t or t.organisatie_id != org_id:
                fouten.append('Ongeldig type activiteit geselecteerd.')

        if not locatie_id:
            fouten.append('Locatie is verplicht.')
        else:
            l = db.session.get(Location, locatie_id)
            if not l or l.organisatie_id != org_id:
                fouten.append('Ongeldige locatie geselecteerd.')

        # Validatie digidokters
        selected_digidokters = []
        for d_id in digidokter_ids:
            d = db.session.get(Digidokter, d_id)
            if d and d.organisatie_id == org_id:
                selected_digidokters.append(d)
            else:
                fouten.append(f'Ongeldige digidokter geselecteerd (ID: {d_id}).')

        is_terugkerend = request.form.get('is_terugkerend') == 'on'
        interval = request.form.get('interval') if is_terugkerend else None
        einddatum_str = request.form.get('einddatum', '').strip() if is_terugkerend else ''

        einddatum = None
        if is_terugkerend:
            if interval not in ['dagelijks', 'wekelijks', 'maandelijks']:
                fouten.append('Selecteer een geldig herhalingsinterval.')
            if not einddatum_str:
                fouten.append('Einddatum is verplicht bij een terugkerende activiteit.')
            else:
                try:
                    einddatum = date.fromisoformat(einddatum_str)
                    if datum and einddatum < datum:
                        fouten.append('Einddatum mag niet vóór de begindatum liggen.')
                except ValueError:
                    fouten.append('Ongeldige einddatum.')

        if fouten:
            for f in fouten:
                flash(f, 'danger')
            return render_template('agenda/item_form.html', actie='Toevoegen', item=None, **keuzes, form_data=request.form)

        import uuid
        from datetime import timedelta

        reeks_id = str(uuid.uuid4()) if is_terugkerend else None
        current_date = datum
        items_to_save = [current_date]

        def add_month(d):
            import calendar
            month = d.month
            year = d.year
            month += 1
            if month > 12:
                month = 1
                year += 1
            day = min(d.day, calendar.monthrange(year, month)[1])
            return date(year, month, day)

        if is_terugkerend and interval and einddatum:
            while True:
                if interval == 'dagelijks':
                    current_date += timedelta(days=1)
                elif interval == 'wekelijks':
                    current_date += timedelta(weeks=1)
                elif interval == 'maandelijks':
                    current_date = add_month(current_date)
                
                if current_date > einddatum:
                    break
                items_to_save.append(current_date)
                if len(items_to_save) >= 100:
                    break

        for d in items_to_save:
            item = AgendaItem(
                datum=d,
                uur_van=uur_van,
                uur_tot=uur_tot,
                type_id=type_id,
                locatie_id=locatie_id,
                omschrijving=omschrijving,
                is_terugkerend=is_terugkerend,
                interval=interval,
                einddatum=einddatum,
                reeks_id=reeks_id
            )
            set_organisatie_id_op_model(item)
            item.digidokters = selected_digidokters
            db.session.add(item)
            
        db.session.commit()
        if is_terugkerend:
            flash(f'{len(items_to_save)} agenda-items succesvol toegevoegd aan de reeks.', 'success')
        else:
            flash('Agenda-item succesvol toegevoegd.', 'success')
        return redirect(url_for('agenda.lijst'))

    return render_template('agenda/item_form.html', actie='Toevoegen', item=None, **keuzes)

@agenda_bp.route('/agenda/<int:item_id>/wijzig', methods=['GET', 'POST'])
@login_required
@writer_required
def wijzigen(item_id):
    org_id = get_huidige_organisatie_id()
    item = db.get_or_404(AgendaItem, item_id)

    if item.organisatie_id != org_id:
        abort(403)

    keuzes = _keuzelijsten()

    if request.method == 'POST':
        datum_str = request.form.get('datum', '').strip()
        uur_van = request.form.get('uur_van', '').strip()
        uur_tot = request.form.get('uur_tot', '').strip()
        type_id = request.form.get('type_id', 0, type=int)
        locatie_id = request.form.get('locatie_id', 0, type=int)
        omschrijving = request.form.get('omschrijving', '').strip()
        digidokter_ids = request.form.getlist('digidokter_ids', type=int)

        fouten = []
        
        # Validatie datum
        datum = None
        if not datum_str:
            fouten.append('Datum is verplicht.')
        else:
            try:
                datum = date.fromisoformat(datum_str)
            except ValueError:
                fouten.append('Ongeldige datum.')

        # Validatie uren
        if not uur_van or not uur_tot:
            fouten.append('Uur van en tot zijn verplicht.')
        else:
            import re
            time_pattern = re.compile(r'^([01]\d|2[0-3]):[0-5]\d$')
            if not time_pattern.match(uur_van) or not time_pattern.match(uur_tot):
                fouten.append('Tijdstip moet in HH:MM formaat zijn.')
            elif uur_van > uur_tot:
                fouten.append('Begintijd mag niet na eindtijd liggen.')

        # Validatie type en locatie
        if not type_id:
            fouten.append('Type activiteit is verplicht.')
        else:
            t = db.session.get(ActivityType, type_id)
            if not t or t.organisatie_id != org_id:
                fouten.append('Ongeldig type activiteit geselecteerd.')

        if not locatie_id:
            fouten.append('Locatie is verplicht.')
        else:
            l = db.session.get(Location, locatie_id)
            if not l or l.organisatie_id != org_id:
                fouten.append('Ongeldige locatie geselecteerd.')

        # Validatie digidokters
        selected_digidokters = []
        for d_id in digidokter_ids:
            d = db.session.get(Digidokter, d_id)
            if d and d.organisatie_id == org_id:
                selected_digidokters.append(d)
            else:
                fouten.append(f'Ongeldige digidokter geselecteerd (ID: {d_id}).')

        if fouten:
            for f in fouten:
                flash(f, 'danger')
            return render_template('agenda/item_form.html', actie='Wijzigen', item=item, **keuzes, form_data=request.form)

        item.datum = datum
        item.uur_van = uur_van
        item.uur_tot = uur_tot
        item.type_id = type_id
        item.locatie_id = locatie_id
        item.omschrijving = omschrijving
        item.digidokters = selected_digidokters
        
        db.session.commit()
        flash('Agenda-item succesvol bijgewerkt.', 'success')
        return redirect(url_for('agenda.lijst'))

    return render_template('agenda/item_form.html', actie='Wijzigen', item=item, **keuzes)

@agenda_bp.route('/agenda/<int:item_id>/verwijder', methods=['POST'])
@login_required
@writer_required
def verwijderen(item_id):
    org_id = get_huidige_organisatie_id()
    item = db.get_or_404(AgendaItem, item_id)

    if item.organisatie_id != org_id:
        abort(403)

    verwijder_reeks = request.form.get('verwijder_reeks') == 'true'

    if verwijder_reeks and item.reeks_id:
        # Verwijder de hele reeks
        AgendaItem.query.filter_by(organisatie_id=org_id, reeks_id=item.reeks_id).delete()
        flash('De gehele reeks van activiteiten is succesvol verwijderd.', 'success')
    else:
        db.session.delete(item)
        flash('Agenda-item succesvol verwijderd.', 'success')

    db.session.commit()
    return redirect(url_for('agenda.lijst'))
