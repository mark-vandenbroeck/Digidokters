"""Systeemgezondheid, telemetrie en diagnostische controles voor het platform."""
import os
import sys
import time
import socket
import shutil
import platform
import resource
from datetime import datetime, date, timedelta, timezone
from flask import current_app, has_request_context, request, session as flask_session
from sqlalchemy import text, func
from extensions import db
from models.telemetry import PageViewStat, SystemErrorLog
from models.registration import Registration
from models.user import User
from models.organisatie import Organisatie
from models.audit import AuditLog
from models.document import Document
from models.agenda import AgendaItem
from models.communicatie import CommunicatieLog
from models.question_classification import QuestionClassification

# Tijdstip waarop het proces gestart is
PROCESS_START_TIME = datetime.now(timezone.utc)

ENDPOINT_LABELS = {
    'platform.dashboard': 'Platform Dashboard',
    'platform.systeemmonitor': 'Platform Systeemmonitor',
    'platform.organisaties': 'Platform Organisaties',
    'platform.koppelingen': 'Platform Koppelingen',
    'platform.emailsjablonen': 'Platform E-mailsjablonen',
    'platform.communicatie': 'Platform Communicatie',
    'platform.vraagcategorieen': 'Platform Vraagcategorieën',
    'platform.vraagclassificaties': 'Platform Vraagclassificaties',
    'reg.lijst': 'Registraties Overzicht',
    'reg.nieuw': 'Nieuwe Registratie',
    'reg.snel': 'Snel Registreren',
    'reg.bekijken': 'Registratie Detail',
    'reg.wijzigen': 'Registratie Bewerken',
    'agenda.lijst': 'Agenda Overzicht',
    'agenda.nieuw': 'Agenda Nieuw Item',
    'agenda.wijzigen': 'Agenda Item Bewerken',
    'eval.resultaten': 'Evaluaties Resultaten',
    'eval.sessie_detail': 'Evaluatie Sessie Detail',
    'eval.overzicht': 'Evaluatieformulieren',
    'eval.formulier_bewerken': 'Evaluatieformulier Bewerken',
    'doc.index': 'Documenten',
    'admin.gebruikers': 'Beheer Gebruikers',
    'admin.gebruiker_nieuw': 'Beheer Gebruiker Nieuw',
    'admin.gebruiker_wijzigen': 'Beheer Gebruiker Bewerken',
    'admin.groepen_overzicht': 'Beheer Groepen & Rechten',
    'admin.digidokters': 'Beheer Digidokters',
    'admin.communicatie': 'Beheer Communicatie',
    'admin.activiteitstypes': 'Beheer Activiteitstypes',
    'admin.locaties': 'Beheer Locaties',
    'admin.leeftijdscategorieën': 'Beheer Leeftijdscategorieën',
    'admin.toestellen': 'Beheer Toestellen',
    'admin.herkomsten': 'Beheer Herkomst',
    'admin.genderidentiteiten': 'Beheer Genderidentiteit',
    'admin.functies': 'Beheer Functies',
    'admin.resultaten': 'Beheer Resultaten',
    'admin.emailsjablonen': 'Beheer E-mailsjablonen',
    'admin.backup': 'Beheer Backup',
    'admin.restore': 'Beheer Restore',
    'admin.audit_log': 'Audit Logs',
    'ie.exporteer': 'Exporteren',
    'stats.overzicht': 'Statistieken',
    'app_docs.index': 'Handleiding / Documentatie',
    'feedback.formulier': 'Feedback Formulier',
    'feedback.lijst': 'Feedback Overzicht',
    'auth.login': 'Inloggen',
    'auth.select_org': 'Organisatie Selecteren',
    'auth.wachtwoord_wijzigen': 'Wachtwoord Wijzigen',
}


