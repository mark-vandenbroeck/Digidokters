"""Statistieken routes."""
from flask import Blueprint, render_template, request
from flask_login import login_required
from sqlalchemy import func, extract
from extensions import db
from models.registration import Registration
from models.digidokter import Digidokter
from models.age_category import AgeCategory
from models.device import Device

stats_bp = Blueprint('stats', __name__)


@stats_bp.route('/statistieken')
@login_required
def overzicht():
    jaar = request.args.get('jaar', None, type=int)
    if not jaar:
        from datetime import date
        jaar = date.today().year

    # Filter op jaar
    def jaar_filter(q):
        return q.filter(extract('year', Registration.datum) == jaar)

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
             .group_by('jaar').order_by('jaar').all()
             if r[0] is not None]
    if not jaren:
        from datetime import date
        jaren = [date.today().year]

    return render_template(
        'stats/overview.html',
        jaar=jaar,
        jaren=jaren,
        totaal_jaar=totaal_jaar,
        per_maand=per_maand,
        per_digidokter=per_digidokter,
        per_leeftijd=per_leeftijd,
        per_toestel=per_toestel,
        nieuwe_klanten=nieuwe_klanten,
        terugkerende_klanten=totaal_jaar - nieuwe_klanten,
        per_dag=per_dag,
    )
