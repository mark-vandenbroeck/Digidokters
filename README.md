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
2.  **Gebruikers (`users`):** Beheert beheerders en medewerkers. Gekoppeld aan organisaties via `user_organisaties`. Tevens voorzien van contactgegevens (`telefoonnummer`, `email`) en wachtwoord-resetkolommen (`reset_code`, `reset_code_verloopt_op`).
3.  **Functies & Gebruiker-Functies (`functies`, `user_functies`):** Beheert vrijwilligersfuncties (bijv. Digidokter, Digihelper, Lesgever) per organisatie en de toekenning (veel-op-veel) aan gebruikers.
4.  **Genderidentiteiten (`gender_identities`):** Beheert de dynamische lijst van geslachten/genderidentiteiten (standaard 'Man', 'Vrouw') per organisatie.
5.  **Digidokters (`digidokters`):** Vrijwilligers binnen een specifieke organisatie (gekoppeld aan registraties en agenda).
6.  **Registraties (`registrations`):** Registratie van een bezoekerssessie met foreign keys naar digidokter, leeftijdscategorie, toestel, herkomst en geslacht.
7.  **Agenda-items (`agenda_items`):** Geplande sessies met type activiteit, locatie en aanwezige digidokters.
8.  **Mappen (`mappen`):** Hiërarchische mappenstructuur per organisatie met self-referencing `parent_id`.
9.  **Documenten (`documenten`):** Bestanden (PDF, Word, Excel, afbeeldingen) opgeslagen als binaire data (`LargeBinary`) met versienummering en geïndexeerde tekstinhoud (`tekst_inhoud`).
10. **Herkomst (`herkomst`):** Standaard keuzelijst met herkomstbronnen (bijv. website, mond-tot-mond) per organisatie.
11. **Evaluatieformulieren & Vragen (`evaluatie_formulieren`, `evaluatie_vragen`):** Configureerbare evaluatievragenlijsten gekoppeld aan specifieke activiteitstypes (zoals Digicafé).
12. **Evaluatiereacties & Uitnodigingen (`evaluatie_reacties`, `evaluatie_uitnodigingen`):** Ingezonden antwoorden per sessie en digidokter, inclusief unieke token-gebaseerde e-mailuitnodigingen.
13. **Audit Logs (`audit_logs`):** Centraal logboek voor database-wijzigingen met details over oude en nieuwe waarden.
14. **Feedback & Conversatie (`feedback_items`, `feedback_votes`, `feedback_comments`):** Beheer van gebruikersfeedback ("Voorstel" of "Foutje?"), stemmen met duimpjes (+1/-1), screenshot-opslag, conversatiereacties en beheerderstatus (open/afgesloten).
15. **Vraagcategorieën (`question_categories`):** Centrale lijst van 10 gestandaardiseerde hoofdcategorieën met AI-richtlijnen en actieve status.
16. **Vraagclassificaties (`question_classifications`):** 1-op-1 gekoppeld aan registraties met AI-categorietoewijzing, betrouwbaarheidsscore (zekerheid %), toelichting en handmatige override-auditering.
17. **App Mappen & App Documenten (`app_mappen`, `app_documenten`):** Centrale, platformbrede documentenopslag gedeeld door alle organisaties (zonder `organisatie_id`).

---

## 📋 Features & Functionaliteiten