def get_friendly_endpoint_label(endpoint: str) -> str:
    """Geeft een leesbare naam terug voor een route-endpoint."""
    if not endpoint:
        return 'Onbekende pagina'
    if endpoint in ENDPOINT_LABELS:
        return ENDPOINT_LABELS[endpoint]
    parts = endpoint.split('.')
    return ' '.join(p.replace('_', ' ').capitalize() for p in parts)


def record_page_view(endpoint: str, pad: str, org_id: int | None = None):
    """Registreert of incrementeert het aantal paginabezoeken voor vandaag."""
    if not endpoint or endpoint.startswith('static') or endpoint in ('service_worker', 'ping'):
        return

    try:
        vandaag = date.today()
        stat = PageViewStat.query.filter_by(
            datum=vandaag,
            endpoint=endpoint,
            organisatie_id=org_id
        ).first()

        if stat:
            stat.aantal_hits += 1
            if pad and not stat.pad:
                stat.pad = pad[:255]
        else:
            label = get_friendly_endpoint_label(endpoint)
            stat = PageViewStat(
                datum=vandaag,
                endpoint=endpoint,
                pad=pad[:255] if pad else None,
                label=label[:100] if label else None,
                organisatie_id=org_id,
                aantal_hits=1
            )
            db.session.add(stat)
        db.session.commit()
    except Exception:
        db.session.rollback()


def record_system_error(status_code: int, type_fout: str, bericht: str,
                        stacktrace: str | None = None, endpoint: str | None = None,
                        pad: str | None = None, methode: str | None = None,
                        ip_adres: str | None = None, gebruiker: str | None = None,
                        organisatie_id: int | None = None):
    """Logt een foutmelding of beveiligingsincident in system_error_logs."""
    try:
        log_entry = SystemErrorLog(
            timestamp=datetime.now(timezone.utc),
            status_code=status_code,
            type_fout=type_fout[:100] if type_fout else 'Error',
            bericht=bericht[:2000] if bericht else None,
            stacktrace=stacktrace[:10000] if stacktrace else None,
            endpoint=endpoint[:100] if endpoint else None,
            pad=pad[:255] if pad else None,
            methode=methode[:10] if methode else None,
            ip_adres=ip_adres[:50] if ip_adres else None,
            gebruiker=gebruiker[:100] if gebruiker else None,
            organisatie_id=organisatie_id
        )
        db.session.add(log_entry)
        db.session.commit()
    except Exception:
        db.session.rollback()


def check_database_health() -> dict:
    """Controleert verbinding, latentie, databasetype en omvang."""
    result = {
        'status': 'ok',
        'db_type': 'Onbekend',
        'db_name': '',
        'latency_ms': 0.0,
        'size_human': 'N.v.t.',
        'counts': {},
        'error': None
    }
    t0 = time.perf_counter()
    try:
        db.session.execute(text('SELECT 1'))
        latency = (time.perf_counter() - t0) * 1000.0
        result['latency_ms'] = round(latency, 2)

        dialect_name = db.engine.dialect.name.lower()
        if 'postgres' in dialect_name:
            result['db_type'] = 'PostgreSQL'
            try:
                db_name_res = db.session.execute(text('SELECT current_database()')).scalar()
                result['db_name'] = db_name_res or ''
                db_size_res = db.session.execute(text('SELECT pg_size_pretty(pg_database_size(current_database()))')).scalar()
                result['size_human'] = db_size_res or 'Onbekend'
            except Exception:
                pass
        elif 'sqlite' in dialect_name:
            result['db_type'] = 'SQLite'
            result['db_name'] = 'In-Memory / Lokaal bestand'
        else:
            result['db_type'] = dialect_name.capitalize()

        # Telling van kernmodellen
        result['counts'] = {
            'registraties': Registration.query.count(),
            'gebruikers': User.query.count(),
            'organisaties': Organisatie.query.count(),
            'audit_logs': AuditLog.query.count(),
            'documenten': Document.query.count(),
            'agenda_items': AgendaItem.query.count()
        }

        if latency > 200:
            result['status'] = 'warning'
    except Exception as e:
        result['status'] = 'danger'
        result['error'] = str(e)

    return result


