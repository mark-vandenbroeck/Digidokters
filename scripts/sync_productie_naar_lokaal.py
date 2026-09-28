#!/usr/bin/env python3
"""
sync_productie_naar_lokaal.py

Maakt rechtstreeks een live backup (pg_dump) van de Supabase productie-database,
bewaart de dump op de interne SSD (/Users/mark/Python/Digidokters-Backup),
en restoret deze direct in het gereserveerde schema ('productie') van je lokale
PostgreSQL database (LXC Postgres op proxmox3).

Voordelen:
- 100% on-demand én geschikt als periodieke cronjob.
- Geen tussenstappen met downloaden en unzippen van GitHub Actions artifacts.
- Lokale 'public' schema (met artificiële testdata) blijft onaangeroerd.
- Veilige logging en foutafhandeling.

Gebruik:
    python scripts/sync_productie_naar_lokaal.py
    python scripts/sync_productie_naar_lokaal.py --dump-only     # Enkel dumpen naar SSD
    python scripts/sync_productie_naar_lokaal.py --schema custom # Ander doelschema
    python scripts/sync_productie_naar_lokaal.py --dry-run
"""

import argparse
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Standaardconfiguraties
DEFAULT_BACKUP_DIR = "/Users/mark/Python/Digidokters-Backup"
DEFAULT_SCHEMA = "productie"
DEFAULT_LOG_FILE = os.path.expanduser("~/Library/Logs/digidokters_backup_restore.log")

# Retentiebeleid: Grootvader-Vader-Zoon (GFS)
DEFAULT_KEEP_DAILY = 7      # Zoon: 7 dagelijkse backups
DEFAULT_KEEP_WEEKLY = 4     # Vader: 4 wekelijkse backups
DEFAULT_KEEP_MONTHLY = 2    # Grootvader: 2 maandelijkse backups

# Zoekpaden voor PostgreSQL 17 client utilities op macOS / Linux
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
    """Zoekt het gevraagde PostgreSQL utility (bijv. pg_dump, pg_restore, psql)."""
    for path in PG_BIN_SEARCH_PATHS:
        full_path = os.path.join(path, name)
        if os.path.isfile(full_path) and os.access(full_path, os.X_OK):
            return full_path

    found = shutil.which(name)
    if found:
        return found

    raise FileNotFoundError(
        f"PostgreSQL utility '{name}' niet gevonden. Installeer postgresql@17 via brew (`brew install postgresql@17`)."
    )


def transform_sql_for_schema(raw_sql: str, target_schema: str) -> str:
    """
    Transformeert de pg_restore SQL-uitvoer zodat alle objecten in het doelschema
    terechtkomen i.p.v. het 'public' schema.
    """
    lines = raw_sql.splitlines(keepends=True)
    out = []

    out.append(f"-- Gegenereerd door sync_productie_naar_lokaal.py op {datetime.now().isoformat()}\n")
    out.append(f"DROP SCHEMA IF EXISTS \"{target_schema}\" CASCADE;\n")
    out.append(f"CREATE SCHEMA \"{target_schema}\";\n")
    out.append(f"SET search_path = \"{target_schema}\", pg_catalog;\n\n")

    in_copy_block = False

    for line in lines:
        if line.startswith("COPY public."):
            out.append(line.replace("COPY public.", f"COPY \"{target_schema}\".", 1))
            in_copy_block = True
        elif in_copy_block:
            if line.strip() == r"\.":
                in_copy_block = False
            out.append(line)
        else:
            modified_line = line.replace("public.", f"\"{target_schema}\".")
            modified_line = modified_line.replace("SCHEMA public", f"SCHEMA \"{target_schema}\"")
            out.append(modified_line)

    return "".join(out)


