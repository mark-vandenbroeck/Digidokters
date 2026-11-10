#!/usr/bin/env python3
"""
uploads/Buggenhout/upload_buggenhout.py

Uploadt registraties van organisatie Buggenhout vanuit een Excel-bestand
(standaard: uploads/Buggenhout/Buggenhout 2026-11-10.xlsx).

Stappen:
1. Verwijdert alle bestaande registraties voor organisatie Buggenhout.
2. Maakt/vindt de fictieve gebruiker "Initiële upload" (upload@example.com)
   en het bijbehorende Digidokter-profiel voor Buggenhout.
3. Leest twee sheets in:
   - "Digibuddies Dinsdag Centrum" -> Locatie "Bib Buggenhout"
   - "2026 digibuddies Opstal"     -> Locatie "Boekenschuur Opstal"
4. Neemt Datum, Bezoeker (voornaam + spatie + naam) en Onderwerp (Vraag of probleem) over.
5. Voorziet een "Onbekend" toestel en leeftijdscategorie (aangezien deze niet geregistreerd werden).
6. Bepaalt chronologisch 'nieuwe_klant' en kent sequentiële registratienummers toe (2026-0001, ...).
7. Ondersteunt zowel de lokale PostgreSQL database als de Live productie database (--live).

Gebruik:
    # Testen tegen lokale database (dry-run / preview):
    python uploads/Buggenhout/upload_buggenhout.py --dry-run

    # Uitvoeren op lokale database:
    python uploads/Buggenhout/upload_buggenhout.py

    # Uitvoeren op Live (productie) database:
    python uploads/Buggenhout/upload_buggenhout.py --live
"""

import os
import sys
import argparse
import secrets
from datetime import datetime, date, timezone
from werkzeug.security import generate_password_hash
import openpyxl

# Zorg dat het projectpad in sys.path staat (twee niveaus hoger)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, '.env'))

from config import Config
from app import create_app
from extensions import db
from models.constants import ROLE_MEDEWERKER
from models.organisatie import Organisatie, UserOrganisatie
from models.user import User
from models.digidokter import Digidokter
from models.location import Location
from models.device import Device
from models.age_category import AgeCategory
from models.registration import Registration
from models.question_classification import QuestionClassification

DEFAULT_EXCEL_PATH = os.path.join(os.path.dirname(__file__), "Buggenhout 2026-11-10.xlsx")


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Upload registratiedata voor organisatie Buggenhout uit Excel"
    )
    parser.add_argument(
        "--excel",
        default=DEFAULT_EXCEL_PATH,
        help=f"Pad naar het Excel-bestand (standaard: {DEFAULT_EXCEL_PATH})"
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Upload naar de Live (productie) database (PROD_DATABASE_URL uit .env)"
    )
    parser.add_argument(
        "--db-url",
        help="Aangepaste database connectie-URL"
    )
    parser.add_argument(
        "--schema",
        help="Database schema (standaard: 'productie' voor lokaal, 'public' voor live)"
    )
    parser.add_argument(
        "--organisatie",
        default="buggenhout",
        help="Slug of ID van de organisatie (standaard: buggenhout)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Voer enkel een simulatie uit zonder wijzigingen op te slaan in de database"
    )
    return parser.parse_args()


