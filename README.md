# Digidokters Platform — Technische Documentatie

Dit project is een webgebaseerd registratie- en planningsplatform voor **Digidokters** (vrijwilligers die burgers helpen met digitale vragen). Het is ontworpen als een multi-tenant applicatie waarmee verschillende gemeentes of organisaties hun eigen geïsoleerde werkomgeving hebben voor de registratie van bezoeken, planning in de agenda, en uitgebreide rapportage.

---

## 🚀 Technologie Stack

*   **Backend:** Python 3.12, Flask (Webframework)
*   **Database ORM:** SQLAlchemy met Flask-SQLAlchemy
*   **Database Migraties:** Alembic met Flask-Migrate
*   **Authentication:** Flask-Login
*   **Beveiliging & Rate Limiting:** Flask-Limiter, CSRF-beveiliging en Secure Session cookies
*   **Frontend:** HTML5, CSS3 (Vanilla CSS), Bootstrap 5.3 (Styling), Bootstrap Icons, en Chart.js (Visualisaties)
*   **Deployment:** Render.com (PostgreSQL database & Flask Web Service)

---

## 🛠️ Architectuur & Multi-tenancy

Het platform is opgebouwd rond een **shared-database, shared-schema multi-tenant model**:
*   Elke tabel (behalve het globale platformbeheer) bevat een kolom `organisatie_id` om data tussen verschillende steden/organisaties te isoleren.
*   Bij het inloggen of via een subdomein-resolver wordt de actieve organisatie vastgesteld en in de Flask-sessie opgeslagen.
*   Alle database-queries worden gefilterd op basis van de actieve `organisatie_id` om strikte data-isolatie te garanderen.

### Belangrijkste tabellen en datamodel:
1.  **Organisaties (`organisaties`):** Beheert de verschillende tenants (bijv. Londerzeel).
2.  **Gebruikers (`users`):** Beheert beheerders en medewerkers. Gekoppeld aan organisaties via `user_organisaties`. Tevens voorzien van wachtwoord-resetkolommen (`reset_code`, `reset_code_verloopt_op`).
3.  **Digidokters (`digidokters`):** Vrijwilligers binnen een specifieke organisatie.
4.  **Registraties (`registrations`):** Registratie van een cliëntbezoek.
5.  **Agenda-items (`agenda_items`):** Geplande sessies met type activiteit, locatie en aanwezige digidokters.
6.  **Mappen (`mappen`):** Hiërarchische mappenstructuur per organisatie met self-referencing `parent_id`.
7.  **Documenten (`documenten`):** Bestanden (PDF, Word, Excel, afbeeldingen) opgeslagen als binaire data (`LargeBinary`) met versienummering.

---

## 📋 Features & Functionaliteiten

### 1. Bezoekenregistratie
*   Medewerkers en beheerders kunnen snel binnenlopende cliënten registreren.
*   Vrijwilligers (digidokters) met de rol `medewerker` hebben ook de mogelijkheid om registraties te wissen bij foutieve invoer.

### 2. Agenda & Planning
*   Ondersteunt eenmalige en terugkerende activiteiten (dagelijks, wekelijks, maandelijks) met een optionele einddatum.
*   Uur- en datumfilters (toekomstige vs. voorbije activiteiten tonen).
*   Sorteerbare kolommen op alle eigenschappen (datum, tijd, locatie, type, etc.).
*   Aanpasbare status (actief/gedeactiveerd) en badgekleur per activiteitstype (Blauw, Teal, Paars, Oranje) die direct in de agenda-lijst worden getoond.

### 3. Statistieken & Dashboard
Gepresenteerd via twee duidelijke tabbladen op de `/statistieken` pagina:
*   **Bezoekers & Consultaties:** Tijdlijn per week (jaar-op-jaar), maandelijkse verdelingen, meest populaire leeftijdscategorieën, toestellen, geslachtsverdeling en drukste dagen.
*   **Vrijwilligers & Agenda:** Totaal aantal gepresteerde uren per digidokter, sessies per locatie en activiteitstype, urentrend per maand en de **Druktest ratio** (gemiddeld aantal bezoeken per aanwezige vrijwilliger per sessie, uitsluitend berekend voor activiteiten in het verleden).

