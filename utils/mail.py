import os
import smtplib
import traceback
from datetime import datetime
from email.mime.text import MIMEText
from flask import current_app, request
from flask_login import current_user

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
        if exception:
            trace_str = f"\n\nStack Trace:\n{''.join(traceback.format_exception(type(exception), exception, exception.__traceback__))}"
        elif error_code == 500:
            # Fallback om actieve traceback te pakken als die er is
            trace_str = f"\n\nStack Trace:\n{traceback.format_exc()}"
            
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
        
        # 3. SMTP-instellingen inladen (ondersteunt zowel SMTP_ als MAIL_ namen)
        smtp_server = os.environ.get('SMTP_SERVER') or os.environ.get('MAIL_SERVER')
        smtp_port = int(os.environ.get('SMTP_PORT') or os.environ.get('MAIL_PORT', '587'))
        smtp_username = os.environ.get('SMTP_USERNAME') or os.environ.get('MAIL_USERNAME')
        smtp_password = os.environ.get('SMTP_PASSWORD') or os.environ.get('MAIL_PASSWORD')
        smtp_sender = os.environ.get('SMTP_SENDER') or os.environ.get('MAIL_DEFAULT_SENDER', 'digidokters@gmail.com')
        
        # 4. Verzenden via SMTP
        if not smtp_server:
            current_app.logger.warning(
                f"SMTP_SERVER is niet geconfigureerd. Foutmail (fout {error_code}) zou verzonden worden naar {ontvangers}. "
                f"Mail inhoud:\n{mail_body}"
            )
            return
            
        msg = MIMEText(mail_body, 'plain', 'utf-8')
        msg['Subject'] = f"[Digidokters Alert] Fout {error_code} opgetreden"
        msg['From'] = smtp_sender
        msg['To'] = ", ".join(ontvangers)
        
        if smtp_port == 465:
            server = smtplib.SMTP_SSL(smtp_server, smtp_port)
        else:
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
            
        if smtp_username and smtp_password:
            server.login(smtp_username, smtp_password)
            
        server.sendmail(smtp_sender, ontvangers, msg.as_string())
        server.quit()
        current_app.logger.info(f"Foutmail succesvol verzonden naar {ontvangers}")
    except Exception as mail_ex:
        current_app.logger.error(f"Fout bij het genereren of verzenden van de foutmail: {str(mail_ex)}")
