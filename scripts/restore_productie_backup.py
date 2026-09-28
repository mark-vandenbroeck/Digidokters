#!/usr/bin/env python3
"""
restore_productie_backup.py

Script om de meest recente PostgreSQL productie-backup (ZIP-bestand uit GitHub Actions)
te restoren in een gereserveerd schema in de lokale PostgreSQL database (LXC Postgres op proxmox3).

Kenmerken:
- Zoekt automatisch het nieuwste backup ZIP-bestand in de opgegeven backup-map.
- Pakt het PostgreSQL custom dump-bestand (.dump) tijdelijk uit.
- Zet tabellen, sequences, constraints en data over naar het opgegeven doelschema (standaard: 'productie').
- Laat het 'public' schema (lokaal ontwikkelwerk) volledig intact.
- Geschikt voor handmatige uitvoering én als automatische cronjob.
- Houdt een statusbestand bij zodat dezelfde backup niet onnodig opnieuw gerestored wordt (tenzij --force).
- Ondersteunt logging naar console en optioneel naar een logbestand.
"""

import argparse
import glob
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Standaardinstellingen
DEFAULT_BACKUP_DIR = "/Users/mark/Python/Digidokters-Backup"
DEFAULT_SCHEMA = "productie"
DEFAULT_STATE_FILE = os.path.expanduser("~/.digidokters_last_restored_backup")
DEFAULT_LOG_FILE = os.path.expanduser("~/Library/Logs/digidokters_backup_restore.log")

# Mogelijke paden voor PostgreSQL 17 client tools op macOS / Linux
PG_BIN_SEARCH_PATHS = [
    "/opt/homebrew/opt/postgresql@17/bin",
    "/opt/homebrew/bin",
    "/usr/local/opt/postgresql@17/bin",
    "/usr/local/bin",
    "/usr/lib/postgresql/17/bin",
    "/usr/bin",
]


def setup_logging(log_file: str | None = None, verbose: bool = False):
    """Configureert logging naar console en optioneel logbestand."""
    handlers = [logging.StreamHandler(sys.stdout)]
    if log_file:
        try:
            log_dir = os.path.dirname(os.path.abspath(log_file))
            os.makedirs(log_dir, exist_ok=True)
            handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
        except Exception as e:
            print(f"[WAARSCHUWING] Kon logbestand niet openen ({log_file}): {e}", file=sys.stderr)

    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
    )


def find_pg_binary(name: str) -> str:
    """Zoekt het gevraagde PostgreSQL binary (bijv. pg_restore, psql)."""
    # Eerst zoeken in expliciete zoekpaden (PG17 prioriteit)
    for path in PG_BIN_SEARCH_PATHS:
        full_path = os.path.join(path, name)
        if os.path.isfile(full_path) and os.access(full_path, os.X_OK):
            return full_path

    # Fallback naar PATH
    found = shutil.which(name)
    if found:
        return found

    raise FileNotFoundError(
        f"PostgreSQL utility '{name}' niet gevonden. Installeer postgresql@17 via brew (`brew install postgresql@17`)."
    )


def find_latest_backup_zip(backup_dir: str) -> Path | None:
    """Vindt het meest recente backup ZIP-bestand."""
    dir_path = Path(backup_dir)
    if not dir_path.is_dir():
        logging.error(f"Backup-directory bestaat niet of is niet gemount: {backup_dir}")
        return None

    zip_files = list(dir_path.glob("digidokters-backup-*.zip"))
    if not zip_files:
        # Zoek eventueel alle .zip bestanden
        zip_files = [f for f in dir_path.glob("*.zip") if not f.name.startswith("._")]

    if not zip_files:
        logging.warning(f"Geen backup ZIP-bestanden gevonden in: {backup_dir}")
        return None

    # Sorteren op bestandsnaam (bevat YYYY-MM-DD_HHMM timestamp) of modificatietijd
    def sort_key(p: Path):
        # Match YYYY-MM-DD_HHMM in filename
        match = re.search(r"(\d{4}-\d{2}-\d{2}[_-]\d{4,6})", p.name)
        if match:
            return match.group(1)
        return str(p.stat().st_mtime)

    sorted_files = sorted(zip_files, key=sort_key, reverse=True)
    return sorted_files[0]


