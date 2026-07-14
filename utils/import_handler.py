"""Import handler: verwerkt CSV en XLSX bestanden naar de database."""
import os
import logging
import pandas as pd
from datetime import datetime, date, timezone
from app import db
from models.digidokter import Digidokter
from models.age_category import AgeCategory
from models.device import Device
from models.registration import Registration


# Verwachte kolomnamen (case-insensitive mapping)
KOLOM_MAP = {
    'datum': 'datum',
    'date': 'datum',
    'client': 'client',
    'cliënt': 'client',
    'klant': 'client',
    'digidokter': 'digidokter',
    'vrijwilliger': 'digidokter',
    'nieuwe klant': 'nieuwe_klant',
    'nieuwe_klant': 'nieuwe_klant',
    'nieuw': 'nieuwe_klant',
    'herkomst': 'herkomst',
    'onderwerp': 'onderwerp',
    'leeftijdscategorie': 'leeftijdscategorie',
    'leeftijd': 'leeftijdscategorie',
    'age category': 'leeftijdscategorie',
    'toestel': 'toestel',
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


def _normalize_bool(waarde) -> bool:
    if isinstance(waarde, bool):
        return waarde
    if isinstance(waarde, (int, float)):
        return bool(waarde)
    s = str(waarde).strip().lower()
    return s in ('ja', 'yes', '1', 'true', 'waar', 'y', 'j')


def _parse_date(waarde) -> date | None:
    if isinstance(waarde, date):
        return waarde
    if isinstance(waarde, datetime):
        return waarde.date()
    if pd.isna(waarde):
        return None
    for fmt in ('%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d', '%d.%m.%Y'):
        try:
            return datetime.strptime(str(waarde).strip(), fmt).date()
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
    digidokters = {d.naam.lower(): d for d in Digidokter.query.filter_by(actief=True).all()}
    leeftijden = {l.naam.lower(): l for l in AgeCategory.query.filter_by(actief=True).all()}
    toestellen = {t.naam.lower(): t for t in Device.query.filter_by(actief=True).all()}

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

        # Digidokter opzoeken
        dd_naam = str(rij.get('digidokter', '')).strip().lower()
        digidokter = digidokters.get(dd_naam)
        if digidokter is None:
            msg = f'Rij {rijnr}: Onbekende digidokter "{dd_naam}"'
            logger.warning(msg)
            resultaat['fouten'].append(msg)
            resultaat['overgeslagen'] += 1
            continue

        # Leeftijdscategorie opzoeken
        lft_naam = str(rij.get('leeftijdscategorie', '')).strip().lower()
        leeftijdscategorie = leeftijden.get(lft_naam)
        if leeftijdscategorie is None:
            msg = f'Rij {rijnr}: Onbekende leeftijdscategorie "{lft_naam}"'
            logger.warning(msg)
            resultaat['fouten'].append(msg)
            resultaat['overgeslagen'] += 1
            continue

        # Toestel opzoeken
        tst_naam = str(rij.get('toestel', '')).strip().lower()
        toestel = toestellen.get(tst_naam)
        if toestel is None:
            msg = f'Rij {rijnr}: Onbekend toestel "{tst_naam}"'
            logger.warning(msg)
            resultaat['fouten'].append(msg)
            resultaat['overgeslagen'] += 1
            continue

        # Dubbele detectie
        bestaande = Registration.query.filter_by(
            datum=datum,
            client=client,
            digidokter_id=digidokter.id
        ).first()
        if bestaande:
            msg = f'Rij {rijnr}: Dubbele registratie overgeslagen ({datum} / {client} / {digidokter.naam})'
            logger.info(msg)
            resultaat['overgeslagen'] += 1
            continue

        # Aanmaken
        try:
            reg = Registration(
                registratienummer=Registration.genereer_registratienummer(datum.year),
                datum=datum,
                client=client,
                digidokter_id=digidokter.id,
                nieuwe_klant=_normalize_bool(rij.get('nieuwe_klant', False)),
                herkomst=str(rij.get('herkomst', '') or '').strip(),
                onderwerp=onderwerp,
                leeftijdscategorie_id=leeftijdscategorie.id,
                toestel_id=toestel.id,
            )
            db.session.add(reg)
            db.session.commit()
            resultaat['toegevoegd'] += 1
            logger.info(f'Rij {rijnr}: Toegevoegd als {reg.registratienummer}')
        except Exception as e:
            db.session.rollback()
            msg = f'Rij {rijnr}: Databasefout – {e}'
            logger.error(msg)
            resultaat['fouten'].append(msg)
            resultaat['overgeslagen'] += 1

    logger.info(
        f'Import voltooid: {resultaat["totaal"]} totaal, '
        f'{resultaat["toegevoegd"]} toegevoegd, '
        f'{resultaat["overgeslagen"]} overgeslagen, '
        f'{len(resultaat["fouten"])} fouten'
    )
    return resultaat
