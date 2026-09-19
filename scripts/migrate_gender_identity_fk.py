"""Script om de tekstuele 'geslacht' kolom in de 'registrations' tabel te migreren naar
een foreign key 'gender_identity_id' verwijzend naar de 'gender_identities' tabel.

Houdt rekening met:
- Organisatie ID (elke organisatie heeft eigen gender identities in de database)
- Case-insensitieve matching van de gender-naam (bijv. 'man' -> 'Man', 'VROUW' -> 'Vrouw')
- Ondersteuning voor --dry-run en --db-url (voor Supabase / PostgreSQL of lokaal SQLite)

Gebruik:
    python scripts/migrate_gender_identity_fk.py --dry-run
    python scripts/migrate_gender_identity_fk.py
    python scripts/migrate_gender_identity_fk.py --organisatie "Londerzeel"
    python scripts/migrate_gender_identity_fk.py --db-url "postgresql://postgres:password@db.xxx.supabase.co:5432/postgres"
"""
import os
import sys
import argparse

# Zorg dat het hoofdproject in sys.path staat
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from extensions import db
from models.organisatie import Organisatie
from models.gender_identity import GenderIdentity
from models.registration import Registration
import sqlalchemy as sa


def migrate_gender_identities(org_naam=None, dry_run=False, verbose=False, db_url=None):
    """Migreer registraties van tekst-geslacht naar gender_identity_id foreign key."""
    if db_url:
        if db_url.startswith('postgres://'):
            db_url = db_url.replace('postgres://', 'postgresql://', 1)
        os.environ['DATABASE_URL'] = db_url

    app = create_app()
    with app.app_context():
        # Controleer of 'gender_identity_id' kolom bestaat op registrations tabel
        inspector = sa.inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns('registrations')]
        has_fk_col = 'gender_identity_id' in columns
        has_text_col = 'geslacht' in columns

        print("=" * 70)
        print("MIGRATIE: Geslacht tekst -> GenderIdentity Foreign Key")
        print("=" * 70)
        print(f"Database dialect: {db.engine.dialect.name}")
        print(f"Kolom 'gender_identity_id' aanwezig: {'Ja' if has_fk_col else 'Nee'}")
        print(f"Kolom 'geslacht' (tekst) aanwezig: {'Ja' if has_text_col else 'Nee'}")

        if not has_fk_col:
            if dry_run:
                print("⚠️  [DRY-RUN] Kolom 'gender_identity_id' zou worden toegevoegd aan 'registrations'.")
            else:
                print("ℹ️  Toevoegen van kolom 'gender_identity_id' aan 'registrations'...")
                with db.engine.begin() as conn:
                    if db.engine.dialect.name == 'sqlite':
                        conn.execute(sa.text("ALTER TABLE registrations ADD COLUMN gender_identity_id INTEGER REFERENCES gender_identities(id)"))
                    else:
                        conn.execute(sa.text("ALTER TABLE registrations ADD COLUMN IF NOT EXISTS gender_identity_id INTEGER REFERENCES gender_identities(id)"))
                print("✓ Kolom 'gender_identity_id' toegevoegd.")

        # Haal organisaties op
        if org_naam:
            organisaties = Organisatie.query.filter(
                sa.or_(
                    Organisatie.naam.ilike(org_naam),
                    Organisatie.slug.ilike(org_naam)
                )
            ).all()
            if not organisaties:
                print(f"❌ Fout: Geen organisatie gevonden met naam of slug '{org_naam}'.")
                return False
        else:
            organisaties = Organisatie.query.order_by(Organisatie.id).all()

        totaal_gemigreerd = 0
        totaal_onbekend_gebleven = 0
        totaal_overgeslagen = 0

        for org in organisaties:
            print(f"\n🏢 Organisatie: {org.naam} (ID: {org.id}, Slug: {org.slug})")

            # Haal alle genderidentiteiten op voor deze organisatie
            genders = GenderIdentity.query.filter_by(organisatie_id=org.id).all()
            gender_map = {g.naam.strip().lower(): g for g in genders}
            print(f"   Beschikbare genderidentiteiten ({len(genders)}): {', '.join(f'{g.naam} (ID: {g.id})' for g in genders) if genders else 'Geen'}")

            # Lees ruwe data uit registrations tabel
            with db.engine.connect() as conn:
                if has_text_col and has_fk_col:
                    sql = sa.text("SELECT id, registratienummer, client, geslacht, gender_identity_id FROM registrations WHERE organisatie_id = :org_id")
                elif has_text_col and not has_fk_col:
                    sql = sa.text("SELECT id, registratienummer, client, geslacht, NULL as gender_identity_id FROM registrations WHERE organisatie_id = :org_id")
                else:
                    sql = sa.text("SELECT id, registratienummer, client, NULL as geslacht, gender_identity_id FROM registrations WHERE organisatie_id = :org_id")
                rows = conn.execute(sql, {"org_id": org.id}).fetchall()

            if not rows:
                print("   Geen registraties gevonden voor deze organisatie.")
                continue

            org_gemigreerd = 0
            org_reeds_ingesteld = 0
            org_leeg = 0
            org_onbekend = 0

            updates_to_perform = []

            for row in rows:
                reg_id = row[0]
                reg_nr = row[1]
                client_naam = row[2]
                geslacht_txt = row[3]
                current_fk = row[4]

                if current_fk is not None:
                    org_reeds_ingesteld += 1
                    totaal_overgeslagen += 1
                    continue

                if not geslacht_txt or not str(geslacht_txt).strip() or str(geslacht_txt).strip().lower() in ('nan', 'none', 'null', ''):
                    org_leeg += 1
                    continue

                geslacht_clean = str(geslacht_txt).strip().lower()
                matched_gender = gender_map.get(geslacht_clean)

                if matched_gender:
                    org_gemigreerd += 1
                    updates_to_perform.append((reg_id, matched_gender.id, reg_nr, client_naam, geslacht_txt, matched_gender.naam))
                else:
                    org_onbekend += 1
                    if verbose:
                        print(f"   ⚠️  Onbekende geslachtwaarde '{geslacht_txt}' bij registratie {reg_nr} ({client_naam}) - wordt NULL")

            print(f"   Status analyse:")
            print(f"   - Totaal aantal registraties: {len(rows)}")
            print(f"   - Reeds gekoppeld via FK: {org_reeds_ingesteld}")
            print(f"   - Te migreren op basis van tekst: {org_gemigreerd}")
            print(f"   - Leeg / niet gespecificeerd: {org_leeg}")
            print(f"   - Niet gematchte tekstwaarden: {org_onbekend}")

            if dry_run:
                if verbose and updates_to_perform:
                    print(f"   [DRY-RUN] Wijzigingen:")
                    for reg_id, g_id, reg_nr, client_naam, orig_val, new_name in updates_to_perform:
                        print(f"     -> Reg {reg_nr} ({client_naam}): '{orig_val}' -> {new_name} (ID: {g_id})")
            else:
                if updates_to_perform:
                    with db.engine.begin() as conn:
                        for reg_id, g_id, reg_nr, client_naam, orig_val, new_name in updates_to_perform:
                            conn.execute(
                                sa.text("UPDATE registrations SET gender_identity_id = :gid WHERE id = :reg_id"),
                                {"gid": g_id, "reg_id": reg_id}
                            )
                            if verbose:
                                print(f"     ✓ Reg {reg_nr} ({client_naam}): '{orig_val}' -> {new_name} (ID: {g_id})")
                    print(f"   ✓ {len(updates_to_perform)} registraties succesvol bijgewerkt!")

            totaal_gemigreerd += org_gemigreerd
            totaal_onbekend_gebleven += org_onbekend

        print("\n" + "=" * 70)
        if dry_run:
            print(f"🏁 [DRY-RUN VOLTOOID] In totaal zouden {totaal_gemigreerd} registraties worden bijgewerkt.")
            print("   Er zijn GEEN wijzigingen weggeschreven in de database.")
        else:
            print(f"🎉 [MIGRATIE VOLTOOID] In totaal zijn {totaal_gemigreerd} registraties bijgewerkt naar foreign key.")
        print("=" * 70)
        return True


def main():
    parser = argparse.ArgumentParser(
        description="Migreer geslacht tekstkolom naar gender_identity_id foreign key in registrations tabel."
    )
    parser.add_argument(
        "--organisatie", "-o",
        type=str,
        default=None,
        help="Naam of slug van een specifieke organisatie (standaard: alle organisaties)"
    )
    parser.add_argument(
        "--dry-run", "-d",
        action="store_true",
        help="Voer een simulatie uit zonder gegevens te wijzigen"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Toon gedetailleerde uitvoer per registratie"
    )
    parser.add_argument(
        "--db-url", "--db",
        type=str,
        default=None,
        help="Database connectie-URL (bijv. voor Supabase PostgreSQL: postgresql://postgres:...)"
    )

    args = parser.parse_args()

    success = migrate_gender_identities(
        org_naam=args.organisatie,
        dry_run=args.dry_run,
        verbose=args.verbose,
        db_url=args.db_url
    )
    if not success:
        sys.exit(1)


if __name__ == '__main__':
    main()
