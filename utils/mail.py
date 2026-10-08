import json
import os
import smtplib
import traceback
import urllib.request
from datetime import datetime
from email.mime.text import MIMEText
from flask import current_app, request
from flask_login import current_user

def verstuur_email(ontvangers, onderwerp, inhoud_tekst, bijlagen=None):
    """
    Verstuurt een e-mail naar één of meerdere ontvangers.
    Ondersteunt optionele bijlagen (lijst van dicts met {'path': str, 'naam': str}).
    Ondersteunt zowel de Brevo HTTPS REST API (werkt op Render.com poort 443) als SMTP fallback.
    """
    import base64
    from email.mime.multipart import MIMEMultipart
    from email.mime.base import MIMEBase
    from email import encoders

    if isinstance(ontvangers, str):
        ontvangers = [ontvangers]

    smtp_sender = os.environ.get('SMTP_SENDER') or os.environ.get('MAIL_DEFAULT_SENDER', 'digidokters@gmail.com')
    brevo_api_key = os.environ.get('BREVO_API_KEY') or os.environ.get('BREVO_KEY')
    
    smtp_username = os.environ.get('SMTP_USERNAME') or os.environ.get('MAIL_USERNAME')
    smtp_password = os.environ.get('SMTP_PASSWORD') or os.environ.get('MAIL_PASSWORD')
    
    # Als de wachtwoord of username een Brevo API sleutel is (begint met xkeysib-), gebruik die automatisch als API key
    if not brevo_api_key and smtp_password and smtp_password.startswith('xkeysib-'):
        brevo_api_key = smtp_password
    elif not brevo_api_key and smtp_username and smtp_username.startswith('xkeysib-'):
        brevo_api_key = smtp_username

    # 1. Probeer Brevo HTTPS REST API (Poort 443 - immuun voor Render outbound port blocks)
    if brevo_api_key:
        try:
            url = "https://api.brevo.com/v3/smtp/email"
            headers = {
                "accept": "application/json",
                "api-key": brevo_api_key,
                "content-type": "application/json"
            }
            payload = {
                "sender": {"email": smtp_sender, "name": "Digidokters"},
                "to": [{"email": r} for r in ontvangers],
                "subject": onderwerp,
                "textContent": inhoud_tekst
            }
            
            if bijlagen:
                payload["attachment"] = []
                for b in bijlagen:
                    content_b64 = None
                    if b.get('content_bytes'):
                        content_b64 = base64.b64encode(b['content_bytes']).decode('utf-8')
                    elif b.get('path') and os.path.exists(b['path']):
                        with open(b['path'], 'rb') as f:
                            content_b64 = base64.b64encode(f.read()).decode('utf-8')

                    if content_b64:
                        payload["attachment"].append({
                            "content": content_b64,
                            "name": b.get('naam', 'bijlage')
                        })
                        
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(url, data=data, headers=headers, method='POST')
            with urllib.request.urlopen(req, timeout=10) as resp:
                res = json.loads(resp.read().decode('utf-8'))
                msg_id = res.get('messageId', 'OK')
                return True, f"Succesvol verzonden via Brevo HTTPS API! (ID: {msg_id})"
        except urllib.error.HTTPError as http_err:
            err_body = http_err.read().decode('utf-8')
            raise Exception(f"Brevo API Fout ({http_err.code}): {err_body}")
        except Exception as api_err:
            # Als er geen SMTP server ingesteld is, gooi dan de API fout
            if not (os.environ.get('SMTP_SERVER') or os.environ.get('MAIL_SERVER')):
                raise Exception(f"Brevo HTTPS API Fout: {str(api_err)}")

    # 2. SMTP Fallback
    smtp_server = os.environ.get('SMTP_SERVER') or os.environ.get('MAIL_SERVER', 'smtp-relay.brevo.com')
    smtp_port = int(os.environ.get('SMTP_PORT') or os.environ.get('MAIL_PORT', '587'))

    if not smtp_username or not smtp_password:
        raise Exception(f"Geen SMTP of Brevo API instellingen geconfigureerd (Server: {smtp_server}). Stel BREVO_API_KEY of SMTP_USERNAME/SMTP_PASSWORD in.")

    if bijlagen:
        msg = MIMEMultipart()
        msg['Subject'] = onderwerp
        msg['From'] = smtp_sender
        msg['To'] = ", ".join(ontvangers)
        
        msg.attach(MIMEText(inhoud_tekst, 'plain', 'utf-8'))
        
        for b in bijlagen:
            raw_bytes = None
            if b.get('content_bytes'):
                raw_bytes = b['content_bytes']
            elif b.get('path') and os.path.exists(b['path']):
                with open(b['path'], 'rb') as f:
                    raw_bytes = f.read()

            if raw_bytes is not None:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(raw_bytes)
                encoders.encode_base64(part)
                filename = b.get('naam', 'bijlage')
                part.add_header('Content-Disposition', f'attachment; filename="{filename}"')
                msg.attach(part)
    else:
        msg = MIMEText(inhoud_tekst, 'plain', 'utf-8')
        msg['Subject'] = onderwerp
        msg['From'] = smtp_sender
        msg['To'] = ", ".join(ontvangers)

    if smtp_port == 465:
        server = smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=10)
    else:
        server = smtplib.SMTP(smtp_server, smtp_port, timeout=10)
        server.starttls()

    server.login(smtp_username, smtp_password)
    server.sendmail(smtp_sender, ontvangers, msg.as_string())
    server.quit()
    return True, f"Succesvol verzonden via SMTP ({smtp_server}:{smtp_port})!"


