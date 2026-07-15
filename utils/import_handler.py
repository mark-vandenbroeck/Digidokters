"""Import handler: verwerkt CSV en XLSX bestanden naar de database."""
import os
import logging
import pandas as pd
from datetime import datetime, date, timezone
from extensions import db
from models.digidokter import Digidokter
from models.age_category import AgeCategory
from models.device import Device
from models.registration import Registration


# Verwachte kolomnamen (case-insensitive mapping)
KOLOM_MAP = {
    'datum': 'datum',
    'date': 'datum',
    'tijdstempel': 'datum',
    'timestamp': 'datum',
    'client': 'client',
    'cliënt': 'client',
    'klant': 'client',
    'voornaam deelnemer': 'client',
    'naam': 'client',
    'digidokter': 'digidokter',
    'vrijwilliger': 'digidokter',
    'aantal bezoeken digidokter': 'nieuwe_klant',
    'nieuwe klant': 'nieuwe_klant',
    'nieuwe_pad': 'nieuwe_klant',
    'nieuw': 'nieuwe_klant',
    'van waar ken je de digidokter?': 'herkomst',
    'herkomst': 'herkomst',
    'geslacht': 'geslacht',
    'gender': 'geslacht',
    'sex': 'geslacht',
    'onderwerp': 'onderwerp',
    'leeftijdscategorie': 'leeftijdscategorie',
    'leeftijd': 'leeftijdscategorie',
    'leeftijd deelnemer': 'leeftijdscategorie',
    'age category': 'leeftijdscategorie',
    'toestel': 'toestel',
    'toestel patiënt': 'toestel',
    'device': 'toestel',
    'apparaat': 'toestel',
}

VERPLICHTE_KOLOMMEN = ['datum', 'client', 'digidokter', 'onderwerp', 'leeftijdscategorie', 'toestel']