# Ingebouwd Supabase Root CA certificaat (nodig voor Supabase poolers en direct connections)
SUPABASE_ROOT_CA = """-----BEGIN CERTIFICATE-----
MIIDxDCCAqygAwIBAgIUbLxMod62P2ktCiAkxnKJwtE9VPYwDQYJKoZIhvcNAQEL
BQAwazELMAkGA1UEBhMCVVMxEDAOBgNVBAgMB0RlbHdhcmUxEzARBgNVBAcMCk5l
dyBDYXN0bGUxFTATBgNVBAoMDFN1cGFiYXNlIEluYzEeMBwGA1UEAwwVU3VwYWJh
c2UgUm9vdCAyMDIxIENBMB4XDTIxMDQyODEwNTY1M1oXDTMxMDQyNjEwNTY1M1ow
azELMAkGA1UEBhMCVVMxEDAOBgNVBAgMB0RlbHdhcmUxEzARBgNVBAcMCk5ldyBD
YXN0bGUxFTATBgNVBAoMDFN1cGFiYXNlIEluYzEeMBwGA1UEAwwVU3VwYWJhc2Ug
Um9vdCAyMDIxIENBMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAqQXW
QyHOB+qR2GJobCq/CBmQ40G0oDmCC3mzVnn8sv4XNeWtE5XcEL0uVih7Jo4Dkx1Q
DmGHBH1zDfgs2qXiLb6xpw/CKQPypZW1JssOTMIfQppNQ87K75Ya0p25Y3ePS2t2
GtvHxNjUV6kjOZjEn2yWEcBdpOVCUYBVFBNMB4YBHkNRDa/+S4uywAoaTWnCJLUi
cvTlHmMw6xSQQn1UfRQHk50DMCEJ7Cy1RxrZJrkXXRP3LqQL2ijJ6F4yMfh+Gyb4
O4XajoVj/+R4GwywKYrrS8PrSNtwxr5StlQO8zIQUSMiq26wM8mgELFlS/32Uclt
NaQ1xBRizkzpZct9DwIDAQABo2AwXjALBgNVHQ8EBAMCAQYwHQYDVR0OBBYEFKjX
uXY32CztkhImng4yJNUtaUYsMB8GA1UdIwQYMBaAFKjXuXY32CztkhImng4yJNUt
aUYsMA8GA1UdEwEB/wQFMAMBAf8wDQYJKoZIhvcNAQELBQADggEBAB8spzNn+4VU
tVxbdMaX+39Z50sc7uATmus16jmmHjhIHz+l/9GlJ5KqAMOx26mPZgfzG7oneL2b
VW+WgYUkTT3XEPFWnTp2RJwQao8/tYPXWEJDc0WVQHrpmnWOFKU/d3MqBgBm5y+6
jB81TU/RG2rVerPDWP+1MMcNNy0491CTL5XQZ7JfDJJ9CCmXSdtTl4uUQnSuv/Qx
Cea13BX2ZgJc7Au30vihLhub52De4P/4gonKsNHYdbWjg7OWKwNv/zitGDVDB9Y2
CMTyZKG3XEu5Ghl1LEnI3QmEKsqaCLv12BnVjbkSeZsMnevJPs1Ye6TjjJwdik5P
o/bKiIz+Fq8=
-----END CERTIFICATE-----
"""

def get_supabase_ca_path() -> str:
    """Schrijft het Supabase Root CA certificaat naar een vast lokaal bestand."""
    ca_path = os.path.expanduser("~/.digidokters_supabase_ca.crt")
    try:
        if not os.path.exists(ca_path) or os.path.getsize(ca_path) < 100:
            with open(ca_path, "w", encoding="utf-8") as f:
                f.write(SUPABASE_ROOT_CA.strip() + "\n")
    except Exception as e:
        logging.warning(f"Kon CA-bestand niet aanmaken ({ca_path}): {e}")
    return ca_path


def get_pg_env() -> dict:
    """Stelt de juiste SSL CA bundle en instellingen in voor libpq/pg_dump/psql op macOS."""
    env = os.environ.copy()
    supabase_ca = get_supabase_ca_path()
    if os.path.exists(supabase_ca):
        env["PGSSLROOTCERT"] = supabase_ca
    elif not env.get("PGSSLROOTCERT"):
        for ca_path in [
            "/etc/ssl/cert.pem",
            "/opt/homebrew/etc/ca-certificates/cert.pem",
            "/etc/ssl/certs/ca-certificates.crt",
        ]:
            if os.path.exists(ca_path):
                env["PGSSLROOTCERT"] = ca_path
                break

    if not env.get("PGSSLMODE"):
        env["PGSSLMODE"] = "require"

    return env


