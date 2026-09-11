"""
AI-gebaseerde vraagclassificatie voor Digidokters met Google Gemini.
Ondersteunt automatische categorisatie, batchverwerking en retroactieve seeding.
"""

import os
import json
import time
import certifi
import requests
from datetime import datetime, timezone
from extensions import db
from models.question_category import QuestionCategory
from models.question_classification import QuestionClassification
from models.registration import Registration

STANDAARD_CATEGORIEEN = [
    {
        "naam": "Communicatie & Sociale Media",
        "omschrijving": "Vragen over WhatsApp, E-mail, Gmail, Outlook, SMS, Facebook, Messenger, contactenlijst, videobellen."
    },
    {
        "naam": "Itsme, Inloggen & Accounts",
        "omschrijving": "Itsme installeren of heractiveren, wachtwoorden vergeten, Apple ID, Google-account, tweestapsverificatie, pincodes."
    },
    {
        "naam": "Digitale Veiligheid & Privacy",
        "omschrijving": "Spam, phishing mails/berichten, virusmeldingen, verdachte telefoons, antivirus, privacy-instellingen, blokkeren."
    },
    {
        "naam": "Opslag, Foto's & Back-up",
        "omschrijving": "Google Foto's, iCloud, foto's overzetten naar pc/USB, opslagruimte vol meldingen, back-up maken."
    },
    {
        "naam": "Nieuw Toestel & Basisinrichting",
        "omschrijving": "Nieuwe smartphone of laptop opstarten, gegevens overzetten van oud naar nieuw toestel, apps downloaden/verwijderen."
    },
    {
        "naam": "Toestel, Hardware & Instellingen",
        "omschrijving": "Wi-Fi en netwerk, printerinstellingen, scherm/geluid, batterij, trage computer, algemene apparaatinstellingen."
    },
    {
        "naam": "Overheid, Gezondheid & Administratie",
        "omschrijving": "MyMinfin, my eBox, pensioenaanvraag, mutualiteit (CM/Solidaris/Helan), doktersvoorschriften, burgerprofiel, eID."
    },
    {
        "naam": "Bankieren & Online Betalen",
        "omschrijving": "Bankapps (KBC, Belfius, BNP, ING), Payconiq, online betalen met QR-code, kaartlezer."
    },
    {
        "naam": "Media, Ontspanning & Mobiliteit",
        "omschrijving": "VRT MAX, VTM GO, YouTube, muziekapps (Spotify/Deezer), NMBS, De Lijn, Google Maps, online tickets."
    },
    {
        "naam": "Overig / Niet-digitaal",
        "omschrijving": "Vragen buiten de digitale scope, telecomabonnementen (Proximus/Telenet facturen), doorverwijzing naar externe hersteldienst."
    }
]


def seed_standaard_categorieen():
    """Zorg ervoor dat de standaard categorieën in de database aanwezig zijn."""
    toegevoegd = 0
    for idx, item in enumerate(STANDAARD_CATEGORIEEN, start=1):
        bestaand = QuestionCategory.query.filter_by(naam=item["naam"]).first()
        if not bestaand:
            cat = QuestionCategory(
                naam=item["naam"],
                omschrijving=item["omschrijving"],
                volgorde=idx,
                actief=True
            )
            db.session.add(cat)
            toegevoegd += 1
    if toegevoegd > 0:
        db.session.commit()
    return toegevoegd


