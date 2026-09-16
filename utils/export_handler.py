import io
from datetime import date
import pandas as pd
from sqlalchemy.orm import joinedload
from models.registration import Registration
from models.age_category import AgeCategory
from models.device import Device
from extensions import db


def _haal_registraties(
    van_datum: date | None = None,
    tot_datum: date | None = None,
    digidokter_id: int | None = None,
    leeftijdscategorie_id: int | None = None,
    toestel_id: int | None = None,
) -> list:
    """Haal gefilterde registraties op als lijst van dicts met eager loading."""
    from utils.tenant import get_huidige_organisatie_id
    org_id = get_huidige_organisatie_id()
    query = (
        db.session.query(Registration)
        .options(
            joinedload(Registration.digidokter),
            joinedload(Registration.herkomst),
            joinedload(Registration.locatie),
            joinedload(Registration.leeftijdscategorie).joinedload(AgeCategory.mapped_to),
            joinedload(Registration.toestel).joinedload(Device.mapped_to),
        )
        .filter(Registration.organisatie_id == org_id)
        .order_by(Registration.datum.desc(), Registration.registratienummer.desc())
    )

    if van_datum:
        query = query.filter(Registration.datum >= van_datum)
    if tot_datum:
        query = query.filter(Registration.datum <= tot_datum)
    if digidokter_id:
        query = query.filter(Registration.digidokter_id == digidokter_id)
    if leeftijdscategorie_id:
        mapped_l_ids = [c.id for c in AgeCategory.query.filter_by(mapped_to_id=leeftijdscategorie_id).all()]
        query = query.filter(Registration.leeftijdscategorie_id.in_([leeftijdscategorie_id] + mapped_l_ids))
    if toestel_id:
        mapped_t_ids = [t.id for t in Device.query.filter_by(mapped_to_id=toestel_id).all()]
        query = query.filter(Registration.toestel_id.in_([toestel_id] + mapped_t_ids))

    rijen = []
    for reg in query.all():
        rijen.append({
            'Registratienummer': reg.registratienummer,
            'Datum': reg.datum.strftime('%d/%m/%Y') if reg.datum else '',
            'Bezoeker': reg.client,
            'Digidokter': reg.digidokter.naam if reg.digidokter else '',
            'Nieuwe bezoeker': 'Ja' if reg.nieuwe_klant else 'Nee',
            'Herkomst': reg.herkomst.naam if reg.herkomst else '',
            'Geslacht': reg.geslacht or '',
            'Onderwerp': reg.onderwerp,
            'Leeftijdscategorie': reg.leeftijdscategorie.effectieve_naam if reg.leeftijdscategorie else '',
            'Toestel': reg.toestel.effectieve_naam if reg.toestel else '',
            'Locatie': reg.locatie.naam if reg.locatie else '',
        })
    return rijen


def exporteer_csv(
    van_datum=None, tot_datum=None,
    digidokter_id=None, leeftijdscategorie_id=None, toestel_id=None
) -> bytes:
    """Genereer CSV als bytes."""
    rijen = _haal_registraties(van_datum, tot_datum, digidokter_id, leeftijdscategorie_id, toestel_id)
    df = pd.DataFrame(rijen) if rijen else pd.DataFrame(
        columns=['Registratienummer', 'Datum', 'Bezoeker', 'Digidokter',
                 'Nieuwe bezoeker', 'Herkomst', 'Geslacht', 'Onderwerp', 'Leeftijdscategorie', 'Toestel', 'Locatie']
    )
    output = io.StringIO()
    df.to_csv(output, index=False, encoding='utf-8-sig')
    return output.getvalue().encode('utf-8-sig')


def exporteer_xlsx(
    van_datum=None, tot_datum=None,
    digidokter_id=None, leeftijdscategorie_id=None, toestel_id=None
) -> bytes:
    """Genereer XLSX als bytes."""
    rijen = _haal_registraties(van_datum, tot_datum, digidokter_id, leeftijdscategorie_id, toestel_id)
    df = pd.DataFrame(rijen) if rijen else pd.DataFrame(
        columns=['Registratienummer', 'Datum', 'Bezoeker', 'Digidokter',
                 'Nieuwe bezoeker', 'Herkomst', 'Geslacht', 'Onderwerp', 'Leeftijdscategorie', 'Toestel', 'Locatie']
    )

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Registraties')

        # Kolombreedte aanpassen
        ws = writer.sheets['Registraties']
        for col in ws.columns:
            max_len = max((len(str(cell.value)) for cell in col if cell.value), default=10)
            ws.column_dimensions[col[0].column_letter].width = min(max_len + 2, 60)

    return output.getvalue()