### 1. Bezoekenregistratie & Balieformulier ('Nieuw bezoek')
*   **Geoptimaliseerd Balieformulier:** De optie 'Nieuw bezoek' is speciaal ontworpen voor touchscreens, tablets en drukke inloopmomenten.
*   **Sticky Sessie-Context:** Datum, actieve Digidokter en consultatielocatie blijven gedurende de hele sessie automatisch bewaard en vooraf geselecteerd.
*   **Touch Segmented Buttons:** Grote, vlot tikbare knoppen voor 'Nieuwe bezoeker (Ja/Nee)', geslacht, leeftijdscategorie en toesteltype.
*   **Snelle Onderwerp-Tags:** Met één tik populaire thema's (itsme, WhatsApp, E-mail, Smartschool, Wifi/Router) toevoegen aan de hulpvraag.
*   **Opslaan & Volgende bezoeker:** Eén opvallende actieknop slaat de consultatie op en zet het scherm direct klaar voor de volgende bezoeker.
*   **Detailpagina & AI-Inzage:** Op de detailpagina van een registratie worden alle gegevens overzichtelijk getoond, inclusief de AI-vraagclassificatie (toegewezen categorie, zekerheidsscore in % en de toelichting/motivatie van het model).
*   **Dynamische Genderidentiteit:** Het geslacht van de bezoeker wordt gekozen uit de geconfigureerde genderidentiteiten van de organisatie (standaard 'Man' en 'Vrouw', uitbreidbaar via stamgegevens).
*   **Consultatielocaties:** Indien er binnen de organisatie meerdere locaties zijn gemarkeerd als *"Gebruikt voor consultaties"*, kan de specifieke locatie direct worden geselecteerd. Bij exact één consultatielocatie wordt deze automatisch zonder extra dropdown toegekend.
*   **Realtime Asynchrone AI-classificatie:** Zodra een consultatie wordt opgeslagen of bewerkt, wordt de vraag op de achtergrond binnen 1-2 seconden geanalyseerd via Google Gemini AI en toegekend aan de passende categorie.
*   Vrijwilligers (digidokters) met de rol `medewerker` hebben ook de mogelijkheid om registraties te wissen bij invoerfouten.

### 2. Agenda & Planning
*   Ondersteunt eenmalige en terugkerende activiteiten (dagelijks, wekelijks, maandelijks) met een optionele einddatum.
*   Uur- en datumfilters (toekomstige vs. voorbije activiteiten tonen).
*   Sorteerbare kolommen op alle eigenschappen (datum, tijd, locatie, type, etc.).
*   Aanpasbare status (actief/gedeactiveerd) en badgekleur per activiteitstype (Blauw, Teal, Paars, Oranje) die direct in de agenda-lijst worden getoond.