def perform_dump(prod_db_url: str, dump_file_path: Path) -> bool:
    """Voert live pg_dump uit op Supabase productie-database."""
    pg_dump_bin = find_pg_binary("pg_dump")
    logging.info(f"Start pg_dump van productie via {pg_dump_bin}...")
    logging.info(f"Doelbestand: {dump_file_path}")

    start_time = time.time()
    dump_cmd = [
        pg_dump_bin,
        prod_db_url,
        "-F", "c",      # PostgreSQL Custom gecomprimeerd formaat
        "-Z", "9",      # Maximale gzip compressie
        "-f", str(dump_file_path),
    ]

    pg_env = get_pg_env()
    res = subprocess.run(dump_cmd, capture_output=True, text=True, env=pg_env)
    duration = time.time() - start_time

    if res.returncode != 0:
        logging.error(f"pg_dump mislukt (code {res.returncode}):\n{res.stderr}")
        if dump_file_path.exists():
            dump_file_path.unlink()
        return False

    size_mb = dump_file_path.stat().st_size / (1024 * 1024)
    logging.info(f"✓ pg_dump succesvol voltooid in {duration:.1f}s ({size_mb:.1f} MB)")
    return True


def perform_restore(dump_file_path: Path, local_db_url: str, target_schema: str) -> bool:
    """Restoret het dumpbestand naar het lokale PostgreSQL doelschema."""
    pg_restore_bin = find_pg_binary("pg_restore")
    psql_bin = find_pg_binary("psql")

    logging.info(f"Start restore naar lokaal schema '{target_schema}'...")
    start_time = time.time()

    # 1. SQL genereren uit custom dump
    restore_cmd = [
        pg_restore_bin,
        "-n", "public",     # Enkel de applicatietabellen uit public schema
        "-O",               # Geen ownership commando's
        "-x",               # Geen privilege/grant commando's
        "-f", "-",          # Output naar stdout
        str(dump_file_path),
    ]

    pg_env = get_pg_env()
    res = subprocess.run(restore_cmd, capture_output=True, text=True, env=pg_env)
    if res.returncode != 0:
        logging.error(f"pg_restore fout (code {res.returncode}):\n{res.stderr}")
        return False

    # 2. SQL transformeren
    transformed_sql = transform_sql_for_schema(res.stdout, target_schema)

    # 3. SQL uitvoeren via psql
    psql_cmd = [
        psql_bin,
        local_db_url,
        "-v", "ON_ERROR_STOP=1",
        "--quiet",
    ]

    psql_res = subprocess.run(
        psql_cmd,
        input=transformed_sql,
        text=True,
        capture_output=True,
        env=pg_env,
    )

    duration = time.time() - start_time

    if psql_res.returncode != 0:
        logging.error(f"psql restore mislukt (code {psql_res.returncode}):\n{psql_res.stderr}")
        return False

    logging.info(f"✓ Restore succesvol voltooid in {duration:.1f}s naar schema '{target_schema}'!")
    return True


def parse_backup_timestamp(path: Path) -> datetime:
    """Extraheert timestamp uit bestandsnaam of valt terug op modificatietijd."""
    match = re.search(r"(\d{4})[-_](\d{2})[-_](\d{2})[_-](\d{2})(\d{2})", path.name)
    if match:
        y, m, d, hh, mm = map(int, match.groups())
        return datetime(y, m, d, hh, mm)
    match_d = re.search(r"(\d{4})[-_](\d{2})[-_](\d{2})", path.name)
    if match_d:
        y, m, d = map(int, match_d.groups())
        return datetime(y, m, d, 0, 0)
    try:
        return datetime.fromtimestamp(path.stat().st_mtime)
    except Exception:
        return datetime.min


