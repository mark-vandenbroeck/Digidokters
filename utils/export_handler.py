"""Export handler: genereert CSV en XLSX bestanden van gefilterde registraties."""
import io
from datetime import date
import pandas as pd
from models.registration import Registration
from app import db


def _haal_registraties(
    van_datum: date | None = None,
    tot_datum: date | None = None,
    digidokter_id: int | None = None,
    leeftijdscategorie_id: int | None = None,
    toestel_id: int | None = None,
) -> list:
    """Haal gefilterde registraties op als lijst van dicts."""
    query = db.session.query(Registration).order_by(
        Registration.datum.desc(), Registration.registratienummer.desc()
    )

    if van_datum:
        query = query.filter(Registration.datum >= van_datum)
    if tot_datum:
        query = query.filter(Registration.datum <= tot_datum)
    if digidokter_id:
        query = query.filter(Registration.digidokter_id == digidokter_id)
    if leeftijdscategorie_id:
        query = query.filter(Registration.leeftijdscategorie_id == leeftijdscategorie_id)
    if toestel_id:
        query = query.filter(Registration.toestel_id == toestel_id)

    rijen = []
    for reg in query.all():
        rijen.append({
            'Registratienummer': reg.registratienummer,
            'Datum': reg.datum.strftime('%d/%m/%Y') if reg.datum else '',
            'Cliënt': reg.client,
            'Digidokter': reg.digidokter.naam if reg.digidokter else '',
            'Nieuwe klant': 'Ja' if reg.nieuwe_klant else 'Nee',
            'Herkomst': reg.herkomst or '',
            'Onderwerp': reg.onderwerp,
            'Leeftijdscategorie': reg.leeftijdscategorie.naam if reg.leeftijdscategorie else '',
            'Toestel': reg.toestel.naam if reg.toestel else '',
        })
    return rijen


def exporteer_csv(
    van_datum=None, tot_datum=None,
    digidokter_id=None, leeftijdscategorie_id=None, toestel_id=None
) -> bytes:
    """Genereer CSV als bytes."""
    rijen = _haal_registraties(van_datum, tot_datum, digidokter_id, leeftijdscategorie_id, toestel_id)
    df = pd.DataFrame(rijen) if rijen else pd.DataFrame(
        columns=['Registratienummer', 'Datum', 'Cliënt', 'Digidokter',
                 'Nieuwe klant', 'Herkomst', 'Onderwerp', 'Leeftijdscategorie', 'Toestel']
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
        columns=['Registratienummer', 'Datum', 'Cliënt', 'Digidokter',
                 'Nieuwe klant', 'Herkomst', 'Onderwerp', 'Leeftijdscategorie', 'Toestel']
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
