import os
import sys
import csv
import re
import argparse
from datetime import date, datetime

# Zorg ervoor dat het projectpad in sys.path staat
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from extensions import db
from models.organisatie import Organisatie
from models.agenda import AgendaItem
from models.activity_type import ActivityType
from models.location import Location
from models.digidokter import Digidokter
from sqlalchemy import func


def parse_hours(uur_str):
    """
    Parse verschillende uur-formaten uit de CSV-file en geef (uur_van, uur_tot) terug in HH:MM formaat.
    """
    s = uur_str.lower()
    s = s.replace("uur", "").replace("(?)", "").strip()
    
    # Enkel uur (bijv. "20") -> neem aan 2 uur duur
    if re.match(r'^\d+$', s):
        hour = int(s)
        return f"{hour:02d}:00", f"{(hour+2):02d}:00"
        
    # Open einde (bijv. "15:15u-..." of "19:30u-...")
    m_open = re.match(r'^(\d+)[u:]?(\d*)\s*u?\s*-\s*\.\.\.$', s)
    if m_open:
        start_h = int(m_open.group(1))
        start_m = int(m_open.group(2)) if m_open.group(2) else 0
        end_h = start_h + 2
        return f"{start_h:02d}:{start_m:02d}", f"{end_h:02d}:{start_m:02d}"
        
    # Splitsen op "-" voor start- en eindtijd
    parts = s.split('-')
    if len(parts) == 2:
        start_part = parts[0].strip()
        end_part = parts[1].strip()
        
        def parse_part(part):
            part = part.replace(':', 'u')
            if 'u' in part:
                p_parts = part.split('u')
                h = int(p_parts[0])
                m_str = p_parts[1].strip()
                m = int(m_str) if m_str else 0
                return f"{h:02d}:{m:02d}"
            else:
                h = int(part)
                return f"{h:02d}:00"
                
        try:
            return parse_part(start_part), parse_part(end_part)
        except Exception as e:
            raise ValueError(f"Fout bij parsen van tijd-onderdeel: {e}")
            
    raise ValueError(f"Onbekend uur-formaat: '{uur_str}'")