def configure_app(args):
    """Initialiseert en configureert de Flask-applicatiecontext op basis van de CLI-argumenten."""
    class CustomConfig(Config):
        pass

    target_schema = args.schema

    if args.live:
        prod_url = args.db_url or os.environ.get("PROD_DATABASE_URL")
        if not prod_url:
            print("Fout: Geen PROD_DATABASE_URL gevonden in .env!")
            sys.exit(1)

        # Normaliseer URL en driver
        if prod_url.startswith("postgres://"):
            prod_url = prod_url.replace("postgres://", "postgresql+psycopg2://", 1)
        elif prod_url.startswith("postgresql://") and not prod_url.startswith("postgresql+"):
            prod_url = prod_url.replace("postgresql://", "postgresql+psycopg2://", 1)

        base_url = prod_url.split("?")[0]
        schema = target_schema or "public"

        CustomConfig.SQLALCHEMY_DATABASE_URI = base_url
        CustomConfig.DB_SCHEMA = schema
        CustomConfig.SQLALCHEMY_ENGINE_OPTIONS = {
            "pool_pre_ping": True,
            "connect_args": {
                "client_encoding": "utf8",
                "sslmode": "prefer",
                "options": f"-c search_path={schema}"
            }
        }
        print("=== MODUS: LIVE PRODUCTIE DATABASE ===")
        print(f"Target host: {base_url.split('@')[-1] if '@' in base_url else 'verborgen'}")
        print(f"Target schema: {schema}")

    else:
        db_url = args.db_url or os.environ.get("DATABASE_URL", "sqlite:///digidokters.db")
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql+psycopg2://", 1)
        elif db_url.startswith("postgresql://") and not db_url.startswith("postgresql+"):
            db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)

        schema = target_schema or os.environ.get("DB_SCHEMA", "productie")

        CustomConfig.SQLALCHEMY_DATABASE_URI = db_url
        CustomConfig.DB_SCHEMA = schema
        if "postgresql" in db_url:
            connect_args = {"client_encoding": "utf8"}
            if schema:
                connect_args["options"] = f"-c search_path={schema},public"
            CustomConfig.SQLALCHEMY_ENGINE_OPTIONS = {
                "pool_pre_ping": True,
                "connect_args": connect_args
            }
        print("=== MODUS: LOKALE DATABASE ===")
        print(f"Target schema: {schema}")

    if args.dry_run:
        print("[DRY-RUN] Er worden GEEN wijzigingen definitief opgeslagen!")

    app = create_app(CustomConfig)
    return app


def vind_of_maak_organisatie(org_identifier):
    """Zoekt de organisatie op basis van ID of slug."""
    if str(org_identifier).isdigit():
        org = db.session.get(Organisatie, int(org_identifier))
    else:
        org = Organisatie.query.filter(
            (Organisatie.slug == org_identifier.lower()) |
            (Organisatie.naam.ilike(f"%{org_identifier}%"))
        ).first()

    if not org:
        print(f"Fout: Organisatie '{org_identifier}' niet gevonden in de database!")
        sys.exit(1)

    return org


def vind_of_maak_upload_user(org):
    """
    Maakt of vindt de fictieve gebruiker 'Initiële upload' (upload@example.com)
    en koppelt deze aan de organisatie via UserOrganisatie.
    """
    email = "upload@example.com"
    user_naam = "Initiële upload"

    user = User.query.filter((User.email == email) | (User.naam == user_naam)).first()
    if not user:
        random_password = secrets.token_urlsafe(32)
        user = User(
            naam=user_naam,
            email=email,
            rol=ROLE_MEDEWERKER,
            actief=True,
            moet_wachtwoord_wijzigen=False,
            wachtwoord_hash=generate_password_hash(random_password)
        )
        db.session.add(user)
        db.session.flush()
        print(f"[Gebruiker] Fictieve gebruiker '{user.naam}' ({user.email}) aangemaakt (ID: {user.id}).")
    else:
        print(f"[Gebruiker] Bestaande gebruiker '{user.naam}' ({user.email}) gevonden (ID: {user.id}).")

    # Controleer UserOrganisatie koppeling
    user_org = UserOrganisatie.query.filter_by(user_id=user.id, organisatie_id=org.id).first()
    if not user_org:
        user_org = UserOrganisatie(
            user_id=user.id,
            organisatie_id=org.id,
            rol="medewerker",
            actief=True
        )
        db.session.add(user_org)
        db.session.flush()
        print(f"[UserOrganisatie] Gebruiker gekoppeld aan organisatie '{org.naam}'.")

    # Controleer Digidokter profiel
    digidokter = Digidokter.query.filter_by(
        organisatie_id=org.id,
        naam=user_naam
    ).first()

    if not digidokter:
        digidokter = Digidokter(
            naam=user_naam,
            user_id=user.id,
            organisatie_id=org.id,
            actief=True,
            volgorde=99
        )
        db.session.add(digidokter)
        db.session.flush()
        print(f"[Digidokter] Digidokter-profiel '{digidokter.naam}' aangemaakt (ID: {digidokter.id}).")
    else:
        if digidokter.user_id != user.id:
            digidokter.user_id = user.id
            db.session.flush()
        print(f"[Digidokter] Bestaand Digidokter-profiel '{digidokter.naam}' gevonden (ID: {digidokter.id}).")

    return user, digidokter