def get_last_restored_file(state_file: str) -> str | None:
    """Leest de naam van het laatst gerestorede bestand uit het statusbestand."""
    if os.path.exists(state_file):
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception as e:
            logging.warning(f"Kon statusbestand niet lezen: {e}")
    return None


def save_last_restored_file(state_file: str, filename: str):
    """Bewaart de naam van het laatst gerestorede bestand."""
    try:
        os.makedirs(os.path.dirname(os.path.abspath(state_file)), exist_ok=True)
        with open(state_file, "w", encoding="utf-8") as f:
            f.write(filename.strip())
    except Exception as e:
        logging.warning(f"Kon statusbestand niet opslaan ({state_file}): {e}")


def transform_sql_for_schema(raw_sql: str, target_schema: str) -> str:
    """
    Transformeert de pg_restore SQL-uitvoer zodat alle objecten in het doelschema
    terechtkomen i.p.v. het 'public' schema.
    """
    lines = raw_sql.splitlines(keepends=True)
    out = []

    # Schema heraanmaken en search_path instellen
    out.append(f"-- Automatisch gegenereerd door restore_productie_backup.py\n")
    out.append(f"DROP SCHEMA IF EXISTS \"{target_schema}\" CASCADE;\n")
    out.append(f"CREATE SCHEMA \"{target_schema}\";\n")
    out.append(f"SET search_path = \"{target_schema}\", pg_catalog;\n\n")

    in_copy_block = False

    for line in lines:
        if line.startswith("COPY public."):
            # Tabeldefinitie in COPY header aanpassen
            out.append(line.replace("COPY public.", f"COPY \"{target_schema}\".", 1))
            in_copy_block = True
        elif in_copy_block:
            # Data-regels binnen COPY ongewijzigd laten (voorkomt ongewenste datavervanging)
            if line.strip() == r"\.":
                in_copy_block = False
            out.append(line)
        else:
            # DDL instructies aanpassen van public. naar target_schema.
            modified_line = line.replace("public.", f"\"{target_schema}\".")
            # En eventuele SCHEMA public definities
            modified_line = modified_line.replace("SCHEMA public", f"SCHEMA \"{target_schema}\"")
            out.append(modified_line)

    return "".join(out)


def restore_backup(
    zip_path: Path,
    db_url: str,
    target_schema: str,
    dry_run: bool = False,
) -> bool:
    """Pakt het dumpbestand uit en voert de restore uit naar het doelschema."""
    pg_restore_bin = find_pg_binary("pg_restore")
    psql_bin = find_pg_binary("psql")

    logging.info(f"Gebruikte tools: pg_restore={pg_restore_bin}, psql={psql_bin}")
    logging.info(f"Backupbestand: {zip_path.name} ({zip_path.stat().st_size / (1024*1024):.1f} MB)")
    logging.info(f"Doelschema: {target_schema}")

    with tempfile.TemporaryDirectory(prefix="digidokters_restore_") as temp_dir:
        # 1. Uitpakken van ZIP
        logging.info("ZIP-bestand uitpakken...")
        with zipfile.ZipFile(zip_path, "r") as z:
            dump_members = [m for m in z.namelist() if m.endswith(".dump")]
            if not dump_members:
                logging.error(f"Geen .dump bestand gevonden in {zip_path.name}")
                return False
            dump_filename = dump_members[0]
            extracted_dump = z.extract(dump_filename, temp_dir)

        logging.info(f"Dumpbestand uitgepakt: {dump_filename} ({os.path.getsize(extracted_dump) / (1024*1024):.1f} MB)")

        if dry_run:
            logging.info("[DRY-RUN] Restore-stappen overgeslagen wegens --dry-run flag.")
            return True

        # 2. pg_restore uitvoeren om SQL te genereren voor 'public' schema
        logging.info("SQL genereren uit custom dump via pg_restore...")
        restore_cmd = [
            pg_restore_bin,
            "-n", "public",     # Alleen public schema objecten
            "-O",               # Geen ownership commands (voorkomt rolconflicten)
            "-x",               # Geen privilege/grant commands
            "-f", "-",          # Output naar stdout
            extracted_dump,
        ]

        res = subprocess.run(restore_cmd, capture_output=True, text=True)
        if res.returncode != 0:
            logging.error(f"pg_restore fout (code {res.returncode}):\n{res.stderr}")
            return False

        # 3. SQL transformeren naar doelschema
        logging.info(f"SQL transformeren naar schema '{target_schema}'...")
        transformed_sql = transform_sql_for_schema(res.stdout, target_schema)

        # 4. SQL uitvoeren via psql
        logging.info(f"Gegevens inladen in PostgreSQL schema '{target_schema}'...")
        psql_cmd = [
            psql_bin,
            db_url,
            "-v", "ON_ERROR_STOP=1",
            "--quiet",
        ]

        psql_res = subprocess.run(
            psql_cmd,
            input=transformed_sql,
            text=True,
            capture_output=True,
        )

        if psql_res.returncode != 0:
            logging.error(f"psql restore mislukt (code {psql_res.returncode}):\n{psql_res.stderr}")
            return False

    logging.info(f"Restore succesvol voltooid in schema '{target_schema}'!")
    return True