def stuur_fout_email(error_code, error_message, exception=None):
    """
    Stuurt een gedetailleerde e-mail naar alle platformbeheerders met een ingevuld e-mailadres.
    """
    from models.user import User
    
    try:
        # 1. Vind platformbeheerders met ingevuld e-mailadres
        platform_admins = User.query.filter(
            User.rol == 'platformbeheerder',
            User.email.isnot(None),
            User.email != ''
        ).all()
        ontvangers = [admin.email for admin in platform_admins]
        
        if not ontvangers:
            current_app.logger.warning("Geen platformbeheerders met ingevuld e-mailadres gevonden om foutmail te sturen.")
            return
            
        # 2. Bouw e-mail details
        url = request.url
        method = request.method
        ip = request.remote_addr
        user_agent = request.headers.get('User-Agent', 'Onbekend')
        
        user_str = "Niet ingelogd"
        if current_user and current_user.is_authenticated:
            user_str = f"{current_user.naam} (ID: {current_user.id}, Rol: {current_user.rol})"
            
        from flask import session
        org_id = session.get('organisatie_id', 'Geen')
        
        trace_str = ""
        if exception and exception.__traceback__:
            trace_str = f"\n\nStack Trace:\n{''.join(traceback.format_exception(type(exception), exception, exception.__traceback__))}"
        else:
            current_tb = traceback.format_exc()
            if "NoneType: None" not in current_tb and "None" not in current_tb.strip():
                trace_str = f"\n\nStack Trace:\n{current_tb}"
            
        mail_body = f"""Beste platformbeheerder,

Er heeft zich een fout voorgedaan in de Digidokters-applicatie.

--- DETAILS ---
Foutcode: {error_code}
Bericht: {error_message}
Tijdstip: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

--- CONTEXT ---
URL: {method} {url}
IP-adres: {ip}
User-Agent: {user_agent}
Gebruiker: {user_str}
Actieve Organisatie ID: {org_id}
{trace_str}

Met vriendelijke groet,
Digidokters Systeem
"""
        
        success, msg = verstuur_email(ontvangers, f"[Digidokters Alert] Fout {error_code} opgetreden", mail_body)
        current_app.logger.info(f"Foutmail: {msg} (naar {ontvangers})")
    except Exception as mail_ex:
        current_app.logger.error(f"Fout bij het genereren of verzenden van de foutmail: {str(mail_ex)}")


