# Handleiding: Agenda Import Script

Dit Python-script (`scripts/import_agenda.py`) maakt het mogelijk om historische of externe activiteiten en aanwezigheden van vrijwilligers (Digidokters) vanuit CSV-bestanden te importeren in de database. Het script ondersteunt zowel de lokale SQLite-database als externe/productie PostgreSQL-databases.

---

## Eigenschappen & functionaliteit
* **Automatisch parsen van datum en uren:** Converteert datums (`D-M-YYYY` formaat) en uiteenlopende uurformaten (bijv. `10 - 12 uur`, `13:30 - 16:30 uur`, `19:30u-...`) naar gestandaardiseerde SQL datatypes.
* **Dynamische aanmaak van stamgegevens:** 
  - Als een locatie nog niet bestaat binnen de geselecteerde organisatie, wordt deze automatisch aangemaakt.
  - Het activiteitstype wordt bepaald op basis van de omschrijving (bijv. als de omschrijving begint met "Digicafé" wordt het type "Digicafé", idem voor "Digidokters"). Niet-bestaande types worden automatisch aangemaakt.
  - Digidokters in kolommen `Digidokter 1` t/m `Digidokter 12` worden automatisch gezocht en gekoppeld. Hierbij worden de volgende regels toegepast:
    - **Enkel de voornaam** wordt overgenomen (het gedeelte tot aan de eerste spatie) om eventuele achternamen of extra toevoegingen zoals `(eenmalig)` of `(bib)` te negeren.
    - Als de naam begint met **`LukS`** (case-insensitive, bijv. `LukS.`, `luks`), wordt dit automatisch vervangen door **`Luk`**.
    - Er wordt **case-insensitive** in de database gezocht. Als de naam al bestaat (op hoofdletters/kleine letters na, bijv. `daniël` vs `Daniël`), wordt de exact bestaande spelling uit de database gebruikt om duplicaten te voorkomen.
    - Niet-bestaande digidokters worden automatisch nieuw aangemaakt.
* **Duplicatenpreventie:** Controleert voor elke rij of de combinatie `(datum, uur_van, uur_tot, type_id)` al bestaat in de database of eerder in het bestand. Dubbele rijen worden automatisch en veilig overgeslagen.
* **Transactioneel:** Alle imports worden binnen één database-transactie uitgevoerd. Als er halverwege een fout optreedt, wordt alles netjes teruggedraaid (rollback).

---

## Vereisten
Zorg ervoor dat de virtuele omgeving geactiveerd is en alle dependencies geïnstalleerd zijn:
```bash
source venv/bin/activate
pip install -r requirements.txt
```

---

## Gebruik & parameters

Het script kan worden uitgevoerd met de volgende syntax:
```bash
python scripts/import_agenda.py [pad_naar_csv] [optionele_parameters]
```

### Parameters:
* **`csv_path`** *(positioneel, optioneel)*: Het pad naar het te importeren CSV-bestand.
  - *Default:* `csv/aanwezigheden Digidokters - archief aanwezigheden_voorbij.csv`
* **`--db`** *(optioneel)*: Een custom database connectie-URL (bijv. voor PostgreSQL).
  - *Default:* Gebruikt de `DATABASE_URL` uit de omgevingsvariabelen of `.env`, of valt terug op de lokale SQLite database.
* **`--organisatie`** *(optioneel)*: De slug of het ID van de organisatie waaronder de items geïmporteerd moeten worden.
  - *Default:* `londerzeel`

---

## Voorbeelden van gebruik

### 1. Importeren in de lokale SQLite-database (Standaardbestand)
Als je het standaard archiefbestand wilt importeren in je lokale SQLite-database:
```bash
python scripts/import_agenda.py
```

### 2. Importeren van een specifiek CSV-bestand
Geef simpelweg het pad naar je bestand mee als eerste argument:
```bash
python scripts/import_agenda.py csv/mijn_nieuwe_aanwezigheden.csv
```

### 3. Importeren in de productie PostgreSQL-database
Om de gegevens rechtstreeks in de PostgreSQL-database op Render of een andere externe host te importeren, geef je de database connectie-URL mee:
```bash
python scripts/import_agenda.py csv/mijn_nieuwe_aanwezigheden.csv --db "postgresql://user:password@host:5432/dbname"
```

### 4. Importeren voor een andere organisatie (bijv. Leuven)
```bash
python scripts/import_agenda.py csv/leuven_aanwezigheden.csv --organisatie leuven
```

---

## CSV Bestand Structuur
Het CSV-bestand moet ten minste de volgende kolomkoppen hebben:
* `Datum`: Datum van de activiteit in het formaat `D-M-YYYY` (bijv. `6-4-2024`).
* `Uur`: Tijdstip (bijv. `10 - 12 uur`, `13u30-16u30`, `15:15u-...`).
* `locatie`: De naam van de locatie.
* `Omschrijving`: De activiteitomschrijving.
* `Digidokter 1` tot `Digidokter 12` *(optioneel)*: Namen van de aanwezige digidokters (bijv. `Daniël`, `Mark`). Lege cellen worden genegeerd.