def vind_of_maak_locaties(org):
    """Zoekt of maakt de locaties 'Bib Buggenhout' en 'Boekenschuur Opstal'."""
    locatie_namen = ["Bib Buggenhout", "Boekenschuur Opstal"]
    locaties = {}

    for naam in locatie_namen:
        loc = Location.query.filter(
            Location.organisatie_id == org.id,
            Location.naam.ilike(naam)
        ).first()

        if not loc:
            loc = Location(
                naam=naam,
                organisatie_id=org.id,
                actief=True,
                gebruikt_voor_consultaties=True,
                volgorde=0
            )
            db.session.add(loc)
            db.session.flush()
            print(f"[Locatie] Nieuwe locatie '{naam}' aangemaakt voor {org.naam} (ID: {loc.id}).")
        else:
            if not loc.gebruikt_voor_consultaties:
                loc.gebruikt_voor_consultaties = True
                db.session.flush()
            print(f"[Locatie] Locatie '{loc.naam}' gevonden (ID: {loc.id}).")
        locaties[naam] = loc

    return locaties


def vind_of_maak_defaults(org):
    """
    Vindt of maakt fallback Device ('Onbekend') en AgeCategory ('Onbekend')
    aangezien deze niet geregistreerd werden in het bronbestand.
    """
    # Device
    device = Device.query.filter(
        Device.organisatie_id == org.id,
        Device.naam.in_(["Onbekend", "Niet gespecificeerd"])
    ).first()

    if not device:
        device = Device(
            naam="Onbekend",
            actief=True,
            organisatie_id=org.id,
            volgorde=99
        )
        db.session.add(device)
        db.session.flush()
        print(f"[Toestel] Fallback-toestel 'Onbekend' aangemaakt voor {org.naam} (ID: {device.id}).")
    else:
        print(f"[Toestel] Fallback-toestel '{device.naam}' gevonden (ID: {device.id}).")

    # AgeCategory
    age_cat = AgeCategory.query.filter(
        AgeCategory.organisatie_id == org.id,
        AgeCategory.naam.in_(["Onbekend", "Niet gespecificeerd"])
    ).first()

    if not age_cat:
        age_cat = AgeCategory(
            naam="Onbekend",
            actief=True,
            organisatie_id=org.id,
            volgorde=99
        )
        db.session.add(age_cat)
        db.session.flush()
        print(f"[Leeftijd] Fallback-leeftijdscategorie 'Onbekend' aangemaakt voor {org.naam} (ID: {age_cat.id}).")
    else:
        print(f"[Leeftijd] Fallback-leeftijdscategorie '{age_cat.naam}' gevonden (ID: {age_cat.id}).")

    return device, age_cat


def wis_bestaande_registraties(org):
    """Verwijdert alle bestaande registraties en bijbehorende vraagclassificaties voor de organisatie."""
    # Haal registraties op
    registraties = Registration.query.filter_by(organisatie_id=org.id).all()
    aantal = len(registraties)

    if aantal > 0:
        reg_ids = [r.id for r in registraties]
        # Verwijder gekoppelde vraagclassificaties
        QuestionClassification.query.filter(QuestionClassification.registration_id.in_(reg_ids)).delete(synchronize_session=False)

        for r in registraties:
            db.session.delete(r)

        db.session.flush()
        print(f"[Wissen] {aantal} bestaande registraties voor {org.naam} succesvol gewist.")
    else:
        print(f"[Wissen] Geen bestaande registraties gevonden voor {org.naam}.")

    return aantal


