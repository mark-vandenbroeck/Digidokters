"""Statistieken routes."""
from datetime import date
from flask import Blueprint, render_template, request
from flask_login import login_required
from sqlalchemy import func, extract
from extensions import db
from models.registration import Registration
from models.digidokter import Digidokter
from models.age_category import AgeCategory
from models.device import Device

stats_bp = Blueprint('stats', __name__)


def _weekelijkse_telling(jaar):
    """Aantal registraties per ISO-weeknummer voor het gegeven jaar.

    Registraties gebeuren enkel op zaterdag, dus 'per week' komt overeen met
    'per zaterdag'. Weken zonder registraties krijgen 0 (i.p.v. ontbreken),
    zodat trends en gemiste weken (feestdagen, vakantie, ...) zichtbaar
    blijven in een tijdlijngrafiek.

    Geeft (laatste_weeknummer, {weeknummer: aantal}) terug.
    """
    from utils.tenant import get_huidige_organisatie_id
    org_id = get_huidige_organisatie_id()
    datums = [r[0] for r in
              db.session.query(Registration.datum)
              .filter(Registration.organisatie_id == org_id, extract('year', Registration.datum) == jaar)
              .all()]
    tellingen = {}
    for d in datums:
        # Let op: een datum vlak bij een jaargrens kan tot het ISO-weeknummer
        # van het aangrenzende jaar behoren. Voor deze visualisatie (trends
        # zien) is dat kleine randgeval verwaarloosbaar.
        week = d.isocalendar()[1]
        tellingen[week] = tellingen.get(week, 0) + 1
    laatste_week = date(jaar, 12, 28).isocalendar()[1]
    return laatste_week, tellingen