### 3. Statistieken & Dashboard
Gepresenteerd via drie duidelijke tabbladen op de `/statistieken` pagina:
*   **Bezoekers & Consultaties:** Tijdlijn per week (jaar-op-jaar), maandelijkse verdelingen, verdeling over locaties, nieuwe vs. terugkerende bezoekers, meest populaire leeftijdscategorieën, toestellen, geslachtsverdeling en drukste dagen.
*   **Vrijwilligers & Agenda:** Totaal aantal gepresteerde uren per digidokter, sessies per locatie en activiteitstype, urentrend per maand en de **Druktest ratio** (gemiddeld aantal bezoeken per aanwezige vrijwilliger per sessie, uitsluitend berekend voor activiteiten in het verleden).
*   **Vragen & AI-Analyse:** AI-gestuurde analyse van consultaties met realtime KPI's (dekkingsgraad, populairste categorie, gemiddelde zekerheid), categorie-staafdiagram, top-5 maandelijkse evolutiegrafiek en kruistabellen per apparaat en leeftijdscategorie.
*   **Filter 'Alle jaren' & Tab-behoud:** Ondersteunt filteren per specifiek jaar én over 'Alle jaren' heen, waarbij het geopende tabblad altijd actief blijft bij filterwijzigingen.

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
*   **Volledig beheer van keuzelijsten:** Beheerders en platformbeheerders kunnen binnen hun organisatie locaties, activiteitstypes, leeftijdscategorieën, toestellen, herkomstbronnen, **genderidentiteiten** en **functies** aanmaken, bewerken, activeren/deactiveren en handmatig van volgorde veranderen.
*   **Statusfilters op alle pagina's:** Elke stamgegevens-beheerpagina bevat een handige statusfilter (*Alle items*, *Enkel actieve items*, *Enkel gedeactiveerde items*) om direct een overzichtelijk beeld te krijgen.
*   **Locaties voor Consultaties:** Locaties kunnen worden aangeduid met de optie *"Gebruikt voor consultaties"*. Enkel locaties met deze vlag verschijnen bij de registratie van consultaties en in het consultatielocatiefilter.
*   **Mapping van gedeactiveerde entries:** Gedeactiveerde leeftijdscategorieën en toesteltypes kunnen in het beheer worden gekoppeld (gemapt) naar een actieve categorie. Historische consultaties blijven intact in de database, maar worden in overzichten, filters, detailweergaven, statistieken en exports automatisch getoond en geaggregeerd onder de gemapte actieve categorie.
*   **Geavanceerde filters in het consultatieoverzicht:** De overzichtspagina van registraties bevat kolommen en filters op zoekterm, digidokter, locatie, toesteltype, geslacht, leeftijdscategorie en datum (van-tot). De dropdowns tonen enkel actieve opties; filteren op een optie matcht automatisch ook historische registraties met een gekoppelde inactieve entry.
*   **Referentiecontroles bij wissen:** Stamgegevens kunnen uitsluitend permanent gewist worden als er **geen enkele andere data naar verwijst**:
    *   *Locaties:* Mag niet gewist worden zolang er nog gekoppelde agenda-activiteiten of geregistreerde consultaties zijn.
    *   *Activiteitstypes:* Mag niet gewist worden zolang er gekoppelde agenda-activiteiten of ingevulde evaluaties zijn.
    *   *Leeftijdscategorieën, Toestellen, Herkomst & Genderidentiteiten:* Mogen niet gewist worden zolang er nog geregistreerde consultaties aan gekoppeld zijn.
    *   *Functies:* Mogen niet gewist worden zolang ze nog toegekend zijn aan één of meerdere gebruikers.
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
    *   Wanneer een platformbeheerder een nieuwe gemeente of organisatie aanmaakt, worden alle actieve stamgegevens (leeftijdscategorieën, toestellen, activiteitstypes, evaluatieformulieren & vragen, locaties, herkomsten, genderidentiteiten en functies) automatisch gekopieerd uit deze Sjabloon-organisatie.
    *   Aanpassingen die de beheerder in de stamgegevens van de Sjabloon-organisatie maakt, gelden direct als de nieuwe standaard voor alle toekomstige organisaties.
    *   **Strikte Beperking:** In de organisatie "Sjabloon" kunnen uitsluitend stamgegevens worden beheerd. Transacties zoals registraties, agenda-items, feedback, documenten en evaluaties zijn geblokkeerd om vervuiling van het standaardsjabloon te voorkomen.
*   **Organisaties Wissen met Cascading Cleanup:** Mogelijkheid om overbodige organisaties permanent te wissen (`/platform/organisaties/<id>/verwijderen`).
    *   **Veiligheid:** De hoofdorganisatie (ID 1) en de template-organisatie (`Sjabloon`) zijn permanent beschermd tegen wissen.
    *   **Volledige Cleanup:** Alle bijbehorende data (registraties, agenda-items, evaluaties, documenten, mappen, stamgegevens en gebruikerskoppelingen) wordt automatisch en geordend verwijderd.
    *   **Duidelijke Waarschuwing:** De interface toont een rode modal die expliciet waarschuwt voor de onomkeerbaarheid en de lijst van alle data die permanent verloren gaat.

