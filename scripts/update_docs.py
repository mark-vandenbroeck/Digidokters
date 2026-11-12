"""Script om documentatie bij te werken:
1. Digidokters_Gebruikershandleiding.docx
2. doc/Rollen_en_Rechten_Digidokters.docx
3. doc/Functionele_Verschillen_Release_Notes.docx
"""
import os
import docx
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import parse_xml, OxmlElement
from docx.oxml.ns import nsdecls, qn


def update_gebruikershandleiding():
    path = "Digidokters_Gebruikershandleiding.docx"
    doc = docx.Document(path)

    # 1. Update bestaande paragrafen
    for p in doc.paragraphs:
        # 2.1 Inloggen / Eerste login
        if "Bij de allereerste aanmelding met een tijdelijk wachtwoord vraagt de app u om onmiddellijk" in p.text:
            p.text = (
                "Bij de allereerste aanmelding met een door de beheerder aangemaakt tijdelijk wachtwoord vraagt de app u om onmiddellijk "
                "een nieuw, persoonlijk wachtwoord in te stellen. Uw actieve organisatie blijft hierbij automatisch bewaard, zodat u direct aan de slag kunt. "
                "Dit wachtwoord moet minstens 8 tekens bevatten, met minstens één hoofdletter en één cijfer."
            )

        # 3.1 Registraties bekijken
        elif "Het menu-item 'Registraties' toont een overzicht van alle geregistreerde" in p.text:
            p.text = (
                "Het menu-item 'Registraties' toont een overzicht van alle geregistreerde consultaties: "
                "datum, bezoeker, digidokter, nieuwe bezoeker (ja/nee), herkomst, geslacht/gender, onderwerp, resultaat van het bezoek, leeftijdscategorie en toestel. "
                "U kan de lijst doorzoeken en filteren (inclusief op resultaat). Klik op een registratie om de detailweergave te openen, inclusief het geregistreerde resultaat en de automatische AI-vraagclassificatie (toegewezen categorie, betrouwbaarheidsscore en motivatie van het taalmodel). "
                "Medewerkers en beheerders kunnen hier ook registraties verwijderen (wissen) bij invoerfouten.\n\n"
                "Filterbehoud bij navigatie: Wanneer u filters instelt en doorklikt naar de details van een registratie (via het oog-icoon) of het wijzigingsformulier (potloodje), en vervolgens terugkeert naar de lijst, blijven al uw actieve filters en zoekopdrachten behouden.\n\n"
                "Opmerking over de Digidokter-filter: Indien voor uw gebruikersgroep de restrictie 'Alleen eigen registraties tonen' is ingesteld, "
                "wordt het filterveld voor digidokters automatisch verborgen en krijgt u uitsluitend uw eigen geregistreerde consultaties te zien."
            )

        # 3.2 Een nieuw bezoek registreren
        elif "Klik in het menu op 'Nieuw bezoek' om een nieuwe registratie toe te voegen." in p.text or "Klik in het menu op 'Nieuw bezoek' om een nieuwe consultatie te registreren." in p.text:
            p.text = (
                "Klik in het menu op 'Nieuw bezoek' om een nieuwe consultatie te registreren. "
                "Dit formulier is speciaal ontworpen voor touchscreens, tablets en drukke inloopmomenten:\n"
                "• Sessie-context (bovenaan): De datum, actieve Digidokter en consultatielocatie blijven gedurende uw sessie automatisch bewaard en geselecteerd.\n"
                "• Touch-chips & grote selectieknoppen: Duidelijke knoppen voor 'Nieuwe bezoeker (Ja/Nee)', geslacht, leeftijdscategorie en toesteltype.\n"
                "• Snelle tag-knoppen: Klik met één tik op populaire thema's zoals itsme, WhatsApp, E-mail, Smartschool of Wifi om het onderwerp direct in te vullen.\n"
                "• Resultaat van het bezoek: Onder 'Hulpvraag/onderwerp' kan optioneel het resultaat van het bezoek worden aangeduid (bijv. 'Vraag beantwoord', 'Bezoeker komt later terug', 'Bezoeker doorverwezen', 'Vraag onmogelijk te beantwoorden', 'Andere'). Dit keuzeveld verschijnt automatisch zodra de organisatie minstens één resultaat heeft ingevoerd in de stamgegevens.\n"
                "• Opslaan & Volgende bezoeker: Eén grote knop slaat het bezoek direct op en zet het formulier meteen klaar voor de volgende bezoeker. "
                "Op de achtergrond start automatisch een asynchrone AI-analyse (Gemini) om de vraag in te delen in de passende categorie voor statistieken."
            )

        # 3.3 Exporteren
        elif "Via 'Exporteren' kan u alle (of gefilterde) registraties downloaden" in p.text:
            p.text = (
                "Via 'Exporteren' kan u alle (of gefilterde) registraties downloaden als Excel- (.xlsx) of CSV-bestand. "
                "U kan filteren op periode, digidokter, locatie, leeftijdscategorie, toestel, geslacht, herkomst en resultaat (indien geconfigureerd). "
                "De gedownloade tabellen bevatten gestandaardiseerde kolomkoppen (waaronder 'Bezoeker', 'Nieuwe bezoeker', 'Resultaat' en de automatische AI-'Vraagclassificatie') voor eenvoudige verwerking en verdere analyse in externe rapporten."
            )

        # 3.4 Statistieken
        elif "Onder 'Statistieken' vindt u gedetailleerde overzichten" in p.text:
            p.text = (
                "Onder 'Statistieken' vindt u gedetailleerde overzichten, KPI's en grafieken verdeeld over vier gespecialiseerde tabbladen:\n"
                "• Tab 1: Bezoekers & Consultaties: Totaal aantal consultaties, verdeling nieuwe versus terugkerende bezoekers, verdeling over consultatielocaties, leeftijdscategorieën, toestellen, herkomstkanalen, geslachtsverdeling, wekelijkse bezoekerstrends en het overzicht 'Resultaat van het bezoek' met percentages berekend over alle consultaties met een geregistreerd resultaat.\n"
                "• Tab 2: Vrijwilligers & Agenda: Totaal aantal gepresteerde uren door digidokters, maandelijkse inzet-trends, sessies per locatie en activiteitstype, en de bezoeker/vrijwilliger-ratio (druktest). Deze ratio houdt uitsluitend rekening met voorbije sessies.\n"
                "• Tab 3: Vragen & AI-Analyse: Diepgaande analyse van de geregistreerde hulpvragen via Gemini AI. Toont de dekkingsgraad (percentage geanalyseerd), de meest voorkomende vraagcategorie, gemiddelde betrouwbaarheidsscore, een categorie-staafdiagram, een maandelijkse evolutiegrafiek van de top-5 categorieën, en kruistabellen met de populairste toestellen en leeftijdsgroepen per vraagcategorie.\n"
                "• Tab 4: Activiteiten & Deelnemers: Uitgebreide statistieken over activiteiten met deelnemersregistratie. Toont het aantal unieke deelnemers, totale deelnames, gemiddelde opkomst per sessie, capaciteitsbezettingsgraad en volzette sessies, een gecombineerde tijdlijn van deelnemers en activiteiten, deelnemersretentie (eenmalig vs. terugkerend), demografische verdelingen (leeftijdscategorieën, toestellen en geografische postcodespreiding), overzichten per activiteitstype en locatie, en een recente activiteitentabel."
            )

        # 4.3 Stamgegevens beheren
        elif "Onder 'Beheer' vindt u pagina's voor 'Digidokters'" in p.text:
            p.text = (
                "Onder 'Beheer' vindt u pagina's voor 'Digidokters', 'Activiteitstypes', 'Locaties', 'Leeftijdscategorieën', 'Toestellen', 'Herkomst', 'Genderidentiteiten', 'Functies', 'Resultaten' en 'Deelnemers'. "
                "Beheerders kunnen keuzelijsten aanpassen, activeren/deactiveren, de volgorde wijzigen en ongebruikte items veilig wissen. "
                "Op elke stamgegevenspagina is tevens een statusfilter aanwezig (Alle items, Enkel actieve items, Enkel gedeactiveerde items).\n\n"
                "• Activiteitstypes & Deelnemersvlag: Bij elk activiteitstype kan de optie 'Registreer ook deelnemers' worden in- of uitgeschakeld. Dit bepaalt of voor activiteiten van dit type een deelnemerslijst en capaciteitslimiet actief zijn.\n"
                "• Deelnemersbeheer (Beheer > Deelnemers): Centraal beheer van alle geregistreerde deelnemers per organisatie. U kan zoeken op naam of postcode, filteren op status (actief/gedeactiveerd) en deelnemers toevoegen of bewerken met naam, postcode, leeftijdscategorie (LOV) en toestel (LOV).\n"
                "• Integriteitsbescherming bij wissen: Leeftijdscategorieën en toestellen kunnen niet per ongeluk worden gewist zolang deze nog gekoppeld zijn aan geregistreerde consultaties of aan deelnemers.\n"
                "• Resultaten: Bij 'Resultaten' kan worden ingesteld welke uitkomsten van een bezoek geregistreerd worden (bijv. 'Vraag beantwoord', 'Bezoeker komt later terug', 'Bezoeker doorverwezen', etc.). Indien een organisatie geen resultaten wenst te registreren, kan de lijst leeggemaakt worden, waarna het veld in het registratieformulier en de exportfilter automatisch verdwijnt."
            )

        # 3.5 Agenda & Planning
        elif p.text.startswith("Via het menu-item 'Agenda' kan u geplande activiteiten bekijken"):
            p.text = (
                "Via het menu-item 'Agenda' kan u geplande activiteiten bekijken, filteren op datum, type, locatie en digidokter, en sorteren op alle kolommen. "
                "Indien u als digidokter aanwezig was bij afgelopen activiteiten met evaluatieplicht waarvoor u nog geen evaluatie heeft ingediend, toont de Agenda bovenaan een handige attentiebanner en kunt u het formulier via de gele knop 'Evaluatie invullen' direct openen en afronden.\n\n"
                "• Filterbehoud bij bewerken & details: Wanneer u filters instelt in de agenda en doorklikt naar het detail- of wijzigingsformulier (via het potloodje) of het annuleringsscherm, en vervolgens terugkeert naar het overzicht, blijven al uw ingestelde filterwaarden intact.\n"
                "• Gelijktijdige bewerkingsvergrendeling: Om te voorkomen dat meerdere beheerders gelijktijdig hetzelfde agenda-item overschrijven, wordt een item automatisch tijdelijk vergrendeld zodra een beheerder het bewerkingsscherm opent. Indien een collega het item reeds bewerkt, toont de applicatie een duidelijke melding wie de bewerking uitvoert.\n"
                "• Deelnemersregistratie & Capaciteitsbeheer: Voor activiteitstypes waarvoor deelnemersregistratie is ingeschakeld ('Registreer ook deelnemers'), verschijnt in het agendamoment automatisch de sectie 'Geregistreerde Deelnemers'. "
                "U kunt deelnemers snel opzoeken via de realtime keuzelijst (autocomplete) of direct toevoegen via de knop 'Toevoegen' of de Enter-toets. Bij elke deelnemer worden de Naam, Postcode, Leeftijdscategorie (keuze uit de actieve categorieën) en het Toestel (keuze uit de actieve toestellen) geregistreerd. "
                "Bestaande deelnemers kunnen direct vanuit de lijst bewerkt worden via een handig pop-upvenster. "
                "Optioneel kan een maximum aantal deelnemers worden ingesteld. De applicatie bewaakt dat de capaciteit niet overschreden wordt en dat het maximum niet lager ingesteld kan worden dan het aantal reeds ingeschreven deelnemers. "
                "In de agendalijst toont een statusbadge realtime de actuele bezetting (bijv. '8 / 10 deelnemers') inclusief een opvallende '(volzet)' aanduiding zodra de activiteit volzet is."
            )

        # 3.7 Evaluatieformulieren invullen (voor Digidokters / Medewerkers)
        elif "Voor bepaalde activiteiten (zoals Digicafés) wordt na afloop gevraagd om een korte evaluatie in te vullen" in p.text:
            p.text = (
                "Voor bepaalde activiteiten (zoals Digicafés) wordt na afloop gevraagd om een korte evaluatie in te vullen:\n"
                "• Uitnodiging via e-mail: Aanwezige digidokters die in de agenda aan de activiteit zijn gekoppeld, ontvangen na afloop van de sessie automatisch een e-mail met een directe, beveiligde link om het formulier in te vullen (inloggen is via deze link niet vereist).\n"
                "• Later invullen via de App: Digidokters en medewerkers kunnen hun formulieren op elk moment via de applicatie invullen:\n"
                "  - Attentiebanner & Actieknoppen in de Agenda: Bovenaan de Agenda verschijnt een waarschuwingsbanner met het aantal openstaande evaluaties. In de lijst staat bij elke afgelopen activiteit waar u aanwezig was een gele knop 'Evaluatie invullen'.\n"
                "  - Notificatiebadge in het Menu: Naast het menu-item 'Evaluaties' toont een oranje badge het aantal nog in te vullen evaluaties voor de ingelogde gebruiker.\n"
                "  - Snelfilter op de Evaluatiepagina: Op de Evaluaties-pagina kunt u via de schakelaar 'Enkel mijn openstaande evaluaties' direct een lijst oproepen van de sessies die op uw feedback wachten.\n"
                "• Statusindicatie per activiteit: In de overzichten ziet u altijd de actuele status van een sessie ('Ingevuld', 'Nog invullen', 'Overgeslagen', 'Niet aanwezig' of 'Toekomstig').\n"
                "• Het formulier: De vragenlijst bestaat uit meerkeuzevragen (met overzichtelijke keuzerondjes naast elkaar) en vrije tekstvelden voor opmerkingen of suggesties. Uw profiel wordt automatisch herkend en reeds ingevulde formulieren kunnen niet dubbel worden ingestuurd.\n"
                "• Evaluatie overslaan: Indien een deelnemer ervoor kiest om voor een bepaalde activiteit geen evaluatie in te vullen, kan hij/zij op het formulier klikken op 'Deze evaluatie overslaan'. De activiteit wordt dan gemarkeerd als overgeslagen, de notificatiebadges en attentiebanners verdwijnen direct, en er worden geen herinneringsmails meer verstuurd."
            )

        # 4.1 Gebruikersbeheer
        elif "Via 'Beheer > Gebruikers' kunt u de medewerkers en beheerders van uw organisatie" in p.text:
            p.text = (
                "Via 'Beheer > Gebruikers' kunt u de medewerkers en beheerders van uw organisatie beheren. "
                "U kunt nieuwe accounts aanmaken met een tijdelijk wachtwoord, wachtwoorden resetten, functies toekennen (zoals Digidokter, Digihelper, Lesgever), "
                "het telefoonnummer noteren en gebruikers toewijzen aan één of meerdere autorisatiegroepen van uw organisatie. "
                "Het systeem leidt de onderliggende rol automatisch af uit de geselecteerde groepen. "
                "Wanneer een gebruiker tot meerdere groepen behoort, worden de toegekende rechten gecombineerd volgens het principe 'hoogste recht telt'."
            )

        # 4.6 Platformbeheer
        elif "• Aanpasbare e-mailsjablonen: Via 'Platformbeheer > E-mailsjablonen'" in p.text or "• Vraagclassificaties & Asynchrone Batch-analyse" in p.text or "• Koppelingen Beheren" in p.text:
            p.text = (
                "• Koppelingen Beheren & Filters: Via 'Platformbeheer > Koppelingen' kunnen gebruikerskoppelingen aan organisaties worden beheerd met flexibele filters op gebruiker (inclusief wildcards met * en ?), organisatie, groep en status. Het e-mailadres van de gebruiker is direct klikbaar om naar de bewerkfiche te springen. Nieuwe koppelingen kunnen direct worden toegewezen aan gewenste groepen.\n"
                "• Aanpasbare e-mailsjablonen: Via 'Platformbeheer > E-mailsjablonen' kunnen de standaardsjablonen voor uitnodigingen en herinneringen worden bewerkt met dynamische tags en een live preview.\n"
                "• Vraagclassificaties & Detail-popups: Onder 'Platformbeheer > Vraagclassificaties' kunnen alle AI-classificaties worden gemonitord en handmatig gecorrigeerd. Klik op een rij om direct een popup-venster met alle details van de registratie te openen. Met de knop 'Batch-analyse starten' kunnen alle ongeclassificeerde vragen asynchroon op de achtergrond worden geanalyseerd met een realtime voortgangsbalk.\n"
                "• Centrale Sjabloon-organisatie ('Sjabloon'): De organisatie 'Sjabloon' dient uitsluitend als referentie-blauwdruk voor stamgegevens en standaardgroepen. Transacties (registraties, agenda, documenten) zijn hierin uitgeschakeld om het standaardsjabloon zuiver te houden."
            )

    # 2. Hoofdstuk 4: Groepen & Permissiebeheer (Permissiematrix) toevoegen / bijwerken
    has_groepen_section = any("Groepen & Autorisatiebeheer" in p.text or "4.2 Groepen" in p.text for p in doc.paragraphs)
    if not has_groepen_section:
        stamgegevens_heading_idx = None
        for idx, p in enumerate(doc.paragraphs):
            if p.text.strip().startswith("4.2 Stamgegevens"):
                stamgegevens_heading_idx = idx
                break

        if stamgegevens_heading_idx is not None:
            target_p = doc.paragraphs[stamgegevens_heading_idx]
            target_p.insert_paragraph_before("4.2 Groepen & Autorisatiebeheer (Permissiematrix)", "Heading 2")
            target_p.insert_paragraph_before(
                "Via 'Beheer > Groepen' kunnen lokale beheerders het autorisatieschema van hun organisatie volledig op maat configureren:\n"
                "• Fijnmazige Permissiematrix: Voor elke groep kan per functionele module (Registraties, Agenda, Evaluaties, Documenten, Statistieken, Export, Feedback, Stamgegevens, Gebruikers, Groepen, Backups, Auditlogs, App documentatie) het recht worden ingesteld op 'Geen toegang', 'Alleen lezen' of 'Lezen en schrijven'.\n"
                "• Snelknoppen (Presets): Gebruik de knoppen 'Stel in als Lezer', 'Stel in als Medewerker' of 'Stel in als Beheerder' om de matrix in één klik volgens best-practice standaarden in te stellen.\n"
                "• Speciale Optie 'Alleen eigen registraties tonen': Wanneer aangevinkt, wordt de Digidokter-filterdropdown in het registratieoverzicht verborgen en ziet de gebruiker uitsluitend de consultaties die aan zijn/haar eigen Digidokter-profiel gekoppeld zijn.\n"
                "• Meervoudige Groepstoewijzing: Gebruikers kunnen aan meerdere groepen tegelijk worden gekoppeld. Het systeem past per module automatisch het hoogste recht toe (Schrijven > Lezen > Geen).\n"
                "• Beschermde Standaardgroepen: De vier standaardgroepen (Lezers, Medewerkers, Beheerders, Platformbeheerders) kunnen niet worden hernoemd of gewist. De groep 'Platformbeheerders' is bovendien permanent beschermd tegen deactivatie en inperking van rechten om te allen tijde beheer van het platform te waarborgen.",
                "Normal"
            )
            target_p.insert_paragraph_before("", "Normal")

            # Hernummer de opvolgende hoofdstukken in hoofdstuk 4
            for p in doc.paragraphs:
                if p.text.strip().startswith("4.2 Stamgegevens"):
                    p.text = "4.3 Stamgegevens beheren"
                elif p.text.strip().startswith("4.3 Evaluatieformulieren"):
                    p.text = "4.4 Evaluatieformulieren beheren & Resultaten raadplegen"
                elif p.text.strip().startswith("4.4 Backup & Restore"):
                    p.text = "4.5 Backup & Restore"
                elif p.text.strip().startswith("4.5 Audit Logs"):
                    p.text = "4.6 Audit Logs"
                elif p.text.strip().startswith("4.6 Platformbeheer"):
                    p.text = "4.7 Platformbeheer (enkel platformbeheerders)"
    else:
        # Update bestaande groepen tekst indien reeds aanwezig
        for p in doc.paragraphs:
            if "• Beschermde Standaardgroepen:" in p.text:
                p.text = (
                    "• Fijnmazige Permissiematrix: Voor elke groep kan per functionele module (Registraties, Agenda, Evaluaties, Documenten, Statistieken, Export, Feedback, Stamgegevens, Gebruikers, Groepen, Backups, Auditlogs, App documentatie) het recht worden ingesteld op 'Geen toegang', 'Alleen lezen' of 'Lezen en schrijven'.\n"
                    "• Snelknoppen (Presets): Gebruik de knoppen 'Stel in als Lezer', 'Stel in als Medewerker' of 'Stel in als Beheerder' om de matrix in één klik volgens best-practice standaarden in te stellen.\n"
                    "• Speciale Optie 'Alleen eigen registraties tonen': Wanneer aangevinkt, wordt de Digidokter-filterdropdown in het registratieoverzicht verborgen en ziet de gebruiker uitsluitend de consultaties die aan zijn/haar eigen Digidokter-profiel gekoppeld zijn.\n"
                    "• Meervoudige Groepstoewijzing: Gebruikers kunnen aan meerdere groepen tegelijk worden gekoppeld. Het systeem past per module automatisch het hoogste recht toe (Schrijven > Lezen > Geen).\n"
                    "• Beschermde Standaardgroepen: De vier standaardgroepen (Lezers, Medewerkers, Beheerders, Platformbeheerders) kunnen niet worden hernoemd of gewist. De groep 'Platformbeheerders' is bovendien permanent beschermd tegen deactivatie en inperking van rechten om te allen tijde beheer van het platform te waarborgen."
                )

    # 3. Zelfbediening 3.11 controleren
    has_311 = any("3.11" in p.text for p in doc.paragraphs)
    if not has_311:
        beheer_heading_idx = None
        for idx, p in enumerate(doc.paragraphs):
            if p.text.strip().startswith("4. Beheer"):
                beheer_heading_idx = idx
                break

        if beheer_heading_idx is not None:
            target_p = doc.paragraphs[beheer_heading_idx]
            p_h311 = target_p.insert_paragraph_before("3.11 Profielbeheer & Eigen functies instellen (Zelfbediening)", "Heading 2")
            p_t311 = target_p.insert_paragraph_before(
                "Elke aangemelde gebruiker kan te allen tijde zijn eigen profielgegevens bekijken en bijwerken door in de linkeronderhoek op zijn/haar gebruikersnaam te klikken:\n"
                "• Eigen functies kiezen: U kunt zelf eenvoudig selectievakjes aan- of uitvinken voor de functies die u opneemt binnen de huidige organisatie (bijv. Digidokter, Digihelper, Lesgever).\n"
                "• Contactgegevens bijwerken: U kunt zelf uw e-mailadres en mobiele telefoonnummer aanpassen voor interne communicatie.\n"
                "• Wachtwoord wijzigen: U kunt uw wachtwoord op elk gewenst moment veilig vernieuwen.",
                "Normal"
            )
            target_p.insert_paragraph_before("", "Normal")

    # 4. Communicatiebeheer (4.7) toevoegen / bijwerken
    has_communicatie_section = any("Communicatie & E-mails" in p.text or "4.7 Communicatie" in p.text for p in doc.paragraphs)
    if not has_communicatie_section:
        platform_heading_idx = None
        for idx, p in enumerate(doc.paragraphs):
            if "Platformbeheer" in p.text and (p.text.strip().startswith("4.6") or p.text.strip().startswith("4.7")):
                platform_heading_idx = idx
                break

        if platform_heading_idx is not None:
            target_p = doc.paragraphs[platform_heading_idx]
            target_p.insert_paragraph_before("4.7 Interne Organisatiecommunicatie & E-mails", "Heading 2")
            target_p.insert_paragraph_before(
                "Onder 'Beheer > Communicatie' kunnen beheerders gerichte e-mailberichten en updates sturen naar hun medewerkers en vrijwilligers:\n"
                "• Doelgroepselectie: Kies eenvoudig tussen 'Alle actieve gebruikers', 'Enkel beheerders' of 'Enkel medewerkers & digidokters'.\n"
                "• Dynamische waarschuwingsindicatie: De interface toont automatisch realtime welke en hoeveel actieve accounts binnen de gekozen doelgroep geen e-mailadres hebben ingesteld.\n"
                "• Proefmail naar mezelf: Met de knop 'Testmail naar mezelf' kan de beheerder het bericht eerst als proefmail ontvangen (voorzien van voorvoegsel [PROEFMAIL]) zonder dat de doelgroep of de officiële verzendhistoriek wordt belast.\n"
                "• Volledige Verzendhistoriek: Elk verzonden bericht wordt gelogd met datum, tijd, afzender, onderwerp, berichttekst en een JSON-snapshot van alle geadresseerden voor transparante opvolging.",
                "Normal"
            )
            target_p.insert_paragraph_before("", "Normal")

            # Hernummer platformbeheer naar 4.8
            for p in doc.paragraphs:
                if "Platformbeheer" in p.text and (p.text.strip().startswith("4.6") or p.text.strip().startswith("4.7")):
                    p.text = "4.8 Platformbeheer (enkel platformbeheerders)"

    doc.save(path)
    print(f"✓ {path} succesvol bijgewerkt.")