def apply_gfs_retention(
    backup_dir: Path,
    keep_daily: int = DEFAULT_KEEP_DAILY,
    keep_weekly: int = DEFAULT_KEEP_WEEKLY,
    keep_monthly: int = DEFAULT_KEEP_MONTHLY,
    dry_run: bool = False,
) -> tuple[dict, list]:
    """
    Past Grootvader-Vader-Zoon (GFS) retentie toe op de backup-directory.
    - keep_daily: aantal dagelijkse backups (Zoon)
    - keep_weekly: aantal wekelijkse backups (Vader)
    - keep_monthly: aantal maandelijkse backups (Grootvader)
    """
    if not backup_dir.is_dir():
        logging.warning(f"Retentie overgeslagen: map bestaat niet ({backup_dir})")
        return {}, []

    candidates = [
        f for f in backup_dir.iterdir()
        if f.is_file() and not f.name.startswith("._") and (f.suffix in [".dump", ".zip"] or "digidokters" in f.name)
    ]

    if not candidates:
        logging.info("Geen backup-bestanden gevonden voor retentiebeheer.")
        return {}, []

    files_with_dt = [(f, parse_backup_timestamp(f)) for f in candidates]
    files_with_dt.sort(key=lambda x: x[1], reverse=True)

    days = defaultdict(list)
    weeks = defaultdict(list)
    months = defaultdict(list)

    for f, dt in files_with_dt:
        days[dt.strftime("%Y-%m-%d")].append((f, dt))
        iso_year, iso_week, _ = dt.isocalendar()
        weeks[f"{iso_year}-W{iso_week:02d}"].append((f, dt))
        months[dt.strftime("%Y-%m")].append((f, dt))

    keep_reasons = defaultdict(list)

    # 1. Dagelijks (Zoon) - top N unieke dagen
    for day_key in sorted(days.keys(), reverse=True)[:keep_daily]:
        chosen_file, _ = days[day_key][0]
        keep_reasons[chosen_file].append(f"Dagelijks ({day_key})")

    # 2. Wekelijks (Vader) - top N unieke ISO-weken
    for week_key in sorted(weeks.keys(), reverse=True)[:keep_weekly]:
        chosen_file, _ = weeks[week_key][0]
        keep_reasons[chosen_file].append(f"Wekelijks ({week_key})")

    # 3. Maandelijks (Grootvader) - top N unieke kalendermaanden
    for month_key in sorted(months.keys(), reverse=True)[:keep_monthly]:
        chosen_file, _ = months[month_key][0]
        keep_reasons[chosen_file].append(f"Maandelijks ({month_key})")

    files_to_keep = set(keep_reasons.keys())
    files_to_delete = [f for f, dt in files_with_dt if f not in files_to_keep]

    logging.info("--- GFS Backup Retentie Overzicht ---")
    logging.info(f"Totaal aanwezige backups: {len(candidates)}")
    logging.info(f"Behouden backups ({len(files_to_keep)}):")
    for f in sorted(files_to_keep, key=parse_backup_timestamp, reverse=True):
        reasons_str = ", ".join(keep_reasons[f])
        size_mb = f.stat().st_size / (1024 * 1024)
        logging.info(f"  ✓ {f.name} ({size_mb:.1f} MB) -> [{reasons_str}]")

    if files_to_delete:
        logging.info(f"Te verwijderen verouderde backups ({len(files_to_delete)}):")
        for f in files_to_delete:
            if dry_run:
                logging.info(f"  [DRY-RUN] Zou verwijderen: {f.name}")
            else:
                try:
                    f.unlink()
                    logging.info(f"  ✗ Verwijderd: {f.name}")
                except Exception as e:
                    logging.error(f"  ! Kon bestand niet verwijderen ({f.name}): {e}")
    else:
        logging.info("Geen verouderde backups die verwijderd hoeven te worden.")

    return keep_reasons, files_to_delete