def check_email_health() -> dict:
    """Controleert configuratie en bereikbaarheid van de mailserver en recente verzendstatistieken."""
    result = {
        'status': 'ok',
        'server': 'Niet geconfigureerd',
        'port': 25,
        'tls': False,
        'socket_connected': False,
        'sent_24h': 0,
        'failed_24h': 0,
        'failed_7d': 0,
        'error': None
    }
    try:
        mail_server = current_app.config.get('MAIL_SERVER') or os.environ.get('MAIL_SERVER')
        mail_port = current_app.config.get('MAIL_PORT') or os.environ.get('MAIL_PORT', 587)
        mail_use_tls = current_app.config.get('MAIL_USE_TLS') or False

        if mail_server:
            result['server'] = str(mail_server)
            result['port'] = int(mail_port)
            result['tls'] = bool(mail_use_tls)

            try:
                s = socket.create_connection((mail_server, int(mail_port)), timeout=1.5)
                s.close()
                result['socket_connected'] = True
            except Exception as conn_err:
                result['socket_connected'] = False
                result['status'] = 'warning'
                result['error'] = f'Poort {mail_port} niet bereikbaar: {str(conn_err)}'
        else:
            result['status'] = 'info'
            result['server'] = 'Lokale simulatie / Niet geconfigureerd'

        # Aliases voor templates
        result['smtp_host'] = result['server']
        result['smtp_port'] = result['port']
        result['ssl'] = current_app.config.get('MAIL_USE_SSL') if has_request_context() else False
        result['default_sender'] = (current_app.config.get('MAIL_DEFAULT_SENDER') or os.environ.get('MAIL_DEFAULT_SENDER', 'Niet ingesteld')) if has_request_context() else 'Niet ingesteld'
        result['total_sent_logs'] = CommunicatieLog.query.count()

        # Recente communicatielogs
        nu = datetime.now(timezone.utc)
        een_dag_geleden = nu - timedelta(days=1)
        een_week_geleden = nu - timedelta(days=7)

        result['sent_24h'] = CommunicatieLog.query.filter(
            CommunicatieLog.verzonden_op >= een_dag_geleden,
            CommunicatieLog.status == 'verzonden'
        ).count()

        result['failed_24h'] = CommunicatieLog.query.filter(
            CommunicatieLog.verzonden_op >= een_dag_geleden,
            CommunicatieLog.status == 'mislukt'
        ).count()

        result['failed_7d'] = CommunicatieLog.query.filter(
            CommunicatieLog.verzonden_op >= een_week_geleden,
            CommunicatieLog.status == 'mislukt'
        ).count()

        if result['failed_24h'] > 0:
            result['status'] = 'warning'
    except Exception as e:
        result['status'] = 'warning'
        result['error'] = str(e)

    return result


def check_ai_health() -> dict:
    """Controleert status van de AI-classificatieservice."""
    result = {
        'status': 'ok',
        'provider': 'Onbekend',
        'model': 'standaard',
        'has_api_key': False,
        'details': '',
        'classified_count': 0,
        'classified_30d': 0,
        'error': None
    }
    try:
        from utils.ai_classifier import get_actieve_provider
        provider = get_actieve_provider() if callable(get_actieve_provider) else 'onbekend'
        result['provider'] = provider
        result['model'] = os.environ.get('AI_MODEL') or 'gemini-2.5-flash'
        result['has_api_key'] = bool(os.environ.get('GEMINI_API_KEY') or os.environ.get('OPENAI_API_KEY'))
        result['classified_count'] = QuestionClassification.query.count()

        nu = datetime.now(timezone.utc)
        dertig_dagen_geleden = nu - timedelta(days=30)
        result['classified_30d'] = QuestionClassification.query.filter(
            QuestionClassification.geclassificeerd_op >= dertig_dagen_geleden
        ).count()

        if provider == 'heuristiek':
            result['status'] = 'info'
            result['details'] = 'Regelgebaseerde trefwoorden (fallback actief, geen LLM verbonden)'
        elif provider in ('ollama', 'openai'):
            result['status'] = 'ok'
            result['details'] = f'Actieve AI model service ({provider.upper()})'
        else:
            result['status'] = 'info'
            result['details'] = 'Geen externe AI service actief'
    except Exception as e:
        result['status'] = 'info'
        result['error'] = str(e)
        result['details'] = 'Fallback trefwoordenfilter'

    return result