def update_rollen_en_rechten():
    path = "doc/Rollen_en_Rechten_Digidokters.docx"
    doc = docx.Document(path)

    # 1. Update inleiding en tekstparagrafen
    for p in doc.paragraphs:
        if "Binnen het platform worden vier rollen onderscheiden." in p.text:
            p.text = (
                "Binnen het platform wordt gebruik gemaakt van een configureerbaar, dynamisch Role-Based Access Control (RBAC) model per organisatie. "
                "Standaard worden vier basisgroepen voorzien (Lezers, Medewerkers, Beheerders, Platformbeheerders). Lokale beheerders kunnen daarnaast "
                "vrij extra maatwerkgroepen aanmaken met een specifieke permissiematrix per functionele module (Geen toegang, Alleen-lezen, Lezen en schrijven). "
                "Gebruikers kunnen aan meerdere groepen tegelijk worden toegewezen, waarbij altijd het meest permissieve recht ('hoogste recht wint') van kracht is."
            )
        elif "• Gebruikersbeheer: Kan accounts van medewerkers" in p.text:
            p.text = (
                "• Gebruikersbeheer: Kan accounts van medewerkers en lezers voor de eigen organisatie aanmaken, tijdelijke wachtwoorden instellen, telefoonnummers registreren, functies toekennen en gebruikers toewijzen aan één of meerdere autorisatiegroepen."
            )
        elif "• Stamgegevens: Beheert alle categorieën van de gemeente" in p.text:
            p.text = (
                "• Groepen & Permissiematrix: Beheert alle autorisatiegroepen van de organisatie en stelt per module de lees- en schrijfrechten in, inclusief opties zoals 'Alleen eigen registraties tonen'.\n"
                "• Stamgegevens: Beheert alle categorieën van de gemeente: activiteitstypes, locaties, leeftijdscategorieën, toestellen, herkomst, genderidentiteiten, functies en resultaten."
            )

    # 2. Update tabel (Table 1 has the matrix with 5 columns)
    if len(doc.tables) > 1:
        table = doc.tables[1]
        for row in table.rows:
            cells_text = [c.text.strip() for c in row.cells]
            if len(cells_text) > 0:
                if "Gebruikers beheren" in cells_text[0]:
                    row.cells[0].text = "Gebruikers beheren (Groepen, Functies & Telefoonnummers toekennen)"
                elif "Stamgegevens beheren" in cells_text[0]:
                    row.cells[0].text = "Stamgegevens beheren (Locaties, Toestellen, Herkomst, Genderidentiteiten, Functies, Resultaten)"

        # Voeg rij toe voor Groepen & Permissiematrix beheren indien nog niet aanwezig
        has_groepen_row = any("Groepen & Autorisaties" in r.cells[0].text or "Groepen beheren" in r.cells[0].text for r in table.rows if len(r.cells) > 0)
        if not has_groepen_row:
            row_g = table.add_row()
            if len(row_g.cells) >= 5:
                row_g.cells[0].text = "Groepen & Autorisatiematrix beheren (Permissies per module & restricties)"
                row_g.cells[1].text = "—"
                row_g.cells[2].text = "—"
                row_g.cells[3].text = "✓"
                row_g.cells[4].text = "✓"

    # Voeg sectie 6 toe over Dynamisch Groepenmodel indien nog niet aanwezig
    has_sec6 = any("6. Dynamisch Groepenmodel" in p.text for p in doc.paragraphs)
    if not has_sec6:
        h6 = doc.add_paragraph("6. Dynamisch Groepenmodel & Permissiematrix", "Heading 1")
        doc.add_paragraph(
            "Het autorisatieschema is volledig dynamisch en multi-tenant opgezet om tegemoet te komen aan verschillende organisatie-eisen:\n\n"
            "1. Permissieniveaus per module:\n"
            "   Voor elke module (Registraties, Agenda, Evaluaties, Documenten, Statistieken, Export, Feedback, Stamgegevens, Gebruikers, Groepen, Backups, Auditlogs, App documentatie) kan per groep het recht worden ingesteld op 'Geen toegang', 'Alleen lezen' of 'Lezen en schrijven'.\n\n"
            "2. Meervoudig groepslidmaatschap:\n"
            "   Een gebruiker kan tot meerdere groepen tegelijk behoren. Bij overlappende rechten combineert het systeem deze volgens het principe 'hoogste recht telt' (Schrijven > Lezen > Geen).\n\n"
            "3. Speciale Digidokter-restrictie ('Alleen eigen registraties tonen'):\n"
            "   Organisaties die eisen dat een digidokter enkel zijn of haar eigen consultaties kan inzien, schakelen deze optie in op de desbetreffende groep. In dat geval wordt het filterveld voor digidokters verborgen en toont het overzicht enkel de eigen consultaties.\n\n"
            "4. Beveiliging en standaardovername:\n"
            "   Standaardgroepen (Lezers, Medewerkers, Beheerders, Platformbeheerders) kunnen niet worden hernoemd of gewist. Bij het aanmaken van een nieuwe organisatie worden alle groepen en permissies automatisch gekopieerd uit de centrale Sjabloon-organisatie.",
            "Normal"
        )

    doc.save(path)
    print(f"✓ {path} succesvol bijgewerkt.")