def parse_excel(excel_path):
    """
    Leest de Excel-spreadsheet en extraheert de rijen uit:
    - 'Digibuddie Dinsdag Centrum' -> Locatie 'Bib Buggenhout'
    - '2026 digibuddie Opstal'     -> Locatie 'Boekenschuur Opstal'
    """
    if not os.path.exists(excel_path):
        print(f"Fout: Excel-bestand '{excel_path}' niet gevonden!")
        sys.exit(1)

    wb = openpyxl.load_workbook(excel_path, data_only=True)

    sheet_mapping = {}
    for sheet_name in wb.sheetnames:
        norm = sheet_name.strip().lower()
        if "digibudd" in norm and "centrum" in norm and "archief" not in norm and "2025" not in norm:
            sheet_mapping[sheet_name] = "Bib Buggenhout"
        elif "digibudd" in norm and "opstal" in norm and "archief" not in norm and "2025" not in norm:
            sheet_mapping[sheet_name] = "Boekenschuur Opstal"

    if len(sheet_mapping) < 2:
        print(f"Waarschuwing: Niet alle verwachte sheets gevonden. Gevonden mapping: {sheet_mapping}")

    print(f"[Excel] Te verwerken sheets: {list(sheet_mapping.keys())}")

    parsed_rows = []
    skipped_rows = 0

    for sheet_name, locatie_naam in sheet_mapping.items():
        ws = wb[sheet_name]
        sheet_count = 0

        for r in range(1, ws.max_row + 1):
            vals = [ws.cell(r, c).value for c in range(1, 5)]
            if not any(vals):
                continue

            datum_val, naam_val, voornaam_val, vraag_val = vals[0], vals[1], vals[2], vals[3]

            # Header rijen overslaan
            if str(datum_val).strip().lower().startswith(('datum', 'd', 'digibuddie')):
                continue

            # Controleer datumformaat
            datum_obj = None
            if isinstance(datum_val, datetime):
                datum_obj = datum_val.date()
            elif isinstance(datum_val, date):
                datum_obj = datum_val
            elif isinstance(datum_val, str):
                try:
                    datum_obj = datetime.strptime(datum_val.strip(), "%d/%m/%Y").date()
                except ValueError:
                    try:
                        datum_obj = datetime.strptime(datum_val.strip(), "%Y-%m-%d").date()
                    except ValueError:
                        pass

            if not datum_obj:
                skipped_rows += 1
                continue

            naam_str = str(naam_val).strip() if naam_val is not None else ""
            voornaam_str = str(voornaam_val).strip() if voornaam_val is not None else ""

            # Filter dummy waarden zoals '-', 'paasvakantie', etc.
            if naam_str in ["-", "- ", "paasvakantie"] and not voornaam_str:
                skipped_rows += 1
                continue

            # Bepaal client naam: voornaam + spatie + naam
            if voornaam_str and naam_str:
                client = f"{voornaam_str} {naam_str}"
            elif voornaam_str:
                client = voornaam_str
            elif naam_str:
                client = naam_str
            else:
                skipped_rows += 1
                continue

            onderwerp = str(vraag_val).strip() if vraag_val is not None and str(vraag_val).strip() else "Geen onderwerp opgegeven"

            parsed_rows.append({
                "datum": datum_obj,
                "client": client,
                "onderwerp": onderwerp,
                "locatie_naam": locatie_naam,
                "sheet": sheet_name,
                "row_idx": r
            })
            sheet_count += 1

        print(f"  - Sheet '{sheet_name}' -> {sheet_count} geldige registraties voor '{locatie_naam}'")

    print(f"[Excel] Totaal ingelezen: {len(parsed_rows)} registraties (overgeslagen dummy/lege rijen: {skipped_rows}).")
    return parsed_rows


