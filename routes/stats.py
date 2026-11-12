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
from utils.helpers import safe_int, safe_str

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
    jaar_param = safe_str(request.args.get('jaar'))
    if jaar_param == 'alle':
        jaar = 'alle'
    else:
        jaar = safe_int(jaar_param, default=date.today().year) or date.today().year

    actieve_tab = safe_str(request.args.get('tab'), default='visitors') or 'visitors'
    if actieve_tab not in ('visitors', 'volunteers', 'questions', 'activities'):
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
    per_digidokter_raw = (
        jaar_filter(
            db.session.query(
                Digidokter.naam,
                func.count(Registration.id).label('aantal'),
                Digidokter.volgorde
            ).join(Digidokter, Registration.digidokter_id == Digidokter.id)
        )
        .group_by(Digidokter.naam, Digidokter.volgorde)
        .order_by(Digidokter.volgorde.asc(), Digidokter.naam.asc())
        .all()
    )
    per_digidokter = [(r[0], r[1]) for r in per_digidokter_raw]

    # Per leeftijdscategorie
    from sqlalchemy.orm import aliased
    MappedAgeCategory = aliased(AgeCategory)
    eff_leeftijd_naam = func.coalesce(MappedAgeCategory.naam, AgeCategory.naam)
    eff_leeftijd_volgorde = func.min(func.coalesce(MappedAgeCategory.volgorde, AgeCategory.volgorde))
    per_leeftijd_raw = (
        jaar_filter(
            db.session.query(
                eff_leeftijd_naam,
                func.count(Registration.id).label('aantal'),
                eff_leeftijd_volgorde.label('volgorde')
            ).join(AgeCategory, Registration.leeftijdscategorie_id == AgeCategory.id)
             .outerjoin(MappedAgeCategory, AgeCategory.mapped_to_id == MappedAgeCategory.id)
        )
        .group_by(eff_leeftijd_naam)
        .order_by(eff_leeftijd_volgorde.asc(), eff_leeftijd_naam.asc())
        .all()
    )
    per_leeftijd = [(r[0], r[1]) for r in per_leeftijd_raw]

    # Per toestel
    MappedDevice = aliased(Device)
    eff_toestel_naam = func.coalesce(MappedDevice.naam, Device.naam)
    eff_toestel_volgorde = func.min(func.coalesce(MappedDevice.volgorde, Device.volgorde))
    per_toestel_raw = (
        jaar_filter(
            db.session.query(
                eff_toestel_naam,
                func.count(Registration.id).label('aantal'),
                eff_toestel_volgorde.label('volgorde')
            ).join(Device, Registration.toestel_id == Device.id)
             .outerjoin(MappedDevice, Device.mapped_to_id == MappedDevice.id)
        )
        .group_by(eff_toestel_naam)
        .order_by(eff_toestel_volgorde.asc(), eff_toestel_naam.asc())
        .all()
    )
    per_toestel = [(r[0], r[1]) for r in per_toestel_raw]

    # Per herkomst
    from models.herkomst import Herkomst
    eff_herkomst_naam = func.coalesce(Herkomst.naam, 'Niet gespecificeerd')
    eff_herkomst_volgorde = func.min(func.coalesce(Herkomst.volgorde, 999999))
    per_herkomst_raw = (
        jaar_filter(
            db.session.query(
                eff_herkomst_naam,
                func.count(Registration.id).label('aantal'),
                eff_herkomst_volgorde.label('volgorde')
            ).outerjoin(Herkomst, Registration.herkomst_id == Herkomst.id)
        )
        .group_by(eff_herkomst_naam)
        .order_by(eff_herkomst_volgorde.asc(), eff_herkomst_naam.asc())
        .all()
    )
    per_herkomst = [(r[0], r[1]) for r in per_herkomst_raw]

    # Per consultatielocatie
    from models.location import Location
    org_consultatie_locs = (
        Location.query
        .filter_by(organisatie_id=org_id, gebruikt_voor_consultaties=True)
        .order_by(Location.volgorde.asc(), Location.naam.asc())
        .all()
    )
    heeft_consultatie_locaties = len(org_consultatie_locs) > 0

    loc_counts_raw = (
        jaar_filter(
            db.session.query(
                Registration.locatie_id,
                func.count(Registration.id).label('aantal')
            )
        )
        .group_by(Registration.locatie_id)
        .all()
    )
    loc_counts = {r[0]: r[1] for r in loc_counts_raw}

    per_locatie = []
    seen_loc_ids = set()

    for loc in org_consultatie_locs:
        per_locatie.append((loc.naam, loc_counts.get(loc.id, 0)))
        seen_loc_ids.add(loc.id)

    # Eventuele overige locaties uit historische registraties
    overige_loc_ids = [lid for lid in loc_counts if lid is not None and lid not in seen_loc_ids]
    if overige_loc_ids:
        overige_locs = Location.query.filter(Location.id.in_(overige_loc_ids)).order_by(Location.volgorde.asc(), Location.naam.asc()).all()
        for loc in overige_locs:
            per_locatie.append((loc.naam, loc_counts.get(loc.id, 0)))
            seen_loc_ids.add(loc.id)

    # Registraties zonder gekoppelde locatie
    zonder_locatie_aantal = loc_counts.get(None, 0)
    if zonder_locatie_aantal > 0:
        per_locatie.append(('Niet gespecificeerd', zonder_locatie_aantal))

    # Nieuwe vs terugkerende klanten
    nieuwe_klanten = jaar_filter(
        db.session.query(func.count(Registration.id)).filter(Registration.nieuwe_klant == True)
    ).scalar() or 0

    # Per geslacht / gender
    from models.gender_identity import GenderIdentity
    gender_identities = (
        GenderIdentity.query
        .filter_by(organisatie_id=org_id)
        .order_by(GenderIdentity.volgorde.asc(), GenderIdentity.naam.asc())
        .all()
    )
    gender_counts_raw = (
        jaar_filter(
            db.session.query(
                Registration.gender_identity_id,
                func.count(Registration.id).label('aantal')
            )
        )
        .group_by(Registration.gender_identity_id)
        .all()
    )
    gender_counts = {r[0]: r[1] for r in gender_counts_raw}

    per_geslacht = []
    seen_gender_ids = set()

    for g in gender_identities:
        per_geslacht.append((g.naam, gender_counts.get(g.id, 0)))
        seen_gender_ids.add(g.id)

    overige_gender_ids = [gid for gid in gender_counts if gid is not None and gid not in seen_gender_ids]
    if overige_gender_ids:
        overige_genders = GenderIdentity.query.filter(GenderIdentity.id.in_(overige_gender_ids)).order_by(GenderIdentity.volgorde.asc(), GenderIdentity.naam.asc()).all()
        for g in overige_genders:
            per_geslacht.append((g.naam, gender_counts.get(g.id, 0)))
            seen_gender_ids.add(g.id)

    zonder_gender_aantal = gender_counts.get(None, 0)
    if zonder_gender_aantal > 0:
        per_geslacht.append(('Niet gespecificeerd', zonder_gender_aantal))

    per_geslacht = sorted(per_geslacht, key=lambda x: x[1], reverse=True)

    # Per resultaat (Afloop / Resultaat van het bezoek)
    from models.resultaat import Resultaat
    org_resultaten = (
        Resultaat.query
        .filter_by(organisatie_id=org_id)
        .order_by(Resultaat.volgorde.asc(), Resultaat.omschrijving.asc())
        .all()
    )
    heeft_resultaten = len(org_resultaten) > 0

    resultaat_counts_raw = (
        jaar_filter(
            db.session.query(
                Registration.resultaat_id,
                func.count(Registration.id).label('aantal')
            )
        )
        .group_by(Registration.resultaat_id)
        .all()
    )
    resultaat_counts = {r[0]: r[1] for r in resultaat_counts_raw}

    per_resultaat = []
    seen_resultaat_ids = set()

    for res in org_resultaten:
        per_resultaat.append((res.omschrijving, resultaat_counts.get(res.id, 0)))
        seen_resultaat_ids.add(res.id)

    overige_res_ids = [rid for rid in resultaat_counts if rid is not None and rid not in seen_resultaat_ids]
    if overige_res_ids:
        overige_res = Resultaat.query.filter(Resultaat.id.in_(overige_res_ids)).order_by(Resultaat.volgorde.asc(), Resultaat.omschrijving.asc()).all()
        for res in overige_res:
            per_resultaat.append((res.omschrijving, resultaat_counts.get(res.id, 0)))
            seen_resultaat_ids.add(res.id)

    totaal_resultaten = sum(r[1] for r in per_resultaat)

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

    # Beschikbare jaren voor de selector (gecombineerd uit registraties en agenda-items)
    from models.agenda import AgendaItem
    reg_jaren = [r[0] for r in
                 db.session.query(extract('year', Registration.datum).label('jaar'))
                 .filter(Registration.organisatie_id == org_id)
                 .group_by('jaar').all()
                 if r[0] is not None]
    agenda_jaren = [r[0] for r in
                    db.session.query(extract('year', AgendaItem.datum).label('jaar'))
                    .filter(AgendaItem.organisatie_id == org_id)
                    .group_by('jaar').all()
                    if r[0] is not None]
    jaren = sorted(list(set([int(y) for y in (reg_jaren + agenda_jaren)] + [date.today().year])))
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

    # Sorteer locaties en types op stamgegevens volgorde
    locatie_order = {
        loc.naam: loc.volgorde 
        for loc in Location.query.filter_by(organisatie_id=org_id).all()
    }
    type_order = {
        t.naam: t.volgorde 
        for t in ActivityType.query.filter_by(organisatie_id=org_id).all()
    }
    locatie_bezetting = sorted(sessions_per_location.items(), key=lambda x: (locatie_order.get(x[0], 999999), x[0]))
    type_bezetting = sorted(sessions_per_type.items(), key=lambda x: (type_order.get(x[0], 999999), x[0]))
    max_loc_sessions = max([s[1] for s in locatie_bezetting], default=1)
    max_type_sessions = max([s[1] for s in type_bezetting], default=1)

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

    # ---------------------------------------------------------
    # TAB 4: ACTIVITEITEN & DEELNEMERS STATISTIEKEN
    # ---------------------------------------------------------
    from models.deelnemer import Deelnemer

    act_query = (
        AgendaItem.query
        .join(ActivityType, AgendaItem.type_id == ActivityType.id)
        .filter(
            AgendaItem.organisatie_id == org_id,
            ActivityType.registreer_deelnemers == True
        )
    )
    if jaar != 'alle':
        act_query = act_query.filter(extract('year', AgendaItem.datum) == jaar)

    act_items = (
        act_query
        .options(
            joinedload(AgendaItem.type),
            joinedload(AgendaItem.locatie),
            selectinload(AgendaItem.digidokters),
            selectinload(AgendaItem.deelnemers).joinedload(Deelnemer.leeftijdscategorie),
            selectinload(AgendaItem.deelnemers).joinedload(Deelnemer.toestel)
        )
        .order_by(AgendaItem.datum.desc(), AgendaItem.uur_van.desc())
        .all()
    )

    dn_totaal_sessies = len(act_items)
    dn_totaal_inschrijvingen = sum(len(item.deelnemers) for item in act_items)

    unieke_deelnemers_dict = {}
    deelnemer_frequenties = {}
    for item in act_items:
        for dn in item.deelnemers:
            unieke_deelnemers_dict[dn.id] = dn
            deelnemer_frequenties[dn.id] = deelnemer_frequenties.get(dn.id, 0) + 1

    dn_totaal_unieke_deelnemers = len(unieke_deelnemers_dict)
    dn_gem_deelnemers_per_sessie = round(dn_totaal_inschrijvingen / dn_totaal_sessies, 1) if dn_totaal_sessies > 0 else 0

    # Capaciteit en bezettingsgraad
    sessies_met_max = [item for item in act_items if item.max_deelnemers is not None and item.max_deelnemers > 0]
    totaal_aangeboden_plaatsen = sum(item.max_deelnemers for item in sessies_met_max)
    totaal_ingenomen_plaatsen = sum(len(item.deelnemers) for item in sessies_met_max)
    dn_bezettingsgraad = round((totaal_ingenomen_plaatsen / totaal_aangeboden_plaatsen * 100), 1) if totaal_aangeboden_plaatsen > 0 else None
    dn_volzette_sessies = sum(1 for item in sessies_met_max if len(item.deelnemers) >= item.max_deelnemers)
    dn_volzette_percentage = round((dn_volzette_sessies / len(sessies_met_max) * 100), 1) if sessies_met_max else None

    # Demografie unieke deelnemers
    postcode_counts = {}
    leeftijd_counts = {}
    toestel_counts = {}
    for dn in unieke_deelnemers_dict.values():
        pc = (dn.postcode or '').strip() or 'Niet opgegeven'
        postcode_counts[pc] = postcode_counts.get(pc, 0) + 1

        lc = dn.effectieve_leeftijdscategorie or 'Niet gespecificeerd'
        leeftijd_counts[lc] = leeftijd_counts.get(lc, 0) + 1

        t = dn.effectief_toestel or 'Geen / Niet gespecificeerd'
        toestel_counts[t] = toestel_counts.get(t, 0) + 1

    dn_per_postcode = sorted(postcode_counts.items(), key=lambda x: (x[0] == 'Niet opgegeven', -x[1], x[0]))
    dn_per_leeftijd = sorted(leeftijd_counts.items(), key=lambda x: (x[0] == 'Niet gespecificeerd', -x[1], x[0]))
    dn_per_toestel = sorted(toestel_counts.items(), key=lambda x: (x[0] == 'Geen / Niet gespecificeerd', -x[1], x[0]))

    dn_leeftijd_chart_labels = [k for k, v in dn_per_leeftijd]
    dn_leeftijd_chart_data = [v for k, v in dn_per_leeftijd]

    dn_toestel_chart_labels = [k for k, v in dn_per_toestel]
    dn_toestel_chart_data = [v for k, v in dn_per_toestel]

    # Per activiteitstype
    type_stats = {}
    for item in act_items:
        t_id = item.type_id
        if t_id not in type_stats:
            type_stats[t_id] = {
                'naam': item.type.naam if item.type else 'Onbekend',
                'kleur': getattr(item.type, 'kleur', 'primary'),
                'sessies': 0,
                'deelnemers': 0,
                'max_plaatsen': 0,
                'ingenomen_met_max': 0,
                'volzet': 0
            }
        type_stats[t_id]['sessies'] += 1
        dn_count = len(item.deelnemers)
        type_stats[t_id]['deelnemers'] += dn_count
        if item.max_deelnemers:
            type_stats[t_id]['max_plaatsen'] += item.max_deelnemers
            type_stats[t_id]['ingenomen_met_max'] += dn_count
            if dn_count >= item.max_deelnemers:
                type_stats[t_id]['volzet'] += 1

    for s in type_stats.values():
        s['gem_deelnemers'] = round(s['deelnemers'] / s['sessies'], 1) if s['sessies'] > 0 else 0
        s['bezettingsgraad'] = round(s['ingenomen_met_max'] / s['max_plaatsen'] * 100, 1) if s['max_plaatsen'] > 0 else None

    dn_per_type = sorted(type_stats.values(), key=lambda x: x['deelnemers'], reverse=True)

    # Per locatie
    loc_stats = {}
    for item in act_items:
        loc_naam = item.locatie.naam if item.locatie else 'Onbekende locatie'
        if loc_naam not in loc_stats:
            loc_stats[loc_naam] = {'naam': loc_naam, 'sessies': 0, 'deelnemers': 0}
        loc_stats[loc_naam]['sessies'] += 1
        loc_stats[loc_naam]['deelnemers'] += len(item.deelnemers)
    for s in loc_stats.values():
        s['gem_deelnemers'] = round(s['deelnemers'] / s['sessies'], 1) if s['sessies'] > 0 else 0
    dn_per_locatie = sorted(loc_stats.values(), key=lambda x: x['deelnemers'], reverse=True)

    # Deelnemersfrequentie / Retentie
    retentie = {
        '1x (Eenmalig)': 0,
        '2x': 0,
        '3 tot 4x': 0,
        '5+ keer (Vaste kern)': 0
    }
    for count in deelnemer_frequenties.values():
        if count == 1:
            retentie['1x (Eenmalig)'] += 1
        elif count == 2:
            retentie['2x'] += 1
        elif 3 <= count <= 4:
            retentie['3 tot 4x'] += 1
        else:
            retentie['5+ keer (Vaste kern)'] += 1
    dn_retentie = list(retentie.items())
    dn_retentie_chart_labels = list(retentie.keys())
    dn_retentie_chart_data = list(retentie.values())

    # Tijdlijn (per maand bij specifiek jaar, of per jaar bij 'alle')
    if jaar != 'alle':
        dn_tijdlijn_labels = ['Jan', 'Feb', 'Mrt', 'Apr', 'Mei', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dec']
        dn_tijdlijn_deelnemers = [0] * 12
        dn_tijdlijn_sessies = [0] * 12
        for item in act_items:
            m = item.datum.month - 1
            dn_tijdlijn_sessies[m] += 1
            dn_tijdlijn_deelnemers[m] += len(item.deelnemers)
    else:
        jr_dict_sessies = {}
        jr_dict_deelnemers = {}
        for item in act_items:
            yr = item.datum.year
            jr_dict_sessies[yr] = jr_dict_sessies.get(yr, 0) + 1
            jr_dict_deelnemers[yr] = jr_dict_deelnemers.get(yr, 0) + len(item.deelnemers)
        all_yrs = sorted(list(set(list(jr_dict_sessies.keys()) + [date.today().year])))
        dn_tijdlijn_labels = [str(y) for y in all_yrs]
        dn_tijdlijn_deelnemers = [jr_dict_deelnemers.get(y, 0) for y in all_yrs]
        dn_tijdlijn_sessies = [jr_dict_sessies.get(y, 0) for y in all_yrs]

    # Recente sessies overzicht
    dn_recente_sessies = []
    for item in act_items[:15]:
        dn_count = len(item.deelnemers)
        is_volzet = item.max_deelnemers is not None and dn_count >= item.max_deelnemers
        dn_recente_sessies.append({
            'id': item.id,
            'datum': item.datum,
            'uur_van': item.uur_van,
            'uur_tot': item.uur_tot,
            'type_naam': item.type.naam if item.type else 'Onbekend',
            'type_kleur': getattr(item.type, 'kleur', 'primary'),
            'locatie_naam': item.locatie.naam if item.locatie else 'Onbekend',
            'omschrijving': item.omschrijving or '',
            'deelnemers_count': dn_count,
            'max_deelnemers': item.max_deelnemers,
            'is_volzet': is_volzet,
            'digidokters': [dd.naam for dd in item.digidokters]
        })

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
        per_locatie=per_locatie,
        heeft_consultatie_locaties=heeft_consultatie_locaties,
        per_geslacht=per_geslacht,
        per_resultaat=per_resultaat,
        totaal_resultaten=totaal_resultaten,
        heeft_resultaten=heeft_resultaten,
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
        max_loc_sessions=max_loc_sessions,
        max_type_sessions=max_type_sessions,
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

        # Tab 4: Activiteiten & Deelnemers
        dn_totaal_sessies=dn_totaal_sessies,
        dn_totaal_inschrijvingen=dn_totaal_inschrijvingen,
        dn_totaal_unieke_deelnemers=dn_totaal_unieke_deelnemers,
        dn_gem_deelnemers_per_sessie=dn_gem_deelnemers_per_sessie,
        dn_bezettingsgraad=dn_bezettingsgraad,
        dn_volzette_sessies=dn_volzette_sessies,
        dn_volzette_percentage=dn_volzette_percentage,
        dn_per_postcode=dn_per_postcode,
        dn_per_leeftijd=dn_per_leeftijd,
        dn_leeftijd_chart_labels=dn_leeftijd_chart_labels,
        dn_leeftijd_chart_data=dn_leeftijd_chart_data,
        dn_per_toestel=dn_per_toestel,
        dn_toestel_chart_labels=dn_toestel_chart_labels,
        dn_toestel_chart_data=dn_toestel_chart_data,
        dn_per_type=dn_per_type,
        dn_per_locatie=dn_per_locatie,
        dn_retentie=dn_retentie,
        dn_retentie_chart_labels=dn_retentie_chart_labels,
        dn_retentie_chart_data=dn_retentie_chart_data,
        dn_tijdlijn_labels=dn_tijdlijn_labels,
        dn_tijdlijn_deelnemers=dn_tijdlijn_deelnemers,
        dn_tijdlijn_sessies=dn_tijdlijn_sessies,
        dn_recente_sessies=dn_recente_sessies,

        actieve_tab=actieve_tab
    )