def main():
    parser = argparse.ArgumentParser(description="Importeer agenda uit CSV-bestand")
    parser.add_argument("csv_path", nargs="?", default="csv/aanwezigheden Digidokters - archief aanwezigheden_voorbij.csv", help="Pad naar het te importeren CSV-bestand")
    parser.add_argument("--db", help="Database connectie-URL (bijv. sqlite:///digidokters.db of postgresql://user:password@host/db)")
    parser.add_argument("--organisatie", default="londerzeel", help="Slug of ID van de organisatie (default: londerzeel)")
    args = parser.parse_args()

    # Configureer de database URI indien meegegeven
    from config import Config
    class CustomConfig(Config):
        pass

    if args.db:
        CustomConfig.SQLALCHEMY_DATABASE_URI = args.db
        print(f"Verbinden met opgegeven database: {args.db}")
    else:
        print(f"Verbinden met database uit configuratie: {CustomConfig.SQLALCHEMY_DATABASE_URI}")

    app = create_app(CustomConfig)

    with app.app_context():
        # Zoek organisatie op
        org = None
        if args.organisatie.isdigit():
            org = db.session.get(Organisatie, int(args.organisatie))
        else:
            org = Organisatie.query.filter_by(slug=args.organisatie).first()

        if not org:
            print(f"Fout: Organisatie '{args.organisatie}' niet gevonden in de database!")
            sys.exit(1)

        print(f"Importeren voor organisatie: {org.naam} (ID: {org.id})")

        csv_path = args.csv_path
        if not os.path.exists(csv_path):
            print(f"Fout: CSV-bestand '{csv_path}' bestaat niet!")
            sys.exit(1)

        # Caches om DB-lookups te minimaliseren
        location_cache = {}
        type_cache = {}
        digidokter_cache = {}

        # Haal bestaande agenda-items op om duplicaten te voorkomen
        existing_items = AgendaItem.query.filter_by(organisatie_id=org.id).all()
        existing_agenda_keys = {
            (item.datum, item.uur_van, item.uur_tot, item.type_id)
            for item in existing_items
        }

        # Statistieken
        stat_imported = 0
        stat_failed = 0
        stat_skipped_duplicates = 0
        stat_new_locations = 0
        stat_new_types = 0
        stat_new_digidokters = 0

        # Lees CSV
        with open(csv_path, newline='', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            
            # Valideer kolommen
            required_cols = ['Datum', 'Uur', 'locatie', 'Omschrijving']
            for col in required_cols:
                if col not in reader.fieldnames:
                    print(f"Fout: Vereiste kolom '{col}' ontbreekt in de CSV-file!")
                    print(f"Beschikbare kolommen: {reader.fieldnames}")
                    sys.exit(1)

            print("Start met inlezen van de rijen...")

            for line_no, row in enumerate(reader, start=2):
                # Sla lege rijen over
                if not any(row.values()):
                    continue

                datum_str = row['Datum'].strip()
                uur_str = row['Uur'].strip()
                loc_name = row['locatie'].strip()
                desc = row['Omschrijving'].strip()

                if not datum_str or not uur_str or not loc_name or not desc:
                    print(f"Rij {line_no} overgeslagen: mist verplichte velden (Datum, Uur, Locatie, of Omschrijving).")
                    stat_failed += 1
                    continue

                try:
                    # 1. Datum parsen (D-M-YYYY)
                    parsed_date = datetime.strptime(datum_str, '%d-%m-%Y').date()

                    # 2. Uren parsen
                    uur_van, uur_tot = parse_hours(uur_str)

                    # 3. Locatie opzoeken/aanmaken
                    if loc_name in location_cache:
                        locatie = location_cache[loc_name]
                    else:
                        locatie = Location.query.filter_by(organisatie_id=org.id, naam=loc_name).first()
                        if not locatie:
                            locatie = Location(naam=loc_name, actief=True, volgorde=0, organisatie_id=org.id)
                            db.session.add(locatie)
                            db.session.flush()
                            stat_new_locations += 1
                        location_cache[loc_name] = locatie

                    # 4. Type bepalen op basis van de omschrijving
                    if desc.startswith("Digicafé"):
                        type_name = "Digicafé"
                    elif desc.startswith("Digidokter"):
                        type_name = "Digidokters"
                    else:
                        type_name = desc

                    if not type_name:
                        type_name = "Digidokters"

                    # Type opzoeken/aanmaken
                    if type_name in type_cache:
                        act_type = type_cache[type_name]
                    else:
                        act_type = ActivityType.query.filter_by(organisatie_id=org.id, naam=type_name).first()
                        if not act_type:
                            act_type = ActivityType(naam=type_name, actief=True, volgorde=0, organisatie_id=org.id)
                            db.session.add(act_type)
                            db.session.flush()
                            stat_new_types += 1
                        type_cache[type_name] = act_type

                    # Uniekheids-check: (datum, uur_van, uur_tot, type_id)
                    key = (parsed_date, uur_van, uur_tot, act_type.id)
                    if key in existing_agenda_keys:
                        stat_skipped_duplicates += 1
                        continue
                    existing_agenda_keys.add(key)

                    # 5. Maak agenda-item
                    agenda_item = AgendaItem(
                        datum=parsed_date,
                        uur_van=uur_van,
                        uur_tot=uur_tot,
                        type_id=act_type.id,
                        locatie_id=locatie.id,
                        omschrijving=desc,
                        organisatie_id=org.id
                    )
                    db.session.add(agenda_item)
                    db.session.flush()

                    # 6. Digidokters koppelen
                    for d_idx in range(1, 13):
                        col_name = f"Digidokter {d_idx}"
                        if col_name in row:
                            dd_name = row[col_name].strip()
                            if dd_name:
                                # Gebruik enkel het gedeelte tot aan de eerste spatie
                                dd_name = dd_name.split(' ')[0]
                                
                                # Als de naam begint met "LukS" (case-insensitive), vervang door "Luk"
                                if dd_name.lower().startswith('luks'):
                                    dd_name = 'Luk'
                                    
                                cache_key = dd_name.lower()
                                if cache_key in digidokter_cache:
                                    digidokter = digidokter_cache[cache_key]
                                else:
                                    # Zoek case-insensitief in de database
                                    digidokter = Digidokter.query.filter(
                                        Digidokter.organisatie_id == org.id,
                                        func.lower(Digidokter.naam) == cache_key
                                    ).first()
                                    
                                    if not digidokter:
                                        digidokter = Digidokter(naam=dd_name, actief=True, volgorde=0, organisatie_id=org.id)
                                        db.session.add(digidokter)
                                        db.session.flush()
                                        stat_new_digidokters += 1
                                    digidokter_cache[cache_key] = digidokter

                                if digidokter not in agenda_item.digidokters:
                                    agenda_item.digidokters.append(digidokter)

                    stat_imported += 1

                except Exception as e:
                    print(f"Fout bij verwerken van rij {line_no} ({datum_str} - {uur_str}): {e}")
                    stat_failed += 1
                    continue

        # Commit alle wijzigingen aan het einde
        try:
            db.session.commit()
            print("\n--- IMPORT VOLTOOID ---")
            print(f"Succesvol geïmporteerde agenda-items: {stat_imported}")
            print(f"Duplicaten overgeslagen:             {stat_skipped_duplicates}")
            print(f"Rijen met fouten/overgeslagen:       {stat_failed}")
            print(f"Nieuwe locaties aangemaakt:          {stat_new_locations}")
            print(f"Nieuwe activiteitstypes aangemaakt:   {stat_new_types}")
            print(f"Nieuwe digidokters aangemaakt:        {stat_new_digidokters}")
        except Exception as e:
            db.session.rollback()
            print(f"\nFout: Database commit mislukt, wijzigingen teruggedraaid! Detail: {e}")
            sys.exit(1)


if __name__ == '__main__':
    main()