def main():
    # Lees .env bestand indien aanwezig in huidige werkmap of projectmap
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if env_file.exists():
        load_dotenv(dotenv_path=env_file)
    else:
        load_dotenv()

    parser = argparse.ArgumentParser(
        description="Restore de meest recente productie database-dump naar een lokaal PostgreSQL schema."
    )
    parser.add_argument(
        "--backup-dir",
        default=os.environ.get("BACKUP_DIR", DEFAULT_BACKUP_DIR),
        help=f"Pad naar de map met backup ZIP-bestanden (standaard: '{DEFAULT_BACKUP_DIR}')",
    )
    parser.add_argument(
        "--schema",
        default=os.environ.get("RESTORE_SCHEMA", DEFAULT_SCHEMA),
        help=f"Doelschema in PostgreSQL (standaard: '{DEFAULT_SCHEMA}')",
    )
    parser.add_argument(
        "--db-url",
        default=os.environ.get("DATABASE_URL"),
        help="PostgreSQL connectiestring (standaard: DATABASE_URL uit .env)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Voer restore altijd uit, zelfs als dit bestand al eerder gerestored is.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Controleer en pak uit, maar voer geen wijzigingen door in de database.",
    )
    parser.add_argument(
        "--log-file",
        default=DEFAULT_LOG_FILE,
        help=f"Pad naar logbestand (standaard: '{DEFAULT_LOG_FILE}')",
    )
    parser.add_argument(
        "--no-log-file",
        action="store_true",
        help="Schrijf geen logbestand, alleen console uitvoer.",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Toon extra debug logging.",
    )

    args = parser.parse_args()

    log_path = None if args.no_log_file else args.log_file
    setup_logging(log_file=log_path, verbose=args.verbose)

    logging.info("=== Start Digidokters Backup Restore Taak ===")

    if not args.db_url:
        logging.error(
            "Geen DATABASE_URL gevonden! Zorg dat DATABASE_URL in je .env staat of geef --db-url mee."
        )
        sys.exit(1)

    latest_zip = find_latest_backup_zip(args.backup_dir)
    if not latest_zip:
        logging.info("Taak beëindigd: geen geldige backup gevonden om te restoren.")
        sys.exit(0)

    last_restored = get_last_restored_file(DEFAULT_STATE_FILE)
    if not args.force and last_restored == latest_zip.name:
        logging.info(
            f"De meest recente backup ({latest_zip.name}) is al eerder succesvol gerestored. "
            "Geen actie vereist. (Gebruik --force om opnieuw te forceren)."
        )
        sys.exit(0)

    success = restore_backup(
        zip_path=latest_zip,
        db_url=args.db_url,
        target_schema=args.schema,
        dry_run=args.dry_run,
    )

    if success:
        if not args.dry_run:
            save_last_restored_file(DEFAULT_STATE_FILE, latest_zip.name)
        logging.info("=== Backup Restore Taak Succesvol Afgerond ===")
        sys.exit(0)
    else:
        logging.error("=== Backup Restore Taak Mislukt ===")
        sys.exit(1)


if __name__ == "__main__":
    main()