### 12. Feedback & Meedenken (Foutjes & Voorstellen)
*   **Nieuwe Rubriek 'Algemeen':** In het linkermenu is een speciale rubriek `Algemeen` toegevoegd waarin zowel **Feedback** (`/feedback/`) als **Privacy & AVG** gecentraliseerd zijn.
*   **Twee Categorieën:** Gebruikers kunnen kiezen tussen **"Voorstel"** (ideeën en verbeteringen) en **"Foutje?"** (bugmelding of afwijkend gedrag).
*   **Automatische Gegevens:** De naam van de indiener en de exacte timestamp worden automatisch geregistreerd en zijn strikt niet-wijzigbaar om betrouwbaarheid te borgen.
*   **Screenshots Uploaden:** Ondersteuning voor het uploaden van schermafbeeldingen (PNG, JPG, JPEG, GIF, WEBP tot 5 MB), veilig opgeslagen als binaire data in de database (`LargeBinary`) en voorzien van een ingebouwde preview- en zoomfunctie in de detailweergave.
*   **Interactief Stemmen:** Gebruikers kunnen hun stem uitbrengen met een duim omhoog (👍) of duim omlaag (👎). Het aantal stemmen staat compact naast het betreffende icoon vermeld. Nogmaals op dezelfde duim klikken trekt de stem in; klikken op de tegenovergestelde duim past de stem aan.
*   **Conversatiedraad per Item:** Onder elk item kunnen gebruikers inhoudelijk reageren. Bij elke bijdrage worden automatisch auteur en tijdstip vastgelegd.
*   **Rolgebaseerde Rechten:**
    *   *Medewerkers & Beheerders:* Kunnen feedback indienen, stemmen en deelnemen aan de conversatie.
    *   *Lezers:* Hebben enkel leesrechten (kunnen de items en reacties raadplegen, maar kunnen niets toevoegen, stemmen of reageren).
*   **Afsluiten door Beheerders:** Beheerders kunnen een item met één klik **afsluiten** (waarna er niet meer op gestemd of gereageerd kan worden) of heropenen.
*   **Overzichtslijst:** Standaard chronologisch gesorteerd (nieuwste items bovenaan). Afgesloten items worden herkenbaar grijs getoond (*greyed out*). Snelfilters voor Alle / Open / Afgesloten, type-selectie en realtime zoekfilter.
*   **Automatisch bijhouden van weergaven (`FeedbackView`):** Het platform registreert per gebruiker het exacte tijdstip waarop de overzichtslijst (`/feedback/`) of een specifieke detailpagina (`/feedback/<id>`) voor het laatst is bekeken.
*   **Klikbare Notificatie-banners bovenaan elke pagina:**
    *   *Nieuwe reactie op eigen feedback:* Zodra een collega reageert op een door de gebruiker ingediend item, verschijnt direct bovenaan elke pagina een klikbare melding (`💬 Nieuwe reactie op uw feedback...`) met directe link naar het gesprek.
    *   *Nieuwe feedback door een collega:* Zodra een collega binnen de organisatie (of platform-breed voor platformbeheerders) een nieuw voorstel of foutje indient dat de gebruiker nog niet heeft gezien, verschijnt er een klikbare melding met een knop om het direct te bekijken.
    *   *Permanente weergave & Wegklikken:* De notificatie verdwijnt niet automatisch na enkele seconden, maar blijft permanent zichtbaar tot het betreffende item wordt geopend, of totdat de gebruiker op het sluitkruisje (`×`) klikt om de melding als gelezen te markeren.