def check_storage_health() -> dict:
    """Controleert schijfruimte en schrijfrechten op upload- en backupmappen."""
    result = {
        'status': 'ok',
        'disk_total_gb': 0.0,
        'disk_used_gb': 0.0,
        'disk_free_gb': 0.0,
        'disk_percent': 0.0,
        'used_percent': 0.0,
        'free_human': '0 GB',
        'used_human': '0 GB',
        'total_human': '0 GB',
        'total_documents': 0,
        'upload_folder': 'uploads/documenten',
        'dirs': {},
        'error': None
    }
    try:
        root_path = current_app.root_path if has_request_context() else os.getcwd()
        usage = shutil.disk_usage(root_path)
        total_gb = usage.total / (1024 ** 3)
        used_gb = usage.used / (1024 ** 3)
        free_gb = usage.free / (1024 ** 3)
        percent = (usage.used / usage.total) * 100.0 if usage.total > 0 else 0.0

        result['disk_total_gb'] = round(total_gb, 1)
        result['disk_used_gb'] = round(used_gb, 1)
        result['disk_free_gb'] = round(free_gb, 1)
        result['disk_percent'] = round(percent, 1)

        result['used_percent'] = round(percent, 1)
        result['free_human'] = f"{round(free_gb, 1)} GB"
        result['used_human'] = f"{round(used_gb, 1)} GB"
        result['total_human'] = f"{round(total_gb, 1)} GB"
        result['total_documents'] = Document.query.count()

        # Controleer upload- en backupmappen
        check_dirs = {
            'documenten': os.path.join(root_path, 'uploads', 'documenten'),
            'app_documenten': os.path.join(root_path, 'uploads', 'app_documenten'),
            'backups': os.path.join(root_path, 'backups')
        }
        result['upload_folder'] = os.path.relpath(check_dirs['documenten'], root_path)

        all_writable = True
        for name, p in check_dirs.items():
            exists = os.path.exists(p)
            writable = os.access(p, os.W_OK) if exists else os.access(os.path.dirname(p), os.W_OK)
            result['dirs'][name] = {
                'path': p,
                'exists': exists,
                'writable': writable
            }
            if not writable:
                all_writable = False

        if percent > 90 or not all_writable:
            result['status'] = 'warning'
        if percent > 95:
            result['status'] = 'danger'
    except Exception as e:
        result['status'] = 'warning'
        result['error'] = str(e)

    return result