def generate_release_notes():
    path = "doc/Functionele_Verschillen_Release_Notes.docx"
    doc = docx.Document()

    # Paginamarges
    for section in doc.sections:
        section.top_margin = Inches(1)
        section.bottom_margin = Inches(1)
        section.left_margin = Inches(1)
        section.right_margin = Inches(1)

    # Kleurenpalet
    COLOR_PRIMARY = RGBColor(29, 78, 216)    # #1d4ed8 (Blauw)
    COLOR_SECONDARY = RGBColor(71, 85, 105)  # #475569 (Slate)
    COLOR_DARK = RGBColor(15, 23, 42)        # #0f172a (Donker)

    # Titel
    p_title = doc.add_paragraph()
    run_title = p_title.add_run("Digidokters Platform — Release Notes")
    run_title.font.name = 'Calibri'
    run_title.font.size = Pt(26)
    run_title.font.bold = True
    run_title.font.color.rgb = COLOR_PRIMARY
    p_title.paragraph_format.space_after = Pt(4)

    # Subtitel
    p_sub = doc.add_paragraph()
    run_sub = p_sub.add_run("Overzicht van functionele uitbreidingen en vernieuwingen (Release 2.8.0 — Deelnemersregistratie & Capaciteitsbeheer)")
    run_sub.font.name = 'Calibri'
    run_sub.font.size = Pt(14)
    run_sub.font.italic = True
    run_sub.font.color.rgb = COLOR_SECONDARY
    p_sub.paragraph_format.space_after = Pt(18)

    # Metadata blokje
    p_meta = doc.add_paragraph()
    p_meta.paragraph_format.space_after = Pt(18)
    run_meta = p_meta.add_run(
        "Datum: November 2026   |   Versie: Release 2.8.0 (Deelnemersregistratie, Capaciteitsbeheer & Stamgegevens-integriteit)   |   Auteur: Digidokters Projectteam"
    )
    run_meta.font.size = Pt(9.5)
    run_meta.font.color.rgb = COLOR_SECONDARY

    # Inleiding
    p_intro = doc.add_paragraph()
    p_intro.paragraph_format.space_after = Pt(14)
    p_intro.add_run(
        "Dit document biedt een integraal functioneel overzicht van alle recente uitbreidingen, vernieuwingen en "
        "gebruikersverbeteringen in het Digidokters Platform. Release 2.7.0 introduceert een volledig configureerbaar "
        "dynamisch autorisatieschema per organisatie met een fijnmazige permissiematrix per module, meervoudig groepslidmaatschap "
        "met 'hoogste recht wint' conflictresolutie, de speciale Digidokter-restrictie 'Alleen eigen registraties tonen', "
        "en een geoptimaliseerde inlog- en activeringsprocedure voor nieuwe gebruikers."
    )

    def add_heading_1(text):
        h = doc.add_paragraph()
        h.paragraph_format.space_before = Pt(16)
        h.paragraph_format.space_after = Pt(6)
        r = h.add_run(text)
        r.font.name = 'Calibri'
        r.font.size = Pt(16)
        r.font.bold = True
        r.font.color.rgb = COLOR_PRIMARY
        return h

    def add_bullet(bold_prefix, text):
        p = doc.add_paragraph(style='List Bullet')
        p.paragraph_format.space_after = Pt(3)
        r_b = p.add_run(bold_prefix + ": ")
        r_b.font.bold = True
        p.add_run(text)
        return p

    # 1. Dynamisch Autorisatieschema & Permissiematrix
    add_heading_1("1. Dynamisch Autorisatieschema & Permissiematrix per Organisatie")
    p_auth = doc.add_paragraph()
    p_auth.add_run(
        "Organisaties en gemeenten kunnen nu hun eigen rollen en groepen samenstellen om nauwkeurig aan te sluiten bij hun lokale werking:"
    )
    add_bullet("Groepenbeheer", "Onder 'Beheer > Groepen' kunnen beheerders zelf groepen toevoegen, aanpassen, activeren of deactiveren.")
    add_bullet("Fijnmazige Permissiematrix", "Voor elke groep kan per module (Registraties, Agenda, Evaluaties, Documenten, Statistieken, Export, Feedback, Stamgegevens, Gebruikers, Groepen, Backups, Auditlogs, App documentatie) het niveau 'Geen toegang', 'Alleen lezen' of 'Lezen en schrijven' worden geconfigureerd.")
    add_bullet("Handige Presets", "Met één klik op 'Stel in als Lezer', 'Stel in als Medewerker' of 'Stel in als Beheerder' wordt de matrix direct volgens best practice ingevuld.")
    add_bullet("Meervoudig Groepslidmaatschap", "Gebruikers kunnen aan meerdere groepen worden gekoppeld. Het systeem past per module het meest ruime recht toe ('hoogste recht wint').")
    add_bullet("Beschermde Standaardgroepen", "De vier basisgroepen (Lezers, Medewerkers, Beheerders, Platformbeheerders) blijven beschermd tegen verwijdering en worden automatisch geseed via de Sjabloon-organisatie.")

    # 2. Speciale Restrictie: Alleen Eigen Registraties Tonen
    add_heading_1("2. Speciale Digidokter-Restrictie ('Alleen eigen registraties tonen')")
    add_bullet("Automatische Filterverberging", "Voor groepen waarin deze optie is ingeschakeld, wordt het filterveld voor digidokters in het registratieoverzicht verborgen.")
    add_bullet("Strikte Gegevensafscherming", "De consultatielijst toont uitsluitend de registraties die gekoppeld zijn aan het eigen Digidokter-profiel van de ingelogde gebruiker.")

    # 3. Geoptimaliseerde Eerste Login & Wachtwoordwissel
    add_heading_1("3. Geoptimaliseerde Eerste Login & Wachtwoordwissel")
    add_bullet("Naadloze Organisatiekoppeling", "Wanneer een nieuwe gebruiker inlogt met een tijdelijk wachtwoord en moet wisselen van wachtwoord, blijft de organisatiecontext behouden zodat er nooit een foutmelding over een inactieve organisatie optreedt.")

    # 4. In-App Evaluatieformulieren & Notificaties
    add_heading_1("4. In-App Evaluatieformulieren & Notificaties")
    add_bullet("Attentiebanner & Actieknop in Agenda", "Bovenaan de Agenda verschijnt een waarschuwingsbanner met het aantal openstaande evaluaties en directe actieknoppen.")
    add_bullet("Menu-notificatiebadge", "Een oranje teller naast 'Evaluaties' toont realtime het aantal nog in te vullen formulieren.")
    add_bullet("Snelfilter 'Enkel mijn openstaande evaluaties'", "Met één klik filteren op sessies die op feedback wachten.")

    # 5. Balie-Registratieformulier ('Nieuw bezoek') & AI-Classificatie
    add_heading_1("5. Geoptimaliseerd Balie-Registratieformulier ('Nieuw bezoek')")
    add_bullet("Sticky Sessie-Context", "Datum, actieve Digidokter en consultatielocatie blijven bewaard gedurende het inloopmoment.")
    add_bullet("Touch-Chips & Onderwerp-Tags", "Grote knoppen en snelle tag-knoppen (itsme, WhatsApp, E-mail, Smartschool, Wifi).")
    add_bullet("Asynchrone AI-Vraaganalyse", "Automatische categorietoewijzing via Gemini AI op de achtergrond zonder browser-blokkering.")

    # 6. Interne Organisatiecommunicatie & Broadcast E-mails
    add_heading_1("6. Interne Organisatiecommunicatie & E-mail Berichten")
    add_bullet("Doelgroepselectie", "Beheerders kunnen berichten sturen naar 'Alle actieve gebruikers', 'Enkel beheerders' of 'Enkel medewerkers & digidokters'.")
    add_bullet("Dynamische Validatie", "Realtime indicatie van accounts zonder e-mailadres per gekozen doelgroep.")
    add_bullet("Proefmail-functie", "Veilig testen via 'Testmail naar mezelf' met automatisch voorvoegsel [PROEFMAIL].")
    add_bullet("Verzendhistoriek & Audit", "Volledig overzicht van verzonden communicatie met datum, afzender, onderwerp, inhoud en JSON-snapshot van alle ontvangers.")

    # 7. Waarborging Platformcontinuïteit & Uitfaseren Organisatierol
    add_heading_1("7. Waarborging Platformcontinuïteit & Autorisatie-optimalisatie")
    add_bullet("Uitfaseren Legacy Organisatierol", "Alle autorisaties en moduletoegang zijn nu 100% gekoppeld aan de dynamische Groepen & Rechten permissiematrix.")
    add_bullet("Bescherming Laatste Platformbeheerder", "De allerlaatste actieve platformbeheerder is beschermd tegen per ongeluk uitschakelen of verwijderen via zowel UI-vergrendeling als server-side validatie.")

    # 8. Deelnemersregistratie & Capaciteitsbeheer bij Activiteiten
    add_heading_1("8. Deelnemersregistratie & Capaciteitsbeheer bij Activiteiten")
    add_bullet("Activiteitstypes met Deelnemersvlag", "Voor workshops, themasessies of groepscursussen kan de optie 'Registreer ook deelnemers' worden ingeschakeld op het activiteitstype.")
    add_bullet("Deelnemersgegevens (Postcode, Leeftijdscategorie & Toestel)", "Per deelnemer worden naam, postcode, leeftijdscategorie (LOV) en toestel (LOV) geregistreerd en met compacte badges weergegeven.")
    add_bullet("Realtime Zoeken & Snelle Toevoegmodal", "In het agendamoment kunnen deelnemers direct via de zoekbalk (autocomplete) worden gekoppeld of met één klik / Enter nieuw worden aangemaakt of bewerkt via een naadloze pop-up modal.")
    add_bullet("Capaciteitslimiet & Volzet-indicatie", "Optioneel instellen van een maximum aantal deelnemers. Het systeem bewaakt dat de capaciteit niet wordt overschreden en toont een opvallende '(volzet)' indicator.")
    add_bullet("Integriteitsbescherming Stamgegevens", "Leeftijdscategorieën en toestellen kunnen niet per ongeluk worden gewist zolang deze nog aan geregistreerde consultaties of deelnemers zijn gekoppeld.")
    add_bullet("Volledig Deelnemersbeheer (CRUD)", "Centraal overzicht onder 'Beheer > Deelnemers' met zoekfunctie op naam en postcode, actieve status en wijzigingsmogelijkheden.")

    # 9. Samenvatting per rol
    add_heading_1("9. Samenvatting: Impact per Gebruikersrol")
    table = doc.add_table(rows=1, cols=3)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.style = 'Table Grid'

    hdr_cells = table.rows[0].cells
    hdr_cells[0].text = "Gebruikersrol / Groep"
    hdr_cells[1].text = "Wat is er nieuw / gewijzigd?"
    hdr_cells[2].text = "Voordeel in de praktijk"
    for cell in hdr_cells:
        cell.paragraphs[0].runs[0].font.bold = True
        shading = parse_xml(f'<w:shd {nsdecls("w")} w:fill="E2E8F0"/>')
        cell._tc.get_or_add_tcPr().append(shading)

    rol_data = [
        ("Medewerker / Digidokter",
         "• Deelnemers registreren met postcode, leeftijd en toestel, en capaciteit opvolgen bij workshops.\n"
         "• Ontvangen van interne organisatie-updates en mededelingen via e-mail.\n"
         "• Optioneel enkel eigen registraties inzien (geen storende filter).\n"
         "• Evaluaties direct via de app afronden met attentiebanner en badges.\n"
         "• Nieuw balieformulier en zelf functies/telefoonnummer beheren.",
         "Duidelijk overzicht van wie deelneemt aan workshops, altijd direct op de hoogte van updates en optimale touchscreen-ervaring."),
        ("Beheerder (Gemeente)",
         "• Volledig beheer van deelnemers per organisatie via Beheer > Deelnemers.\n"
         "• Activiteitstypes configureren met deelnemersregistratie en capaciteitsbewaking.\n"
         "• Verzenden van interne mededelingen met doelgroepfilter, proefmail en historiek.\n"
         "• Volledig beheer van autorisatiegroepen en permissiematrix per module.\n"
         "• Toewijzen van gebruikers aan meerdere groepen tegelijk.",
         "Optimale opvolging van workshops en cursussen, betrouwbare capaciteitsbewaking en maximale flexibiliteit in rollen en rechten."),
        ("Platformbeheerder",
         "• Platformbrede aankondigingen sturen naar alle aangesloten beheerders.\n"
         "• Automatische overname van standaardgroepen via Sjabloon bij nieuwe gemeenten.\n"
         "• Gegarandeerde platformcontinuïteit door bescherming van de laatste superuser.",
         "Centraal beheer, efficiënte communicatie naar alle gemeenten en gewaarborgde beheercontinuïteit.")
    ]

    for rol, nieuw, voordeel in rol_data:
        row = table.add_row()
        row.cells[0].text = rol
        row.cells[0].paragraphs[0].runs[0].font.bold = True
        row.cells[1].text = nieuw
        row.cells[2].text = voordeel

    for row in table.rows:
        for cell in row.cells:
            for p in cell.paragraphs:
                p.paragraph_format.space_after = Pt(2)
                p.paragraph_format.space_before = Pt(2)

    doc.save(path)
    print(f"✓ {path} succesvol aangemaakt.")


if __name__ == "__main__":
    print("Starten met bijwerken van documenten...")
    update_gebruikershandleiding()
    update_rollen_en_rechten()
    generate_release_notes()
    print("✓ Alle documenten zijn verwerkt!")