### 13. AI-Vraaganalyse & Monitoring (Gemini AI)
*   **Automatische Real-time Classificatie:** Consultatievragen worden bij het opslaan op de achtergrond (asynchroon via daemon threads) geanalyseerd door Google Gemini AI (`gemini-2.5-flash`) en ingedeeld in 10 gestandaardiseerde hoofdcategorieën.
*   **Betrouwbaarheid & Motivatie:** Ieder resultaat bevat een zekerheidsscore (0–100%) en een motivatie/toelichting van het model.
*   **Beheer van Vraagcategorieën (`/platform/vraagcategorieen`):** Centrale lijst van categorieën met AI-richtlijnen en definities. Alleen toegankelijk voor platformbeheerders.
*   **Monitoring & Interactieve Detail-Popups (`/platform/vraagclassificaties`):** Overzichtstabel met filters op onzekere AI-scores (< 80%), organisatie en categorie. Alle rijen zijn klikbaar en openen direct een popup-modal met de volledige registratiedetails. Platformbeheerders kunnen classificaties handmatig overriden of met één klik opnieuw laten analyseren door de AI.
*   **Asynchrone Batch-analyse:** De knop "Batch-analyse starten" draait volledig asynchroon in de achtergrond met realtime statusindicatie (`/api/vraagclassificaties/batch-status`), waardoor de app direct bruikbaar blijft zonder time-outs of vastlopende webpagina's.
*   **Batch- & CLI-seeding:** Ondersteunt batchverwerking van historische consultaties via `flask seed-vragenanalyse` of de batchknop in de webinterface.

### 14. App Documentatie (Centraal & Gemeenschappelijk)
*   **Platformbrede Kennisbank (`/app-documentatie`):** Bevindt zich in de rubriek `Algemeen` tussen *Feedback* en *Privacy & AVG*.
*   **Gedeeld over alle Organisaties:** Documenten (zoals gebruikershandleidingen, security-audits en technische documentatie) worden één keer geplaatst en zijn direct beschikbaar voor alle aangesloten gemeenten.
*   **Mappen & Full-text Zoeken:** Hiërarchische mappen, documentupload tot 16 MB, inline preview (PDF/afbeeldingen), versiebeheer bij overschrijven (`v1`, `v2`...) en full-text doorzoeking van documentinhoud.
*   **Rechten:** Alle gebruikers (lezers, medewerkers, beheerders) kunnen documenten inzien en downloaden; beheeracties (uploaden, mappen, bewerken, wissen) zijn gereserveerd voor platformbeheerders.

### 15. Inklapbare Navigatie & Interface-ergonomie
*   **Inklapbare Rubrieken:** Alle rubrieken in de linker zijbalk zijn inklapbaar met geanimeerde indicators. De actieve inklapstatus wordt automatisch per gebruiker/browser bewaard in `localStorage`.
*   **Consequente 'Bezoeker'-terminologie:** Overal in formulieren, exports en statistieken is overgeschakeld op de gastvrije en AVG-conforme term "Bezoeker" (i.p.v. "Klant" of "Cliënt").
*   **Digidokter-voorselectie:** Bij een nieuw bezoek wordt de ingelogde gebruiker automatisch als actieve Digidokter ingesteld om herhaald klikwerk te vermijden.

### 16. Vrijwilligersfuncties & Zelfbediening Gebruikersprofiel
*   **Functies Stamgegevens (`/beheer/functies`):** Beheer van vrijwilligersfuncties per organisatie (standaard 'Digidokter', 'Digihelper' en 'Lesgever'). Functies kunnen worden toegevoegd, gewijzigd, geactiveerd/gedeactiveerd en gerangschikt.
*   **Toekennen aan Gebruikers:** Beheerders kunnen in het gebruikersbeheer (`/beheer/gebruikers`) één of meerdere functies toekennen aan een medewerker of beheerder, en een contacttelefoonnummer registreren.
*   **Zelfbediening via Linkeronderhoek (`/wachtwoord`):** Gebruikers kunnen door op hun naam linksonder te klikken zelf:
    *   Hun e-mailadres en contacttelefoonnummer aanpassen.
    *   De functies die ze binnen de huidige organisatie opnemen direct selecteren of aanpassen via handige selectievakjes.
    *   Optioneel hun wachtwoord wijzigen.

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
*   **AI-integratie:** Voeg in het Render Dashboard onder **Environment Variables** de variabele `GEMINI_API_KEY` toe voor automatische vraagcategorisatie via Google Gemini AI.
*   **Historische AI-seeding:** Voer eenmalig in de Render Shell `flask seed-vragenanalyse` uit om alle historische consultaties te analyseren.
