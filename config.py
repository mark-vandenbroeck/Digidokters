import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

_IS_PRODUCTION = os.environ.get('FLASK_ENV') == 'production'


class Config:
    # Security
    SECRET_KEY = os.environ.get('SECRET_KEY', 'digidokters-dev-key-change-in-production-2024')

    # Session cookies (Secure alleen in productie, zodat lokaal HTTP blijft werken)
    SESSION_COOKIE_SECURE = _IS_PRODUCTION
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    REMEMBER_COOKIE_SECURE = _IS_PRODUCTION
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)

    # Database: supports both SQLite (local) and PostgreSQL (Supabase/Render)
    _db_url = os.environ.get('DATABASE_URL', 'sqlite:///digidokters.db')
    # Fix older Heroku/Render postgres:// URLs
    if _db_url.startswith('postgres://'):
        _db_url = _db_url.replace('postgres://', 'postgresql://', 1)
    SQLALCHEMY_DATABASE_URI = _db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
        'pool_size': 10,
        'max_overflow': 20,
        'pool_timeout': 30,
    }

    # Upload settings
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
    IMPORT_LOG_FOLDER = os.path.join(os.path.dirname(__file__), 'import_logs')

    # CSRF
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 3600  # 1 uur
    WTF_CSRF_SSL_STRICT = _IS_PRODUCTION
    WTF_CSRF_COOKIE_SECURE = _IS_PRODUCTION
    WTF_CSRF_COOKIE_HTTPONLY = True

    # App info
    APP_NAME = 'Digidokters'
    APP_VERSION = '1.0.0'