### 4. Documentbeheer
*   Volledige hiërarchische mappenstructuur per organisatie.
*   Uploaden en downloaden van bestanden (PDF, Word, Excel, afbeeldingen) met een limiet van 16 MB per bestand.
*   Binaire bestandsobjecten worden direct in de database opgeslagen (`LargeBinary`), zodat ze automatisch meegaan in databasebackups en isolatie.
*   In-browser preview voor ondersteunde bestandstypen (zoals PDF en afbeeldingen).
*   **Versiebeheer:** Mogelijkheid om bestaande documenten te overschrijven, waarbij het versienummer automatisch wordt verhoogd (v1, v2, v3...).
*   Toegang is afgeschermd voor gebruikers met de rol `lezer`.

### 5. Wachtwoord Vergeten & Herstelprocedure
*   Ingebouwde herstelprocedure via het inlogscherm.
*   Gebruikers voeren hun gebruikersnaam in en ontvangen een 6-cijferige verificatiecode op hun geregistreerde e-mailadres via de Brevo HTTPS REST API.
*   De code heeft een verlooptijd van exact 30 minuten.
*   Bij invoer van de juiste code kan de gebruiker een nieuw wachtwoord instellen dat direct wordt gevalideerd op complexiteitseisen.

### 6. CSV Import-script (`scripts/import_agenda.py`)
Een robuust CLI-script om historische CSV-bestanden met agenda-items en aanwezigheden te importeren:
*   **Naam-opschoning:** Filtert achternamen en toevoegingen (zoals `(bib)` of `(eenmalig)`) weg, zodat enkel de voornaam wordt gebruikt.
*   **LukS-regel:** Vervangt alle namen die beginnen met `LukS` (case-insensitive) automatisch door `Luk`.
*   **Case-insensitive matching:** Voorkomt duplicaten in de database door hoofdletterongevoelig te zoeken naar bestaande digidokters (bijv. `daniël` wordt gekoppeld aan de bestaande `Daniël`).
*   **Duplicatenpreventie:** Slaat rijen met identieke combinaties van `(datum, uur_van, uur_tot, type_id)` automatisch over.

---

## 💻 Lokale Installatie & Setup

### 1. Omgeving voorbereiden
Zorg dat Python 3.12 geïnstalleerd is. Kloon de repository en maak een virtuele omgeving aan:

```bash
# Virtuele omgeving aanmaken
python3 -m venv venv

# Activeren
source venv/bin/activate  # Op macOS/Linux
# venv\Scripts\activate  # Op Windows

# Dependencies installeren
pip install -r requirements.txt
```

### 2. Environment Variables configureren
Maak een `.env` bestand aan in de root op basis van `.env.example`:

```env
FLASK_APP=app.py
FLASK_ENV=development
SECRET_KEY=je-geheime-sleutel
DATABASE_URL=sqlite:///digidokters.db
```

### 3. Database initialiseren & Seeden
Voer de database-migraties uit om de SQLite-database aan te maken en vul deze met standaard seed-data (organisatie, standaard keuzelijsten en beheerder):

```bash
flask db upgrade
flask seed
```

*De standaard admin-inloggegevens na seeding zijn:*
*   **Gebruikersnaam:** `PlatformAdmin`
*   **Wachtwoord:** `PlatformAdmin123!`

### 4. Applicatie starten
Start de lokale ontwikkelserver:

```bash
flask run
```
Ga naar `http://127.0.0.1:5000` in je browser.

---

## 📊 CSV Import Gebruiken

Om een CSV-bestand met historische aanwezigheden in te lezen, gebruik je het import-script. Zorg dat je virtuele omgeving actief is:

```bash
python scripts/import_agenda.py "csv/aanwezigheden Digidokters - archief aanwezigheden.csv"
```

*Je kunt optioneel een andere database-URL (`--db`) of een specifieke organisatie (`--organisatie`) als parameter meegeven:*
```bash
python scripts/import_agenda.py "pad/naar/bestand.csv" --organisatie digidokters --db "sqlite:///digidokters.db"
```

Zie de volledige [Handleiding: Agenda Import Script](file:///Users/mark/Python/Digidokters/scripts/import_agenda.md) voor meer informatie over datum- en uurformaten.

---

## 🌐 Productie & Deployment (Render.com)

Het platform is geconfigureerd om direct te deployen naar Render.com.
*   **Build-commando:** `pip install -r requirements.txt && flask db upgrade && flask seed`
*   **Start-commando:** `gunicorn app:app`
*   **Database:** PostgreSQL (Render PostgreSQL add-on). De `DATABASE_URL` omgevingsvariabele wordt door Render automatisch gekoppeld.