def classificeer_vragen_batch(items_lijst):
    """
    Classificeer een lijst met items: [{'id': reg_id, 'tekst': onderwerp}, ...]
    Gebruikt de actieve categorieën uit de database.
    """
    if not items_lijst:
        return []

    gemini_api_key = os.getenv("GEMINI_API_KEY")
    if not gemini_api_key:
        raise ValueError("GEMINI_API_KEY ontbreekt in de omgevingsvariabelen.")

    # Haal actieve categorieën op uit de database
    categorieen = QuestionCategory.query.filter_by(actief=True).order_by(QuestionCategory.volgorde.asc()).all()
    if not categorieen:
        seed_standaard_categorieen()
        categorieen = QuestionCategory.query.filter_by(actief=True).order_by(QuestionCategory.volgorde.asc()).all()

    categorie_instructie = "\n".join([f"- **{c.naam}**: {c.omschrijving}" for c in categorieen])
    items_json = json.dumps(items_lijst, ensure_ascii=False)

    prompt = f"""Je bent een behulpzame AI-assistent voor 'Digidokters' (een organisatie waar vrijwilligers burgers helpen met digitale vragen).
Hieronder staan een aantal hulpvragen van bezoekers ('onderwerp').

Jouw taak is om voor ELKE vraag de meest passende categorie te kiezen uit deze lijst:
{categorie_instructie}

Geef je antwoord UITSLUITEND als een geldige JSON-array terug met de volgende structuur:
[
  {{
    "id": 0,
    "categorie": "Exacte categorienaam uit de lijst",
    "zekerheid": 0.95,
    "toelichting": "Korte motivatie in maximaal 1 zin"
  }}
]

Te classificeren onderwerpen:
{items_json}
"""

    modellen_om_te_proberen = ["gemini-3.5-flash", "gemini-3.1-flash-lite", "gemini-3.6-flash"]
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "responseMimeType": "application/json"
        }
    }

    laatste_fout = None
    gekozen_model = None
    resultaten = None

    for model_naam in modellen_om_te_proberen:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_naam}:generateContent?key={gemini_api_key}"
        try:
            resp = requests.post(url, json=payload, verify=certifi.where(), timeout=45)
            if resp.status_code == 200:
                data = resp.json()
                raw_text = data['candidates'][0]['content']['parts'][0]['text'].strip()
                
                # Extraheer JSON array veilig
                start_idx = raw_text.find('[')
                end_idx = raw_text.rfind(']')
                if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                    raw_text = raw_text[start_idx:end_idx + 1]

                resultaten = json.loads(raw_text)
                gekozen_model = model_naam
                break
            elif resp.status_code in (503, 429):
                laatste_fout = f"HTTP {resp.status_code} op {model_naam}: {resp.text}"
                continue
            else:
                raise Exception(f"Gemini API fout ({resp.status_code}) op {model_naam}: {resp.text}")
        except requests.exceptions.RequestException as e:
            laatste_fout = f"Verbindingsfout op {model_naam}: {e}"
            continue

    if resultaten is None:
        raise Exception(f"Alle Gemini modellen faalden: {laatste_fout}")

    # Map categorienaam naar categorie_id
    cat_map = {c.naam.lower().strip(): c.id for c in categorieen}

    verwerkte_resultaten = []
    for res in resultaten:
        item_id = res.get("id")
        cat_naam = res.get("categorie", "").strip()
        cat_id = cat_map.get(cat_naam.lower(), None)
        zekerheid = float(res.get("zekerheid", 0.0))
        toelichting = res.get("toelichting", "")

        verwerkte_resultaten.append({
            "registration_id": item_id,
            "category_id": cat_id,
            "categorie_naam": cat_naam,
            "zekerheid": zekerheid,
            "toelichting": toelichting,
            "model_naam": gekozen_model
        })

    return verwerkte_resultaten


