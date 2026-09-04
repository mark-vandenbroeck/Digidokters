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
*   Bestandsopslagen (zoals documenten en importlogbestanden) zijn eveneens gescopeerd aan de actieve `organisatie_id` om cross-tenant toegang (IDOR) te voorkomen.

### Belangrijkste tabellen en datamodel:
1.  **Organisaties (`organisaties`):** Beheert de verschillende tenants (bijv. Londerzeel).
2.  **Gebruikers (`users`):** Beheert beheerders en medewerkers. Gekoppeld aan organisaties via `user_organisaties`. Tevens voorzien van wachtwoord-resetkolommen (`reset_code`, `reset_code_verloopt_op`).
3.  **Digidokters (`digidokters`):** Vrijwilligers binnen een specifieke organisatie.
4.  **Registraties (`registrations`):** Registratie van een cliëntbezoek met foreign keys naar digidokter, leeftijdscategorie, toestel en herkomst.
5.  **Agenda-items (`agenda_items`):** Geplande sessies met type activiteit, locatie en aanwezige digidokters.
6.  **Mappen (`mappen`):** Hiërarchische mappenstructuur per organisatie met self-referencing `parent_id`.
7.  **Documenten (`documenten`):** Bestanden (PDF, Word, Excel, afbeeldingen) opgeslagen als binaire data (`LargeBinary`) met versienummering en geïndexeerde tekstinhoud (`tekst_inhoud`).
8.  **Herkomst (`herkomst`):** Standaard keuzelijst met herkomstbronnen (bijv. website, mond-tot-mond) per organisatie.
9.  **Evaluatieformulieren & Vragen (`evaluatie_formulieren`, `evaluatie_vragen`):** Configureerbare evaluatievragenlijsten gekoppeld aan specifieke activiteitstypes (zoals Digicafé).
10. **Evaluatiereacties & Uitnodigingen (`evaluatie_reacties`, `evaluatie_uitnodigingen`):** Ingezonden antwoorden per sessie en digidokter, inclusief unieke token-gebaseerde e-mailuitnodigingen.
11. **Audit Logs (`audit_logs`):** Centraal logboek voor database-wijzigingen met details over oude en nieuwe waarden.

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
*   **Full-text zoeken (inclusief documentinhoud):** De zoekbalk doorzoekt niet alleen mappen, bestandsnamen en omschrijvingen, maar ook de volledige tekstinhoud van documenten (Word `.docx`, PDF `.pdf`, Excel `.xlsx` en tekstbestanden). Bij een inhoudsmatch toont de resultatentabel een badge *Gevonden in inhoud* met een contextfragment (snippet) rondom de zoekterm.
*   Toegang is afgeschermd voor gebruikers met de rol `lezer`.

### 5. Evaluatieformulieren voor Activiteiten & Digicafés
*   **Activiteitstype-integratie:** Activiteitstypes kunnen worden gemarkeerd met de vlag `"Evaluatieformulier gewenst"` (`heeft_evaluatie`), standaard actief voor **Digicafé**.
*   **Dynamische Vragenlijst-editor:** Beheerders kunnen per activiteitstype dynamisch een onbeperkt aantal vragen toevoegen, bewerken, van volgorde wisselen of verwijderen.
*   **Ondersteunde Vraagtypes:** Multiple choice (met configureerbare opties horizontaal gerangschikt) en vrije open tekstvelden, met optionele verplichting.
*   **Geautomatiseerde E-mailuitnodigingen & Herinneringen:** Na afloop van een sessie worden gekoppelde digidokters automatisch uitgenodigd via een unieke, beveiligde token-URL (`/evaluaties/invullen/<token>`). Beheerders kunnen uitnodigingen ook handmatig verzenden en gerichte herinneringsmails sturen naar digidokters die het formulier nog niet hebben ingevuld, inclusief visuele statusindicatoren per digidokter.
*   **Registratie:** Inzendingen registreren de specifieke digidokter, de timestamp (`ingediend_op`) en de antwoorden als JSON data, met bescherming tegen dubbel invullen.
*   **Resultatenoverzicht & Filter:** Inzage in alle reacties per activiteit met filter *"Enkel activiteiten met minstens 1 ingevulde evaluatie"* en detailinzage per sessie.