def verwerk_upload(args):
    app = configure_app(args)

    with app.app_context():
        # 1. Zoek organisatie
        org = vind_of_maak_organisatie(args.organisatie)
        print(f"[Organisatie] Geselecteerd: {org.naam} (ID: {org.id}, slug: {org.slug})")

        # 2. Parse Excel
        parsed_records = parse_excel(args.excel)
        if not parsed_records:
            print("Geen registraties om te verwerken!")
            return

        # 3. Sorteer chronologisch op datum (en behoud oorspronkelijke volgorde per dag)
        parsed_records.sort(key=lambda x: (x["datum"], x["row_idx"]))

        if args.dry_run:
            print("\n--- SIMULATIE (DRY-RUN) ---")
            print(f"Zou {Registration.query.filter_by(organisatie_id=org.id).count()} bestaande registraties wissen.")
            print(f"Zou {len(parsed_records)} registraties aanmaken:")
            for i, item in enumerate(parsed_records[:5], 1):
                reg_nr = f"2026-{i:04d}"
                print(f"  {reg_nr} | {item['datum']} | {item['client']} | {item['locatie_naam']} | {item['onderwerp'][:40]}")
            if len(parsed_records) > 5:
                print(f"  ... en nog {len(parsed_records) - 5} andere.")
            print("--- EINDE SIMULATIE ---\n")
            return

        # 4. Fictieve gebruiker en digidokter opzetten
        user, digidokter = vind_of_maak_upload_user(org)

        # 5. Locaties opzetten
        locaties = vind_of_maak_locaties(org)

        # 6. Fallback Toestel en Leeftijdscategorie opzetten
        device, age_cat = vind_of_maak_defaults(org)

        # 7. Wis alle bestaande registraties voor Buggenhout
        wis_bestaande_registraties(org)

        # 8. Maak nieuwe registraties aan
        seen_clients = set()
        aangemaakt_count = 0
        now_utc = datetime.now(timezone.utc)

        for i, item in enumerate(parsed_records, 1):
            reg_nr = f"2026-{i:04d}"
            locatie_obj = locaties.get(item["locatie_naam"])

            client_key = item["client"].strip().lower()
            nieuwe_klant = client_key not in seen_clients
            seen_clients.add(client_key)

            reg = Registration(
                registratienummer=reg_nr,
                datum=item["datum"],
                client=item["client"],
                onderwerp=item["onderwerp"],
                digidokter_id=digidokter.id,
                aangemaakt_door_id=user.id,
                locatie_id=locatie_obj.id if locatie_obj else None,
                toestel_id=device.id,
                leeftijdscategorie_id=age_cat.id,
                nieuwe_klant=nieuwe_klant,
                organisatie_id=org.id,
                aangemaakt_op=now_utc,
                gewijzigd_op=now_utc
            )
            db.session.add(reg)
            aangemaakt_count += 1

        # 9. Commit naar database
        try:
            db.session.commit()
            print("\n==========================================")
            print(f"UPLOAD SUCCESVOL VOLTOOID VOOR {org.naam.upper()}!")
            print(f"Totaal nieuw aangemaakte registraties: {aangemaakt_count}")
            print(f"Aantal unieke bezoekers: {len(seen_clients)}")
            print(f"Registratienummers: 2026-0001 t/m 2026-{aangemaakt_count:04d}")
            print("==========================================\n")
        except Exception as e:
            db.session.rollback()
            print(f"\n[FOUT] Commit mislukt, wijzigingen teruggedraaid! Fout: {e}")
            sys.exit(1)


if __name__ == "__main__":
    cli_args = parse_arguments()
    verwerk_upload(cli_args)