@stats_bp.route('/statistieken')
@login_required
def overzicht():
    jaar = request.args.get('jaar', None, type=int)
    if not jaar:
        jaar = date.today().year

    from utils.tenant import get_huidige_organisatie_id
    org_id = get_huidige_organisatie_id()

    # Filter op jaar en organisatie
    def jaar_filter(q):
        return q.filter(Registration.organisatie_id == org_id, extract('year', Registration.datum) == jaar)

    # Totaal dit jaar
    totaal_jaar = jaar_filter(db.session.query(func.count(Registration.id))).scalar() or 0

    # Per maand
    per_maand_data = (
        jaar_filter(
            db.session.query(
                extract('month', Registration.datum).label('maand'),
                func.count(Registration.id).label('aantal')
            )
        )
        .group_by(extract('month', Registration.datum))
        .order_by(extract('month', Registration.datum))
        .all()
    )

    MAAND_NAMEN = ['', 'Januari', 'Februari', 'Maart', 'April', 'Mei', 'Juni',
                   'Juli', 'Augustus', 'September', 'Oktober', 'November', 'December']
    per_maand = [(MAAND_NAMEN[int(r.maand)], r.aantal) for r in per_maand_data]

    # Per digidokter
    per_digidokter = (
        jaar_filter(
            db.session.query(
                Digidokter.naam,
                func.count(Registration.id).label('aantal')
            ).join(Digidokter, Registration.digidokter_id == Digidokter.id)
        )
        .group_by(Digidokter.naam)
        .order_by(func.count(Registration.id).desc())
        .all()
    )

    # Per leeftijdscategorie
    per_leeftijd = (
        jaar_filter(
            db.session.query(
                AgeCategory.naam,
                func.count(Registration.id).label('aantal')
            ).join(AgeCategory, Registration.leeftijdscategorie_id == AgeCategory.id)
        )
        .group_by(AgeCategory.naam)
        .order_by(func.count(Registration.id).desc())
        .all()
    )

    # Per toestel
    per_toestel = (
        jaar_filter(
            db.session.query(
                Device.naam,
                func.count(Registration.id).label('aantal')
            ).join(Device, Registration.toestel_id == Device.id)
        )
        .group_by(Device.naam)
        .order_by(func.count(Registration.id).desc())
        .all()
    )

    # Nieuwe vs terugkerende klanten
    nieuwe_klanten = jaar_filter(
        db.session.query(func.count(Registration.id)).filter(Registration.nieuwe_klant == True)
    ).scalar() or 0

    # Per geslacht
    per_geslacht_raw = (
        jaar_filter(
            db.session.query(
                Registration.geslacht,
                func.count(Registration.id).label('aantal')
            )
        )
        .group_by(Registration.geslacht)
        .all()
    )
    per_geslacht = []
    for r in per_geslacht_raw:
        if r.geslacht == 'man':
            label = 'Man'
        elif r.geslacht == 'vrouw':
            label = 'Vrouw'
        else:
            label = 'Niet gespecificeerd'
        per_geslacht.append((label, r.aantal))
    per_geslacht = sorted(per_geslacht, key=lambda x: x[1], reverse=True)

    # Recente 10 dagen met meeste bezoeken
    per_dag = (
        jaar_filter(
            db.session.query(
                Registration.datum,
                func.count(Registration.id).label('aantal')
            )
        )
        .group_by(Registration.datum)
        .order_by(func.count(Registration.id).desc())
        .limit(10)
        .all()
    )

    # Beschikbare jaren voor de selector
    jaren = [r[0] for r in
             db.session.query(extract('year', Registration.datum).label('jaar'))
             .filter(Registration.organisatie_id == org_id)
             .group_by('jaar').order_by('jaar').all()
             if r[0] is not None]
    if not jaren:
        jaren = [date.today().year]

    # Tijdlijn per week: dit jaar vs vorig jaar, uitgelijnd op weeknummer
    laatste_week_huidig, tellingen_huidig = _weekelijkse_telling(jaar)
    laatste_week_vorig, tellingen_vorig = _weekelijkse_telling(jaar - 1)
    max_weken = max(laatste_week_huidig, laatste_week_vorig)
    week_labels = [f'W{w}' for w in range(1, max_weken + 1)]
    per_week = [tellingen_huidig.get(w, 0) if w <= laatste_week_huidig else None
                for w in range(1, max_weken + 1)]
    per_week_vorig_jaar = [tellingen_vorig.get(w, 0) if w <= laatste_week_vorig else None
                            for w in range(1, max_weken + 1)]

    # ---------------------------------------------------------
    # AGENDA & VRIJWILLIGERS STATISTIEKEN (Nieuwe Tab)
    # ---------------------------------------------------------
    from models.agenda import AgendaItem
    from models.location import Location
    from models.activity_type import ActivityType

    # Haal agenda-items op van dit jaar voor deze organisatie
    agenda_items = (
        AgendaItem.query
        .filter(AgendaItem.organisatie_id == org_id, extract('year', AgendaItem.datum) == jaar)
        .all()
    )

    totaal_sessies = len(agenda_items)
    
    # Berekening uren
    def calc_duration_hours(item):
        try:
            h1, m1 = map(int, item.uur_van.split(':'))
            h2, m2 = map(int, item.uur_tot.split(':'))
            t1 = h1 + m1 / 60.0
            t2 = h2 + m2 / 60.0
            return max(0.0, t2 - t1)
        except Exception:
            return 0.0

    totaal_vrijwilligersuren = 0.0
    actieve_vrijwilligers_set = set()
    
    hours_per_digidokter = {}
    sessions_per_digidokter = {}
    sessions_per_location = {}
    sessions_per_type = {}
    hours_per_month_dict = {m: 0.0 for m in range(1, 13)}

    for item in agenda_items:
        duration = calc_duration_hours(item)
        num_vols = len(item.digidokters)
        totaal_vrijwilligersuren += duration * num_vols
        
        # Maandelijkse uren
        m = item.datum.month
        hours_per_month_dict[m] = hours_per_month_dict.get(m, 0.0) + (duration * num_vols)
        
        # Locatie aggregatie
        loc_naam = item.locatie.naam if item.locatie else 'Onbekende locatie'
        sessions_per_location[loc_naam] = sessions_per_location.get(loc_naam, 0) + 1
        
        # Type aggregatie
        type_naam = item.type.naam if item.type else 'Onbekend type'
        sessions_per_type[type_naam] = sessions_per_type.get(type_naam, 0) + 1
        
        # Digidokters aggregatie
        for dd in item.digidokters:
            actieve_vrijwilligers_set.add(dd.id)
            hours_per_digidokter[dd.naam] = hours_per_digidokter.get(dd.naam, 0.0) + duration
            sessions_per_digidokter[dd.naam] = sessions_per_digidokter.get(dd.naam, 0) + 1

    totaal_actieve_vrijwilligers = len(actieve_vrijwilligers_set)
    
    # Sorteer inzet per digidokter op uren desc
    vrijwilligers_inzet = []
    for naam in sorted(sessions_per_digidokter.keys()):
        vrijwilligers_inzet.append({
            'naam': naam,
            'sessies': sessions_per_digidokter[naam],
            'uren': round(hours_per_digidokter[naam], 1)
        })
    vrijwilligers_inzet = sorted(vrijwilligers_inzet, key=lambda x: x['uren'], reverse=True)

    # Sorteer locaties en types op aantal sessies desc
    locatie_bezetting = sorted(sessions_per_location.items(), key=lambda x: x[1], reverse=True)
    type_bezetting = sorted(sessions_per_type.items(), key=lambda x: x[1], reverse=True)

    # Maandelijkse uren trend
    maand_labels = ['Jan', 'Feb', 'Mrt', 'Apr', 'Mei', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dec']
    vrijwilligersuren_per_maand = [round(hours_per_month_dict[m], 1) for m in range(1, 13)]

    # Druktest / ratio per dag
    reg_counts = (
        db.session.query(Registration.datum, func.count(Registration.id))
        .filter(Registration.organisatie_id == org_id, extract('year', Registration.datum) == jaar)
        .group_by(Registration.datum)
        .all()
    )
    reg_counts_dict = {r[0]: r[1] for r in reg_counts}

    sessions_ratio = []
    for item in agenda_items:
        vol_count = len(item.digidokters)
        visit_count = reg_counts_dict.get(item.datum, 0)
        ratio = round(visit_count / vol_count, 1) if vol_count > 0 else 0
        sessions_ratio.append({
            'datum': item.datum,
            'omschrijving': item.omschrijving or item.type.naam,
            'vrijwilligers': vol_count,
            'bezoeken': visit_count,
            'ratio': ratio
        })
    sessions_ratio = sorted(sessions_ratio, key=lambda x: x['datum'], reverse=True)[:10]

    return render_template(
        'stats/overview.html',
        jaar=jaar,
        jaren=jaren,
        totaal_jaar=totaal_jaar,
        per_maand=per_maand,
        per_digidokter=per_digidokter,
        per_leeftijd=per_leeftijd,
        per_toestel=per_toestel,
        per_geslacht=per_geslacht,
        nieuwe_klanten=nieuwe_klanten,
        terugkerende_klanten=totaal_jaar - nieuwe_klanten,
        per_dag=per_dag,
        week_labels=week_labels,
        per_week=per_week,
        per_week_vorig_jaar=per_week_vorig_jaar,
        vorig_jaar=jaar - 1,
        
        # Agenda & Vrijwilligers
        totaal_sessies=totaal_sessies,
        totaal_vrijwilligersuren=round(totaal_vrijwilligersuren, 1),
        totaal_actieve_vrijwilligers=totaal_actieve_vrijwilligers,
        vrijwilligers_inzet=vrijwilligers_inzet,
        locatie_bezetting=locatie_bezetting,
        type_bezetting=type_bezetting,
        maand_labels=maand_labels,
        vrijwilligersuren_per_maand=vrijwilligersuren_per_maand,
        sessions_ratio=sessions_ratio
    )