def main():
    # Laad .env bestand indien aanwezig
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if env_file.exists():
        load_dotenv(dotenv_path=env_file)
    else:
        load_dotenv()

    parser = argparse.ArgumentParser(
        description="Maak een live dump van de productie database en synchroniseer met het lokale PostgreSQL schema."
    )
    parser.add_argument(
        "--prod-db-url",
        default=os.environ.get("PROD_DATABASE_URL") or os.environ.get("PRODUCTION_DATABASE_URL"),
        help="Supabase Productie PostgreSQL connectiestring (standaard: PROD_DATABASE_URL uit .env)",
    )
    parser.add_argument(
        "--local-db-url",
        default=os.environ.get("DATABASE_URL"),
        help="Lokale PostgreSQL connectiestring op Proxmox (standaard: DATABASE_URL uit .env)",
    )
    parser.add_argument(
        "--backup-dir",
        default=os.environ.get("BACKUP_DIR", DEFAULT_BACKUP_DIR),
        help=f"Doelmap voor het opslaan van dumps (standaard: '{DEFAULT_BACKUP_DIR}')",
    )
    parser.add_argument(
        "--schema",
        default=os.environ.get("RESTORE_SCHEMA", DEFAULT_SCHEMA),
        help=f"Doelschema in lokale database (standaard: '{DEFAULT_SCHEMA}')",
    )
    parser.add_argument(
        "--dump-only",
        action="store_true",
        help="Maak enkel een dump op de SSD zonder te restoren naar de lokale database.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Test configuratie en paden zonder daadwerkelijk te dumpen of restoren.",
    )
    parser.add_argument(
        "--keep-daily",
        type=int,
        default=DEFAULT_KEEP_DAILY,
        help=f"Aantal dagelijkse backups om te behouden (Zoon, standaard: {DEFAULT_KEEP_DAILY})",
    )
    parser.add_argument(
        "--keep-weekly",
        type=int,
        default=DEFAULT_KEEP_WEEKLY,
        help=f"Aantal wekelijkse backups om te behouden (Vader, standaard: {DEFAULT_KEEP_WEEKLY})",
    )
    parser.add_argument(
        "--keep-monthly",
        type=int,
        default=DEFAULT_KEEP_MONTHLY,
        help=f"Aantal maandelijkse backups om te behouden (Grootvader, standaard: {DEFAULT_KEEP_MONTHLY})",
    )
    parser.add_argument(
        "--no-prune",
        action="store_true",
        help="Schakel het automatisch verwijderen van verouderde backups uit.",
    )
    parser.add_argument(
        "--log-file",
        default=DEFAULT_LOG_FILE,
        help=f"Pad naar logbestand (standaard: '{DEFAULT_LOG_FILE}')",
    )
    parser.add_argument(
        "--no-log-file",
        action="store_true",
        help="Schrijf geen logbestand, enkel console.",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Toon extra debug logging.",
    )

    args = parser.parse_args()

    log_path = None if args.no_log_file else args.log_file
    setup_logging(log_file=log_path, verbose=args.verbose)

    logging.info("=== Start Live Productie Sync & Backup ===")

    if not args.prod_db_url:
        logging.error(
            "Geen PROD_DATABASE_URL gevonden! Voeg 'PROD_DATABASE_URL=postgresql://...' toe aan je .env bestand "
            "of geef het mee via --prod-db-url."
        )
        sys.exit(1)

    if not args.dump_only and not args.local_db_url:
        logging.error(
            "Geen lokale DATABASE_URL gevonden! Zorg dat DATABASE_URL in .env staat of geef --local-db-url mee."
        )
        sys.exit(1)

    backup_dir_path = Path(args.backup_dir)
    if not backup_dir_path.exists():
        if str(args.backup_dir).startswith("/Volumes/"):
            logging.error(f"Externe schijf of backup-map is niet gemount: {args.backup_dir}")
            logging.error("Sluit je externe SSD aan en ontgrendel deze alvorens de sync uit te voeren.")
            sys.exit(1)
        try:
            backup_dir_path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logging.error(f"Backup-directory kon niet worden aangemaakt ({args.backup_dir}): {e}")
            sys.exit(1)

    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    dump_filename = f"digidokters_{stamp}.dump"
    dump_path = backup_dir_path / dump_filename

    if args.dry_run:
        logging.info("[DRY-RUN] Alle configuraties zijn geldig. Dump en restore overgeslagen wegens --dry-run.")
        if not args.no_prune:
            apply_gfs_retention(
                backup_dir_path,
                keep_daily=args.keep_daily,
                keep_weekly=args.keep_weekly,
                keep_monthly=args.keep_monthly,
                dry_run=True,
            )
        sys.exit(0)

    # Stap 1: pg_dump van productie
    dump_success = perform_dump(args.prod_db_url, dump_path)
    if not dump_success:
        logging.error("=== Live Productie Sync Mislukt (Dump gefaald) ===")
        sys.exit(1)

    # Stap 2: restore naar lokaal schema (tenzij --dump-only)
    if not args.dump_only:
        restore_success = perform_restore(dump_path, args.local_db_url, args.schema)
        if not restore_success:
            logging.error("=== Live Productie Sync Mislukt (Restore gefaald) ===")
            sys.exit(1)

    # Stap 3: GFS Retentiebeheer (tenzij --no-prune)
    if not args.no_prune:
        apply_gfs_retention(
            backup_dir_path,
            keep_daily=args.keep_daily,
            keep_weekly=args.keep_weekly,
            keep_monthly=args.keep_monthly,
            dry_run=False,
        )

    logging.info("=== Live Productie Sync & Backup Succesvol Afgerond ===")
    sys.exit(0)


if __name__ == "__main__":
    main()