def check_security_health() -> dict:
    """Haalt recente beveiligings- en foutstatistieken op."""
    limiter_storage = (current_app.config.get('RATELIMIT_STORAGE_URI') or 'In-memory') if has_request_context() else 'In-memory'
    is_https = request.is_secure if has_request_context() else False

    result = {
        'status': 'ok',
        'rate_limiter_storage': limiter_storage,
        'https_active': is_https,
        'errors_24h': 0,
        'errors_7d': 0,
        'rate_limits_24h': 0,
        'failed_logins_24h': 0,
        'locked_accounts': 0,
        'recent_errors': []
    }
    try:
        nu = datetime.now(timezone.utc)
        een_dag_geleden = nu - timedelta(days=1)
        een_week_geleden = nu - timedelta(days=7)

        result['errors_24h'] = SystemErrorLog.query.filter(
            SystemErrorLog.timestamp >= een_dag_geleden,
            SystemErrorLog.status_code == 500
        ).count()

        result['errors_7d'] = SystemErrorLog.query.filter(
            SystemErrorLog.timestamp >= een_week_geleden,
            SystemErrorLog.status_code == 500
        ).count()

        result['rate_limits_24h'] = SystemErrorLog.query.filter(
            SystemErrorLog.timestamp >= een_dag_geleden,
            SystemErrorLog.status_code == 429
        ).count()

        result['failed_logins_24h'] = SystemErrorLog.query.filter(
            SystemErrorLog.timestamp >= een_dag_geleden,
            SystemErrorLog.type_fout == 'LoginFailed'
        ).count()

        result['locked_accounts'] = User.query.filter(User.reset_pogingen >= 5).count()

        # Haal de laatste 15 fouten op
        recent = SystemErrorLog.query.order_by(SystemErrorLog.timestamp.desc()).limit(15).all()
        result['recent_errors'] = [
            {
                'id': e.id,
                'timestamp': e.timestamp,
                'status_code': e.status_code,
                'type_fout': e.type_fout,
                'bericht': e.bericht,
                'stacktrace': e.stacktrace,
                'pad': e.pad,
                'methode': e.methode,
                'ip_adres': e.ip_adres,
                'gebruiker': e.gebruiker,
                'organisatie_naam': e.organisatie.naam if e.organisatie else 'Algemeen'
            }
            for e in recent
        ]

        if result['errors_24h'] > 0 or result['rate_limits_24h'] > 10:
            result['status'] = 'warning'
        if result['errors_24h'] > 10:
            result['status'] = 'danger'
    except Exception:
        pass

    return result


def get_system_info() -> dict:
    """Verzamelt algemene runtime-informatie."""
    import flask
    now = datetime.now(timezone.utc)
    uptime_delta = now - PROCESS_START_TIME
    days = uptime_delta.days
    hours, remainder = divmod(uptime_delta.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    uptime_str = f"{days}d {hours}u {minutes}m" if days > 0 else f"{hours}u {minutes}m {seconds}s"

    mem_bytes = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # Op macOS is ru_maxrss in bytes, op Linux in kilobytes
    mem_mb = round(mem_bytes / (1024 * 1024) if sys.platform == 'darwin' else mem_bytes / 1024, 1)
    hostname = socket.gethostname() if hasattr(socket, 'gethostname') else 'localhost'
    try:
        import importlib.metadata
        flask_ver = importlib.metadata.version('flask')
    except Exception:
        flask_ver = '3.x'

    return {
        'python_version': platform.python_version(),
        'platform_os': platform.platform(terse=True),
        'os': platform.platform(terse=True),
        'architecture': platform.machine(),
        'flask_version': flask_ver,
        'hostname': hostname,
        'process_start': PROCESS_START_TIME,
        'uptime': uptime_str,
        'uptime_human': uptime_str,
        'memory_mb': mem_mb,
        'memory_usage_human': f"{mem_mb} MB",
        'env': os.environ.get('FLASK_ENV', 'development')
    }


def get_full_platform_health() -> dict:
    """Voert alle individuele controles uit en bepaalt de algehele platformgezondheid."""
    db_health = check_database_health()
    mail_health = check_email_health()
    ai_health = check_ai_health()
    storage_health = check_storage_health()
    sec_health = check_security_health()
    sys_info = get_system_info()

    statuses = [db_health['status'], storage_health['status'], sec_health['status']]
    if 'danger' in statuses or 'error' in statuses:
        overall = 'danger'
    elif 'warning' in statuses or mail_health['status'] == 'warning':
        overall = 'warning'
    else:
        overall = 'healthy'

    return {
        'overall_status': overall,
        'database': db_health,
        'email': mail_health,
        'ai': ai_health,
        'ai_service': ai_health,
        'storage': storage_health,
        'security': sec_health,
        'system': sys_info,
        'system_info': sys_info,
        'timestamp': datetime.now(timezone.utc)
    }