def _setup_logger(log_path: str) -> logging.Logger:
    logger = logging.getLogger(f'import_{datetime.now().timestamp()}')
    logger.setLevel(logging.DEBUG)
    handler = logging.FileHandler(log_path, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    logger.addHandler(handler)
    return logger


def _parse_nieuwe_klant(waarde) -> bool:
    if pd.isna(waarde) or waarde is None:
        return False
    s = str(waarde).strip().lower()
    return s in ('nieuwe klant', '1', 'ja', 'yes', 'true', 'j', 'waar')


def _parse_geslacht(waarde) -> str | None:
    if pd.isna(waarde) or waarde is None:
        return None
    s = str(waarde).strip().lower()
    if s in ('man', 'm', 'male', 'he', 'him'):
        return 'man'
    if s in ('vrouw', 'v', 'f', 'female', 'she', 'her'):
        return 'vrouw'
    return None


def _parse_date(waarde) -> date | None:
    if isinstance(waarde, date):
        return waarde
    if isinstance(waarde, datetime):
        return waarde.date()
    if pd.isna(waarde):
        return None
    # Strip eventuele tijdstempels (bijv. "13-6-2026 07:05:29" -> "13-6-2026")
    datum_deel = str(waarde).strip().split(' ')[0]
    for fmt in ('%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d', '%d.%m.%Y'):
        try:
            return datetime.strptime(datum_deel, fmt).date()
        except ValueError:
            continue
    return None


def verwerk_import(bestand_pad: str, bestandsnaam: str, log_map: str) -> dict:
    """
    Lees een CSV of XLSX bestand in en importeer in de database.
    Geeft een dict terug met: totaal, toegevoegd, overgeslagen, fouten, log_bestand.
    """
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_bestand = f"import_{timestamp}.log"
    log_pad = os.path.join(log_map, log_bestand)
    logger = _setup_logger(log_pad)

    resultaat = {
        'totaal': 0, 'toegevoegd': 0, 'overgeslagen': 0,
        'fouten': [], 'log_bestand': log_bestand
    }

    logger.info(f'Start import van bestand: {bestandsnaam}')

    # Lees bestand
    try:
        ext = os.path.splitext(bestandsnaam)[1].lower()
        if ext == '.csv':
            df = pd.read_csv(bestand_pad, dtype=str, encoding='utf-8-sig')
        elif ext in ('.xlsx', '.xls'):
            df = pd.read_excel(bestand_pad, dtype=str)
        else:
            msg = f'Niet-ondersteund bestandsformaat: {ext}'
            logger.error(msg)
            resultaat['fouten'].append(msg)
            return resultaat
    except Exception as e:
        msg = f'Fout bij lezen van bestand: {e}'
        logger.error(msg)
        resultaat['fouten'].append(msg)
        return resultaat

    # Normaliseer kolomnamen
    df.columns = [KOLOM_MAP.get(c.strip().lower(), c.strip().lower()) for c in df.columns]
    logger.info(f'Kolommen gevonden: {list(df.columns)}')

    # Controleer verplichte kolommen
    ontbrekend = [k for k in VERPLICHTE_KOLOMMEN if k not in df.columns]
    if ontbrekend:
        msg = f'Ontbrekende verplichte kolommen: {", ".join(ontbrekend)}'
        logger.error(msg)
        resultaat['fouten'].append(msg)
        return resultaat

    # Cacheer lookup-tabellen
    from utils.tenant import get_huidige_organisatie_id
    org_id = get_huidige_organisatie_id()

    digidokters = {d.naam.lower(): d for d in Digidokter.query.filter_by(actief=True, organisatie_id=org_id).all()}
    leeftijden = {l.naam.lower(): l for l in AgeCategory.query.filter_by(actief=True, organisatie_id=org_id).all()}
    toestellen = {t.naam.lower(): t for t in Device.query.filter_by(actief=True, organisatie_id=org_id).all()}

    # Cacheer bestaande registraties (voor dubbele-detectie) en registratienummer-
    # tellers per jaar in telkens 1 query, zodat we niet per rij naar de database
    # moeten gaan. Dat is essentieel bij een externe database (Supabase/Render):
    # elke round-trip kost netwerklatency, en bij honderden rijen loopt dat op
    # tot een gunicorn worker timeout.
    from sqlalchemy import extract, func
    bestaande_registraties = set(
        db.session.query(Registration.datum, Registration.client, Registration.digidokter_id)
        .filter(Registration.organisatie_id == org_id).all()
    )
    tellers = {
        int(jaar): aantal
        for jaar, aantal in db.session.query(
            extract('year', Registration.datum), func.count(Registration.id)
        ).filter(Registration.organisatie_id == org_id).group_by(extract('year', Registration.datum)).all()
    }

    resultaat['totaal'] = len(df)

    for idx, rij in df.iterrows():
        rijnr = idx + 2  # Excel-rijnummer (1-indexed + header)

        # Verplichte velden
        datum = _parse_date(rij.get('datum'))
        if datum is None:
            msg = f'Rij {rijnr}: Ongeldige datum "{rij.get("datum")}"'
            logger.warning(msg)
            resultaat['fouten'].append(msg)
            resultaat['overgeslagen'] += 1
            continue

        client = str(rij.get('client', '')).strip()
        if not client:
            msg = f'Rij {rijnr}: Cliëntnaam ontbreekt'
            logger.warning(msg)
            resultaat['fouten'].append(msg)
            resultaat['overgeslagen'] += 1
            continue

        onderwerp = str(rij.get('onderwerp', '')).strip()

        # Digidokter opzoeken of aanmaken
        dd_naam_original = str(rij.get('digidokter', '')).strip()
        if not dd_naam_original:
            msg = f'Rij {rijnr}: Digidokter ontbreekt'
            logger.warning(msg)
            resultaat['fouten'].append(msg)
            resultaat['overgeslagen'] += 1
            continue
        dd_naam_lower = dd_naam_original.lower()
        digidokter = digidokters.get(dd_naam_lower)
        if digidokter is None:
            max_volgorde = db.session.query(db.func.max(Digidokter.volgorde)).filter(Digidokter.organisatie_id == org_id).scalar() or 0
            digidokter = Digidokter(naam=dd_naam_original, actief=True, volgorde=max_volgorde + 1, organisatie_id=org_id)
            db.session.add(digidokter)
            db.session.flush()
            digidokters[dd_naam_lower] = digidokter
            logger.info(f'Nieuwe digidokter aangemaakt: {dd_naam_original}')

        # Leeftijdscategorie opzoeken of aanmaken
        lft_naam_original = str(rij.get('leeftijdscategorie', '')).strip()
        if not lft_naam_original:
            msg = f'Rij {rijnr}: Leeftijdscategorie ontbreekt'
            logger.warning(msg)
            resultaat['fouten'].append(msg)
            resultaat['overgeslagen'] += 1
            continue
        lft_naam_lower = lft_naam_original.lower()
        leeftijdscategorie = leeftijden.get(lft_naam_lower)
        if leeftijdscategorie is None:
            max_volgorde = db.session.query(db.func.max(AgeCategory.volgorde)).filter(AgeCategory.organisatie_id == org_id).scalar() or 0
            leeftijdscategorie = AgeCategory(naam=lft_naam_original, actief=True, volgorde=max_volgorde + 1, organisatie_id=org_id)
            db.session.add(leeftijdscategorie)
            db.session.flush()
            leeftijden[lft_naam_lower] = leeftijdscategorie
            logger.info(f'Nieuwe leeftijdscategorie aangemaakt: {lft_naam_original}')

        # Toestel opzoeken of aanmaken
        tst_naam_original = str(rij.get('toestel', '')).strip()
        if not tst_naam_original:
            msg = f'Rij {rijnr}: Toestel ontbreekt'
            logger.warning(msg)
            resultaat['fouten'].append(msg)
            resultaat['overgeslagen'] += 1
            continue
        tst_naam_lower = tst_naam_original.lower()
        toestel = toestellen.get(tst_naam_lower)
        if toestel is None:
            max_volgorde = db.session.query(db.func.max(Device.volgorde)).filter(Device.organisatie_id == org_id).scalar() or 0
            toestel = Device(naam=tst_naam_original, actief=True, volgorde=max_volgorde + 1, organisatie_id=org_id)
            db.session.add(toestel)
            db.session.flush()
            toestellen[tst_naam_lower] = toestel
            logger.info(f'Nieuw toestel aangemaakt: {tst_naam_original}')

        # Dubbele detectie (in-memory, geen query per rij)
        sleutel = (datum, client, digidokter.id)
        if sleutel in bestaande_registraties:
            msg = f'Rij {rijnr}: Dubbele registratie overgeslagen ({datum} / {client} / {digidokter.naam})'
            logger.info(msg)
            resultaat['overgeslagen'] += 1
            continue

        # Registratienummer via lokale teller (geen COUNT-query per rij)
        jaar = datum.year
        tellers[jaar] = tellers.get(jaar, 0) + 1
        registratienummer = f"{jaar}-{tellers[jaar]:04d}"

        # Aanmaken. We gebruiken een SAVEPOINT (begin_nested) zodat een fout in
        # één rij enkel die rij terugdraait, en niet de volledige batch die al
        # geflusht is sinds de laatste commit.
        try:
            with db.session.begin_nested():
                reg = Registration(
                    registratienummer=registratienummer,
                    datum=datum,
                    client=client,
                    digidokter_id=digidokter.id,
                    nieuwe_klant=_parse_nieuwe_klant(rij.get('nieuwe_klant', False)),
                    herkomst=str(rij.get('herkomst', '') or '').strip(),
                    geslacht=_parse_geslacht(rij.get('geslacht')),
                    onderwerp=onderwerp,
                    leeftijdscategorie_id=leeftijdscategorie.id,
                    toestel_id=toestel.id,
                    organisatie_id=org_id,
                )
                db.session.add(reg)
            bestaande_registraties.add(sleutel)
            resultaat['toegevoegd'] += 1
            logger.info(f'Rij {rijnr}: Toegevoegd als {registratienummer}')

            # Periodieke commit zodat de transactie niet onbeperkt groeit bij
            # zeer grote bestanden.
            if resultaat['toegevoegd'] % 100 == 0:
                db.session.commit()
        except Exception as e:
            tellers[jaar] -= 1  # teller terugdraaien, deze rij telde niet mee
            msg = f'Rij {rijnr}: Databasefout – {e}'
            logger.error(msg)
            resultaat['fouten'].append(msg)
            resultaat['overgeslagen'] += 1

    db.session.commit()

    logger.info(
        f'Import voltooid: {resultaat["totaal"]} totaal, '
        f'{resultaat["toegevoegd"]} toegevoegd, '
        f'{resultaat["overgeslagen"]} overgeslagen, '
        f'{len(resultaat["fouten"])} fouten'
    )
    return resultaat