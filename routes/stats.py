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
from models.question_category import QuestionCategory
from models.question_classification import QuestionClassification

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
    jaar_param = request.args.get('jaar')
    if jaar_param == 'alle':
        jaar = 'alle'
    else:
        try:
            jaar = int(jaar_param) if jaar_param else date.today().year
        except (ValueError, TypeError):
            jaar = date.today().year

    actieve_tab = request.args.get('tab', 'visitors')
    if actieve_tab not in ('visitors', 'volunteers', 'questions'):
        actieve_tab = 'visitors'

    from utils.tenant import get_huidige_organisatie_id
    org_id = get_huidige_organisatie_id()

    # Filter op jaar en organisatie
    def jaar_filter(q):
        if jaar == 'alle':
            return q.filter(Registration.organisatie_id == org_id)
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
    from sqlalchemy.orm import aliased
    MappedAgeCategory = aliased(AgeCategory)
    eff_leeftijd_naam = func.coalesce(MappedAgeCategory.naam, AgeCategory.naam)
    per_leeftijd = (
        jaar_filter(
            db.session.query(
                eff_leeftijd_naam,
                func.count(Registration.id).label('aantal')
            ).join(AgeCategory, Registration.leeftijdscategorie_id == AgeCategory.id)
             .outerjoin(MappedAgeCategory, AgeCategory.mapped_to_id == MappedAgeCategory.id)
        )
        .group_by(eff_leeftijd_naam)
        .order_by(func.count(Registration.id).desc())
        .all()
    )

    # Per toestel
    MappedDevice = aliased(Device)
    eff_toestel_naam = func.coalesce(MappedDevice.naam, Device.naam)
    per_toestel = (
        jaar_filter(
            db.session.query(
                eff_toestel_naam,
                func.count(Registration.id).label('aantal')
            ).join(Device, Registration.toestel_id == Device.id)
             .outerjoin(MappedDevice, Device.mapped_to_id == MappedDevice.id)
        )
        .group_by(eff_toestel_naam)
        .order_by(func.count(Registration.id).desc())
        .all()
    )

    # Per herkomst
    from models.herkomst import Herkomst
    per_herkomst_raw = (
        jaar_filter(
            db.session.query(
                Herkomst.naam,
                func.count(Registration.id).label('aantal')
            ).outerjoin(Herkomst, Registration.herkomst_id == Herkomst.id)
        )
        .group_by(Herkomst.naam)
        .all()
    )
    per_herkomst = []
    for r in per_herkomst_raw:
        naam = r.naam if r.naam else 'Niet gespecificeerd'
        per_herkomst.append((naam, r.aantal))
    per_herkomst = sorted(per_herkomst, key=lambda x: x[1], reverse=True)

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

    # Tijdlijn per week (jaar-op-jaar) of per jaar (bij 'alle')
    if jaar != 'alle':
        vorig_jaar = jaar - 1
        laatste_week_huidig, tellingen_huidig = _weekelijkse_telling(jaar)
        laatste_week_vorig, tellingen_vorig = _weekelijkse_telling(jaar - 1)
        max_weken = max(laatste_week_huidig, laatste_week_vorig)
        week_labels = [f'W{w}' for w in range(1, max_weken + 1)]
        per_week = [tellingen_huidig.get(w, 0) if w <= laatste_week_huidig else None
                    for w in range(1, max_weken + 1)]
        per_week_vorig_jaar = [tellingen_vorig.get(w, 0) if w <= laatste_week_vorig else None
                                for w in range(1, max_weken + 1)]
        per_jaar_labels = []
        per_jaar_counts = []
    else:
        vorig_jaar = None
        week_labels = []
        per_week = []
        per_week_vorig_jaar = []
        jaren_tellingen = (
            db.session.query(
                extract('year', Registration.datum).label('jr'),
                func.count(Registration.id).label('aantal')
            )
            .filter(Registration.organisatie_id == org_id)
            .group_by('jr')
            .order_by('jr')
            .all()
        )
        per_jaar_labels = [str(int(r.jr)) for r in jaren_tellingen if r.jr is not None]
        per_jaar_counts = [r.aantal for r in jaren_tellingen if r.jr is not None]

    # ---------------------------------------------------------
    # AGENDA & VRIJWILLIGERS STATISTIEKEN (Nieuwe Tab)
    # ---------------------------------------------------------
    from models.agenda import AgendaItem
    from models.location import Location
    from models.activity_type import ActivityType
    from sqlalchemy.orm import joinedload, selectinload

    # Haal agenda-items op voor deze organisatie met eager loading
    agenda_query = AgendaItem.query.filter(AgendaItem.organisatie_id == org_id)
    if jaar != 'alle':
        agenda_query = agenda_query.filter(extract('year', AgendaItem.datum) == jaar)
    agenda_items = (
        agenda_query
        .options(
            joinedload(AgendaItem.type),
            joinedload(AgendaItem.locatie),
            selectinload(AgendaItem.digidokters)
        )
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
    reg_counts_query = (
        db.session.query(Registration.datum, func.count(Registration.id))
        .filter(Registration.organisatie_id == org_id)
    )
    if jaar != 'alle':
        reg_counts_query = reg_counts_query.filter(extract('year', Registration.datum) == jaar)
    reg_counts = reg_counts_query.group_by(Registration.datum).all()
    reg_counts_dict = {r[0]: r[1] for r in reg_counts}

    sessions_ratio = []
    today = date.today()
    for item in agenda_items:
        if item.datum <= today:
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

    # ---------------------------------------------------------
    # AI VRAGENANALYSE STATISTIEKEN (Tab 3)
    # ---------------------------------------------------------
    totaal_geanalyseerd = (
        jaar_filter(
            db.session.query(func.count(QuestionClassification.id))
            .select_from(Registration)
            .join(QuestionClassification, Registration.id == QuestionClassification.registration_id)
        ).scalar() or 0
    )
    
    dekkingsgraad = round((totaal_geanalyseerd / totaal_jaar * 100), 1) if totaal_jaar > 0 else 0
    
    gem_zekerheid_val = (
        jaar_filter(
            db.session.query(func.avg(QuestionClassification.zekerheid))
            .select_from(Registration)
            .join(QuestionClassification, Registration.id == QuestionClassification.registration_id)
        ).scalar()
    )
    gemiddelde_zekerheid = round(gem_zekerheid_val * 100, 1) if gem_zekerheid_val is not None else 0

    aantal_handmatig = (
        jaar_filter(
            db.session.query(func.count(QuestionClassification.id))
            .select_from(Registration)
            .join(QuestionClassification, Registration.id == QuestionClassification.registration_id)
            .filter(QuestionClassification.is_handmatig_aangepast == True)
        ).scalar() or 0
    )

    vragen_per_cat_raw = (
        jaar_filter(
            db.session.query(
                QuestionCategory.naam,
                func.count(QuestionClassification.id).label('aantal'),
                func.avg(QuestionClassification.zekerheid).label('gem_zekerheid')
            )
            .select_from(Registration)
            .join(QuestionClassification, Registration.id == QuestionClassification.registration_id)
            .join(QuestionCategory, QuestionClassification.category_id == QuestionCategory.id)
        )
        .group_by(QuestionCategory.naam)
        .order_by(func.count(QuestionClassification.id).desc())
        .all()
    )

    vragen_per_categorie = []
    for r in vragen_per_cat_raw:
        pct = round((r.aantal / totaal_geanalyseerd * 100), 1) if totaal_geanalyseerd > 0 else 0
        gem_z = round((r.gem_zekerheid or 0) * 100, 1)
        vragen_per_categorie.append({
            'naam': r.naam,
            'aantal': r.aantal,
            'percentage': pct,
            'gem_zekerheid': gem_z
        })

    cat_chart_labels = [c['naam'] for c in vragen_per_categorie]
    cat_chart_data = [c['aantal'] for c in vragen_per_categorie]

    # Top 5 categorieën verloop doorheen het jaar (12 maanden)
    top_5_cat_namen = [c['naam'] for c in vragen_per_categorie[:5]]
    trend_per_maand_cats = {}
    for cat_naam in top_5_cat_namen:
        maand_tellingen = dict(
            jaar_filter(
                db.session.query(
                    extract('month', Registration.datum).label('maand'),
                    func.count(QuestionClassification.id)
                )
                .select_from(Registration)
                .join(QuestionClassification, Registration.id == QuestionClassification.registration_id)
                .join(QuestionCategory, QuestionClassification.category_id == QuestionCategory.id)
                .filter(QuestionCategory.naam == cat_naam)
            )
            .group_by(extract('month', Registration.datum))
            .all()
        )
        trend_per_maand_cats[cat_naam] = [maand_tellingen.get(m, 0) for m in range(1, 13)]

    # Kruisanalyse per toestel
    MappedDeviceStats = aliased(Device)
    eff_tst_naam = func.coalesce(MappedDeviceStats.naam, Device.naam).label('toestel_naam')
    cat_toestel_raw = (
        jaar_filter(
            db.session.query(
                QuestionCategory.naam.label('cat_naam'),
                eff_tst_naam,
                func.count(Registration.id).label('aantal')
            )
            .select_from(Registration)
            .join(QuestionClassification, Registration.id == QuestionClassification.registration_id)
            .join(QuestionCategory, QuestionClassification.category_id == QuestionCategory.id)
            .join(Device, Registration.toestel_id == Device.id)
            .outerjoin(MappedDeviceStats, Device.mapped_to_id == MappedDeviceStats.id)
        )
        .group_by(QuestionCategory.naam, eff_tst_naam)
        .order_by(func.count(Registration.id).desc())
        .all()
    )
    cat_toestel_dict = {}
    for r in cat_toestel_raw:
        cat_toestel_dict.setdefault(r.cat_naam, []).append({'toestel': r.toestel_naam, 'aantal': r.aantal})

    # Kruisanalyse per leeftijd
    MappedAgeStats = aliased(AgeCategory)
    eff_lft_naam = func.coalesce(MappedAgeStats.naam, AgeCategory.naam).label('leeftijd_naam')
    cat_leeftijd_raw = (
        jaar_filter(
            db.session.query(
                QuestionCategory.naam.label('cat_naam'),
                eff_lft_naam,
                func.count(Registration.id).label('aantal')
            )
            .select_from(Registration)
            .join(QuestionClassification, Registration.id == QuestionClassification.registration_id)
            .join(QuestionCategory, QuestionClassification.category_id == QuestionCategory.id)
            .join(AgeCategory, Registration.leeftijdscategorie_id == AgeCategory.id)
            .outerjoin(MappedAgeStats, AgeCategory.mapped_to_id == MappedAgeStats.id)
        )
        .group_by(QuestionCategory.naam, eff_lft_naam)
        .order_by(func.count(Registration.id).desc())
        .all()
    )
    cat_leeftijd_dict = {}
    for r in cat_leeftijd_raw:
        cat_leeftijd_dict.setdefault(r.cat_naam, []).append({'leeftijd': r.leeftijd_naam, 'aantal': r.aantal})

    return render_template(
        'stats/overview.html',
        jaar=jaar,
        jaren=jaren,
        totaal_jaar=totaal_jaar,
        per_maand=per_maand,
        per_digidokter=per_digidokter,
        per_leeftijd=per_leeftijd,
        per_toestel=per_toestel,
        per_herkomst=per_herkomst,
        per_geslacht=per_geslacht,
        nieuwe_klanten=nieuwe_klanten,
        terugkerende_klanten=totaal_jaar - nieuwe_klanten,
        per_dag=per_dag,
        week_labels=week_labels,
        per_week=per_week,
        per_week_vorig_jaar=per_week_vorig_jaar,
        vorig_jaar=vorig_jaar,
        per_jaar_labels=per_jaar_labels,
        per_jaar_counts=per_jaar_counts,
        
        # Agenda & Vrijwilligers
        totaal_sessies=totaal_sessies,
        totaal_vrijwilligersuren=round(totaal_vrijwilligersuren, 1),
        totaal_actieve_vrijwilligers=totaal_actieve_vrijwilligers,
        vrijwilligers_inzet=vrijwilligers_inzet,
        locatie_bezetting=locatie_bezetting,
        type_bezetting=type_bezetting,
        maand_labels=maand_labels,
        vrijwilligersuren_per_maand=vrijwilligersuren_per_maand,
        sessions_ratio=sessions_ratio,

        # AI Vragenanalyse
        totaal_geanalyseerd=totaal_geanalyseerd,
        dekkingsgraad=dekkingsgraad,
        gemiddelde_zekerheid=gemiddelde_zekerheid,
        aantal_handmatig=aantal_handmatig,
        vragen_per_categorie=vragen_per_categorie,
        cat_chart_labels=cat_chart_labels,
        cat_chart_data=cat_chart_data,
        top_5_cat_namen=top_5_cat_namen,
        trend_per_maand_cats=trend_per_maand_cats,
        cat_toestel_dict=cat_toestel_dict,
        cat_leeftijd_dict=cat_leeftijd_dict,
        actieve_tab=actieve_tab
    )