### 6. Wachtwoord Vergeten & Herstelprocedure
*   Ingebouwde herstelprocedure via het inlogscherm.
*   Gebruikers voeren hun e-mailadres in en ontvangen een 6-cijferige verificatiecode op hun e-mailadres via de Brevo HTTPS REST API.
*   De code heeft een verlooptijd van exact 30 minuten.
*   Bij invoer van de juiste code kan de gebruiker een nieuw wachtwoord instellen dat direct wordt gevalideerd op complexiteitseisen.

### 7. Database Auditing & GUI
*   Volledige auditing van alle CRUD-acties (Create, Update, Delete) via SQLAlchemy-sessielisteners.
*   Opslag van gewijzigde gegevens (oude vs. nieuwe waarden) in JSON-formaat.
*   GUI-pagina (`/beheer/audit-log`) exclusief toegankelijk voor beheerders en platformbeheerders.
*   Interactieve details-modal met duidelijke vergelijkingstabel (groen/rood) van wijzigingen.
*   Filters op datum (van-tot), gebruiker, operatie, tabel, en de switch "Toon ook logins" (inlogacties worden standaard verborgen om de loglijst overzichtelijk te houden).
*   Subtiele weergave van record-IDs in alle data-weergaven ter vereenvoudiging van auditing.

### 8. Stamgegevensbeheer & Veilig Wissen
*   **Volledig beheer van keuzelijsten:** Beheerders en platformbeheerders kunnen binnen hun organisatie locaties, activiteitstypes, leeftijdscategorieën, toestellen en herkomstbronnen aanmaken, bewerken, activeren/deactiveren en handmatig van volgorde veranderen.
*   **Referentiecontroles bij wissen:** Stamgegevens kunnen uitsluitend permanent gewist worden als er **geen enkele andere data naar verwijst**:
    *   *Locaties:* Mag niet gewist worden zolang er nog gekoppelde agenda-activiteiten zijn.
    *   *Activiteitstypes:* Mag niet gewist worden zolang er gekoppelde agenda-activiteiten of ingevulde evaluaties zijn.
    *   *Leeftijdscategorieën, Toestellen & Herkomst:* Mogen niet gewist worden zolang er nog geregistreerde consultaties aan gekoppeld zijn.
*   **Duidelijke gebruikersfeedback:** Indien een item nog in gebruik is, wordt de verwijderknop automatisch gedeactiveerd met een tooltip die het aantal gekoppelde records vermeldt. Indien ongebruikt, kan het item met één klik en bevestiging definitief worden verwijderd.

### 9. CSV Import-script (`scripts/import_agenda.py`)
Een robuust CLI-script om historische CSV-bestanden met agenda-items en aanwezigheden te importeren:
*   **Naam-opschoning:** Filtert achternamen en toevoegingen (zoals `(bib)` of `(eenmalig)`) weg, zodat enkel de voornaam wordt gebruikt.
*   **LukS-regel:** Vervangt alle namen die beginnen met `LukS` (case-insensitive) automatisch door `Luk`.
*   **Case-insensitive matching:** Voorkomt duplicaten in de database door hoofdletterongevoelig te zoeken naar bestaande digidokters (bijv. `daniël` wordt gekoppeld aan de bestaande `Daniël`).
*   **Duplicatenpreventie:** Slaat rijen met identieke combinaties van `(datum, uur_van, uur_tot, type_id)` automatisch over.

### 10. Keep-alive & Health Check (`/ping`)
*   **Health Check Endpoint:** Het endpoint `/ping` geeft simpelweg de tekst `'OK'` terug en dient om te verifiëren of de applicatie actief is.
*   **Bypass:** Dit endpoint omzeilt alle authenticatie-, autorisatie- en multi-tenancy-controles, waardoor externe monitoringtools of keep-alive scripts de app snel en zonder database-overhead kunnen controleren.
*   **Keep-alive Workflow:** Een GitHub Actions-workflow (`.github/workflows/keep-alive.yml`) roept dit endpoint elke 10 minuten aan (tussen 8u en 22u Brusselse tijd) om te voorkomen dat de gratis Render.com-instantie in slaap valt.