def stuur_welkomst_email(gebruiker_email, gebruiker_naam, tijdelijk_wachtwoord=None, organisatie_id=None):
    """
    Stuurt een welkomstmail naar een nieuwe gebruiker met logininstructies en de handleiding als bijlage.
    Gebruikt het dynamische e-mailsjabloon 'welkomstmail' van de betreffende organisatie (of platform default).
    """
    if not gebruiker_email:
        return False, "Geen e-mailadres opgegeven."

    if organisatie_id is None:
        try:
            from utils.tenant import get_huidige_organisatie_id
            organisatie_id = get_huidige_organisatie_id()
        except Exception:
            organisatie_id = None

    wachtwoord_blok = ""
    if tijdelijk_wachtwoord:
        wachtwoord_blok = f"\nJe tijdelijke wachtwoord is: {tijdelijk_wachtwoord}\nJe dient dit wachtwoord bij de eerste login onmiddellijk te wijzigen.\n"
    else:
        wachtwoord_blok = "\nJe kunt inloggen met de inloggegevens die door je beheerder aan jou zijn verstrekt.\n"

    try:
        from flask import request, has_request_context
        if has_request_context():
            login_url = request.host_url.rstrip('/')
        else:
            login_url = "https://digidokters.onrender.com"
    except Exception:
        login_url = "https://digidokters.onrender.com"

    context = {
        'naam': gebruiker_naam or 'gebruiker',
        'email': gebruiker_email,
        'login_url': login_url,
        'wachtwoord_blok': wachtwoord_blok,
        'contact_email': 'digidokters.admin@gmail.com'
    }

    onderwerp = "Welkom bij Digidokters!"
    inhoud = f"""Beste {gebruiker_naam},

Welkom bij de Digidokters-applicatie!

Er is een nieuw account voor jou aangemaakt. Je kunt de applicatie bereiken via onderstaande URL:
{login_url}

Je inloggegevens:
E-mailadres: {gebruiker_email}
{wachtwoord_blok}
Als bijlage sturen we je alvast de gebruikershandleiding mee. Hierin vind je een duidelijke uitleg over het gebruik van de applicatie (zoals het registreren van bezoeken, de agenda en documentbeheer).

Mocht je vragen of problemen hebben, neem dan gerust contact op met de beheerder via digidokters.admin@gmail.com.

Met vriendelijke groet,
Digidokters Team
"""

    try:
        from models.email_template import EmailTemplate
        tpl = EmailTemplate.get_template_voor_organisatie('welkomstmail', organisatie_id)
        if tpl:
            onderwerp, inhoud = tpl.render(context)
    except Exception as e:
        current_app.logger.warning(f"Kon e-mailsjabloon welkomstmail niet laden: {str(e)}")

    # Haal de actuele gebruikershandleiding op uit AppDocumenten (App documentatie -> Gebruikershandleidingen)
    bijlagen = []
    handleiding_doc = None
    try:
        from models.app_document import AppDocument, AppFolder
        # Zoek eerst in map 'Gebruikershandleidingen' naar Digidokters_Gebruikershandleiding.docx
        handleiding_doc = (
            AppDocument.query
            .join(AppFolder, AppDocument.map_id == AppFolder.id)
            .filter(
                AppFolder.naam.ilike('%gebruiker%'),
                AppDocument.bestandsnaam.ilike('%Digidokters_Gebruikershandleiding%')
            )
            .order_by(AppDocument.gewijzigd_op.desc())
            .first()
        )
        if not handleiding_doc:
            # Fallback op bestandsnaam binnen globale AppDocumenten
            handleiding_doc = (
                AppDocument.query
                .filter(AppDocument.bestandsnaam.ilike('%Digidokters_Gebruikershandleiding%'))
                .order_by(AppDocument.gewijzigd_op.desc())
                .first()
            )
    except Exception as doc_ex:
        current_app.logger.warning(f"Fout bij ophalen handleiding uit AppDocumenten: {str(doc_ex)}")

    if handleiding_doc and handleiding_doc.inhoud:
        bijlagen.append({
            'naam': handleiding_doc.bestandsnaam,
            'content_bytes': handleiding_doc.inhoud
        })
    else:
        # Fallback op bestand op schijf
        handleiding_pad = os.path.join(current_app.root_path, 'Digidokters_Gebruikershandleiding.docx')
        if os.path.exists(handleiding_pad):
            bijlagen.append({
                'path': handleiding_pad,
                'naam': 'Digidokters_Gebruikershandleiding.docx'
            })
        else:
            current_app.logger.warning(f"Gebruikershandleiding niet gevonden in AppDocumenten of op pad: {handleiding_pad}")

    try:
        success, msg = verstuur_email(
            ontvangers=[gebruiker_email],
            onderwerp=onderwerp,
            inhoud_tekst=inhoud,
            bijlagen=bijlagen
        )
        return success, msg
    except Exception as e:
        current_app.logger.error(f"Fout bij verzenden welkomstmail: {str(e)}")
        return False, str(e)