def seed_retroactieve_classificaties(batch_size=25, progress_callback=None):
    """
    Classificeer alle registraties met een onderwerp die nog GEEN QuestionClassification hebben.
    """
    seed_standaard_categorieen()

    # Zoek alle registraties zonder classificatie
    query = (
        Registration.query
        .outerjoin(QuestionClassification, Registration.id == QuestionClassification.registration_id)
        .filter(QuestionClassification.id.is_(None))
        .filter(Registration.onderwerp.isnot(None))
        .filter(Registration.onderwerp != '')
        .order_by(Registration.id.asc())
    )

    totaal_te_doen = query.count()
    if totaal_te_doen == 0:
        return 0, 0

    alle_registraties = query.all()
    totaal_verwerkt = 0
    totaal_fouten = 0

    for i in range(0, len(alle_registraties), batch_size):
        chunk = alle_registraties[i:i + batch_size]
        items_payload = [{"id": r.id, "tekst": r.onderwerp} for r in chunk]

        try:
            classificaties = classificeer_vragen_batch(items_payload)
            for item in classificaties:
                reg_id = item["registration_id"]
                cat_id = item["category_id"]
                zekerheid = item["zekerheid"]
                toelichting = item["toelichting"]
                model_naam = item["model_naam"]

                # Maak of update classificatie
                cls_obj = QuestionClassification.query.filter_by(registration_id=reg_id).first()
                if not cls_obj:
                    cls_obj = QuestionClassification(
                        registration_id=reg_id,
                        category_id=cat_id,
                        zekerheid=zekerheid,
                        toelichting=toelichting,
                        model_naam=model_naam,
                        is_handmatig_aangepast=False,
                        geclassificeerd_op=datetime.now(timezone.utc)
                    )
                    db.session.add(cls_obj)
                else:
                    if not cls_obj.is_handmatig_aangepast:
                        cls_obj.category_id = cat_id
                        cls_obj.zekerheid = zekerheid
                        cls_obj.toelichting = toelichting
                        cls_obj.model_naam = model_naam
                        cls_obj.geclassificeerd_op = datetime.now(timezone.utc)

            db.session.commit()
            totaal_verwerkt += len(chunk)

            if progress_callback:
                progress_callback(totaal_verwerkt, totaal_te_doen)

            # Korte pauze tussen batches om rate limits te vermijden
            time.sleep(0.5)

        except Exception as e:
            db.session.rollback()
            totaal_fouten += len(chunk)
            print(f"Fout bij verwerken van batch {i}-{i+len(chunk)}: {e}")

    return totaal_verwerkt, totaal_fouten


def classificeer_enkele_registratie(registration_id):
    """Heranalyseer één registratie met Gemini."""
    reg = db.session.get(Registration, registration_id)
    if not reg or not reg.onderwerp:
        return None

    res_lijst = classificeer_vragen_batch([{"id": reg.id, "tekst": reg.onderwerp}])
    if not res_lijst:
        return None

    res = res_lijst[0]
    cls_obj = QuestionClassification.query.filter_by(registration_id=reg.id).first()
    if not cls_obj:
        cls_obj = QuestionClassification(
            registration_id=reg.id,
            category_id=res["category_id"],
            zekerheid=res["zekerheid"],
            toelichting=res["toelichting"],
            model_naam=res["model_naam"],
            is_handmatig_aangepast=False,
            geclassificeerd_op=datetime.now(timezone.utc)
        )
        db.session.add(cls_obj)
    else:
        cls_obj.category_id = res["category_id"]
        cls_obj.zekerheid = res["zekerheid"]
        cls_obj.toelichting = res["toelichting"]
        cls_obj.model_naam = res["model_naam"]
        cls_obj.is_handmatig_aangepast = False
        cls_obj.geclassificeerd_op = datetime.now(timezone.utc)

    db.session.commit()
    return cls_obj


def trigger_asynchrone_classificatie(registration_id, app=None):
    """
    Start een achtergrond-thread om een registratie asynchroon te classificeren met Gemini.
    Vertraagt de web-request niet en vangt eventuele fouten geruisloos op.
    """
    import threading
    from flask import current_app

    if app is None:
        try:
            app = current_app._get_current_object()
        except RuntimeError:
            return None

    if app.config.get('TESTING') and not app.config.get('ENABLE_ASYNC_CLASSIFIER_TEST'):
        return None

    def _async_worker():
        with app.app_context():
            try:
                classificeer_enkele_registratie(registration_id)
            except Exception as e:
                app.logger.warning(f"Asynchrone classificatie mislukt voor registratie {registration_id}: {e}")

    thread = threading.Thread(target=_async_worker, daemon=True)
    thread.start()
    return thread