### 11. Platformbeheer & Organisatiebeheer
*   **Globaal Platformdashboard (`/platform/dashboard`):**
    *   *Geaggregeerde Platform-KPI's:* Direct inzicht in het totaal aantal consultaties over alle aangesloten gemeenten heen, het totaal aantal actieve vrijwilligers (inclusief unieke personen), aangesloten gemeenten en sessies.
    *   *Interactieve Visualisaties:* Chart.js staafgrafiek voor de consultatiespreiding per gemeente en doughnutgrafiek voor de verdeling van actieve vrijwilligers.
    *   *Spreidingstabel:* Volledige tabel met statusbadges, aantal consultaties, percentage-aandeel in het netwerk (met dynamische voortgangsbalken), actieve vrijwilligers, sessies en actieve koppelingen per gemeente.
    *   *Periodefilter:* Selecteerbaar kalenderjaar of totaaloverzicht ("Alle jaren").
*   **Aanpasbare E-mailsjablonen (`/platform/emailsjablonen`):**
    *   Platformbeheerders kunnen de standaardteksten en onderwerpen van uitnodigings- (`evaluatie_uitnodiging`) en herinneringsmails (`evaluatie_herinnering`) direct via de beheerinterface aanpassen.
    *   *Dynamische Placeholders:* Ondersteuning voor variabelen zoals `{naam}`, `{activiteit}`, `{datum}`, `{uur_van}`, `{uur_tot}`, `{locatie}`, `{omschrijving_blok}` en `{link}` met handige klikbare invoegbadges.
    *   *Real-time Live Preview:* Een split-screen weergave die direct toont hoe de e-mail eruitziet met realistische dummy-data.
    *   *Fabrieksherstel:* Met één klik kan elk sjabloon worden hersteld naar de standaardinstellingen.
*   **Multi-tenant Organisatiebeheer:** Platformbeheerders kunnen nieuwe organisaties toevoegen, bewerken, en gebruikers koppelen aan organisaties met specifieke rollen.
*   **Centrale Sjabloon-organisatie (`Sjabloon`):** Een speciale beschermde tenant met slug `sjabloon` dient als referentie-blauwdruk voor het hele platform.
    *   Wanneer een platformbeheerder een nieuwe gemeente of organisatie aanmaakt, worden alle actieve stamgegevens (leeftijdscategorieën, toestellen, activiteitstypes, evaluatieformulieren & vragen, locaties, herkomsten) automatisch gekopieerd uit deze Sjabloon-organisatie.
    *   Aanpassingen die de beheerder in de stamgegevens van de Sjabloon-organisatie maakt, gelden direct als de nieuwe standaard voor alle toekomstige organisaties.
*   **Organisaties Wissen met Cascading Cleanup:** Mogelijkheid om overbodige organisaties permanent te wissen (`/platform/organisaties/<id>/verwijderen`).
    *   **Veiligheid:** De hoofdorganisatie (ID 1) en de template-organisatie (`Sjabloon`) zijn permanent beschermd tegen wissen.
    *   **Volledige Cleanup:** Alle bijbehorende data (registraties, agenda-items, evaluaties, documenten, mappen, stamgegevens en gebruikerskoppelingen) wordt automatisch en geordend verwijderd.
    *   **Duidelijke Waarschuwing:** De interface toont een rode modal die expliciet waarschuwt voor de onomkeerbaarheid en de lijst van alle data die permanent verloren gaat.

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
*   **E-mailadres:** `digidokters.admin@gmail.com`
*   **Wachtwoord:** `Digidokter2024!`

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

## 🧪 Unit Tests Uitvoeren

Het platform is uitgerust met een geautomatiseerde test-suite (gebaseerd op Python's ingebouwde `unittest` framework) die draait op een in-memory SQLite database.

Om alle tests uit te voeren, run je het volgende commando vanuit de hoofdmap:
```bash
PYTHONPATH=. venv/bin/python -m unittest discover -s tests
```

---

## 🌐 Productie & Deployment (Render.com)

Het platform is geconfigureerd om direct te deployen naar Render.com.
*   **Build-commando:** `pip install -r requirements.txt && flask db upgrade && flask seed`
*   **Start-commando:** `gunicorn app:app`
*   **Database:** PostgreSQL (Render PostgreSQL add-on). De `DATABASE_URL` omgevingsvariabele wordt door Render automatisch gekoppeld.
