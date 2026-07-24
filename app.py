from flask import Flask, send_from_directory, render_template, flash
from config import Config
from extensions import db, migrate, login_manager, csrf, limiter
import os
from sqlalchemy.engine import Engine
from sqlalchemy import event


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    # Enkel uitvoeren op SQLite databaseverbindingen
    if 'sqlite' in str(type(dbapi_connection)).lower():
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        except Exception:
            pass
        cursor.close()


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Extensions
    db.init_app(app)
    from utils.audit import register_audit_listeners
    register_audit_listeners(db)
    
    migrate.init_app(app, db)

    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    # Flask-Login configuratie
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Gelieve in te loggen om deze pagina te bekijken.'
    login_manager.login_message_category = 'warning'

    # Maak upload/log mappen aan
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['IMPORT_LOG_FOLDER'], exist_ok=True)

    # Importeer modellen zodat Flask-Migrate ze detecteert
    from models import user, digidokter, age_category, device, registration, organisatie, activity_type, location, agenda  # noqa: F401

    # Registreer blueprints
    from routes.auth import auth_bp
    from routes.registrations import reg_bp
    from routes.admin import admin_bp
    from routes.import_export import ie_bp
    from routes.stats import stats_bp
    from routes.platform import platform_bp
    from routes.agenda import agenda_bp
    from routes.documents import doc_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(reg_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(ie_bp)
    app.register_blueprint(stats_bp)
    app.register_blueprint(platform_bp)
    app.register_blueprint(agenda_bp)
    app.register_blueprint(doc_bp)


    # Controleer de organisatie-context voor authenticated requests
    from flask import session, redirect, url_for, request, flash, g
    from flask_login import current_user

    @app.before_request
    def check_organisatie_context():
        if request.endpoint:
            # Exclude statics, service worker, auth endpoints and platform endpoints
            exempt_endpoints = [
                'static',
                'service_worker',
                'test_mail',
                'auth.login',
                'auth.logout',
                'auth.select_org',
                'auth.switch_organisatie',
            ]
            if request.endpoint in exempt_endpoints or request.endpoint.startswith('auth.') or request.endpoint.startswith('platform.'):
                if current_user.is_authenticated and current_user.rol == 'platformbeheerder':
                    from models.organisatie import Organisatie
                    g.beschikbare_organisaties = Organisatie.query.filter_by(actief=True).all()
                return

        if current_user.is_authenticated:
            if current_user.rol == 'platformbeheerder':
                from models.organisatie import Organisatie
                g.beschikbare_organisaties = Organisatie.query.filter_by(actief=True).all()
                org_id = session.get('organisatie_id')
                if not org_id:
                    return redirect(url_for('auth.select_org', next=request.full_path))
                org = Organisatie.query.filter_by(id=org_id, actief=True).first()
                if not org:
                    session.pop('organisatie_id', None)
                    flash('De geselecteerde organisatie is niet langer actief.', 'warning')
                    return redirect(url_for('auth.select_org'))
            else:
                org_id = session.get('organisatie_id')
                if not org_id:
                    return redirect(url_for('auth.select_org', next=request.full_path))
                
                # Controleer of de gebruiker nog een actief lidmaatschap heeft
                membership = next((uo for uo in current_user.user_organisaties if uo.organisatie_id == org_id and uo.actief and uo.organisatie.actief), None)
                if not membership:
                    session.pop('organisatie_id', None)
                    flash('Uw toegang tot deze organisatie is niet langer geldig.', 'warning')
                    return redirect(url_for('auth.select_org'))

    # Service worker moet op root-niveau staan (niet /static/sw.js) zodat
    # zijn scope de volledige app dekt, wat vereist is voor PWA-installatie.
    @app.route('/sw.js')
    def service_worker():
        response = send_from_directory(app.static_folder, 'sw.js')
        response.headers['Content-Type'] = 'application/javascript'
        response.headers['Service-Worker-Allowed'] = '/'
        return response

    @app.route('/test-mail')
    def test_mail():
        from flask import request, jsonify
        from utils.mail import verstuur_email
        
        recipient = request.args.get('to')
        if not recipient:
            return jsonify({
                'status': 'error',
                'message': 'Geef een ontvanger op via ?to=jouw-email@domain.com'
            }), 400

        try:
            body = 'Hallo!\n\nDit is een test e-mail verstuurd vanuit de Digidokters applicatie.'
            success, msg = verstuur_email(recipient, 'Test Mail Digidokters', body)
            
            return jsonify({
                'status': 'success',
                'message': f'{msg} (naar {recipient})'
            })
        except Exception as e:
            return jsonify({
                'status': 'error',
                'message': f'Fout bij het verzenden van e-mail: {str(e)}'
            }), 500


    @app.after_request
    def add_security_headers(response):
        if os.environ.get('FLASK_ENV') == 'production':
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
            "font-src 'self' https://cdn.jsdelivr.net https://fonts.gstatic.com; "
            "img-src 'self' data:; "
            "connect-src 'self';"
        )
        return response

    # Foutafhandeling
    from flask_wtf.csrf import CSRFError

    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        flash('Uw sessie is verlopen vanwege inactiviteit. Log opnieuw in.', 'warning')
        return redirect(url_for('auth.login'))

    @app.errorhandler(403)
    def forbidden_error(e):
        return render_template('errors/403.html'), 403

    @app.errorhandler(404)
    def not_found_error(e):
        return render_template('errors/404.html'), 404

    @app.errorhandler(429)
    def ratelimit_handler(e):
        flash('Te veel aanvragen. Probeer het over enkele minuten opnieuw.', 'danger')
        return render_template('errors/429.html'), 429

    @app.errorhandler(500)
    def internal_error(e):
        db.session.rollback()
        app.logger.error(f"Internal Server Error: {e}")
        try:
            from utils.mail import stuur_fout_email
            stuur_fout_email(500, str(e), exception=e)
        except Exception as mail_err:
            app.logger.error(f"Kon foutmail niet versturen: {mail_err}")
        return render_template('errors/500.html'), 500

    # CLI-commando: flask seed
    @app.cli.command('seed')
    def seed():
        """Maak de standaard beheerder en initiële lijsten aan."""
        from models.organisatie import Organisatie, UserOrganisatie
        from models.user import User
        from models.digidokter import Digidokter
        from models.age_category import AgeCategory
        from models.device import Device
        from models.activity_type import ActivityType
        from models.location import Location
        from werkzeug.security import generate_password_hash

        # 0. Schoning inactieve e-mailteksten ('none', 'null', '') naar SQL NULL
        try:
            db.session.execute(db.text("UPDATE users SET email = NULL WHERE LOWER(email) IN ('none', 'null', '', 'n/a');"))
            db.session.commit()
            print('✓ E-mailadressen in database opgeschoond naar NULL')
        except Exception:
            db.session.rollback()

        # 1. Seed Organisatie
        default_org = Organisatie.query.filter_by(slug='digidokters').first()
        if not default_org:
            default_org = Organisatie(naam='Digidokters', slug='digidokters', actief=True)
            db.session.add(default_org)
            db.session.commit()
            print('✓ Standaard organisatie aangemaakt: Digidokters')
        else:
            print('Standaard organisatie bestaat al.')

        # 2. Seed Admin User
        admin_email = 'digidokters.admin@gmail.com'
        admin = User.query.filter((User.email == admin_email) | (User.naam == 'Mark')).first()
        if not admin:
            admin = User(
                naam='Mark',
                email=admin_email,
                wachtwoord_hash=generate_password_hash('Digidokter2024!'),
                rol='beheerder',  # fallback
                actief=True,
                moet_wachtwoord_wijzigen=True
            )
            db.session.add(admin)
            db.session.commit()
            print(f'✓ Admin aangemaakt: {admin_email}')
            print('  Tijdelijk wachtwoord: Digidokter2024!')
            print('  Wijzig dit wachtwoord na de eerste login!')
        else:
            print(f'Admin {admin_email} bestaat al.')

        # 3. Koppel Admin aan default org
        if not UserOrganisatie.query.filter_by(user_id=admin.id, organisatie_id=default_org.id).first():
            uo = UserOrganisatie(user_id=admin.id, organisatie_id=default_org.id, rol='beheerder', actief=True)
            db.session.add(uo)
            db.session.commit()
            print('✓ Admin gekoppeld aan standaard organisatie')

        # 4. Seed Digidokters
        if not Digidokter.query.filter_by(organisatie_id=default_org.id).first():
            for i, name in enumerate(['Mark', 'Jan', 'Els']):
                db.session.add(Digidokter(naam=name, actief=True, volgorde=i, organisatie_id=default_org.id))
            db.session.commit()
            print("✓ Digidokters geïnitialiseerd voor standaard organisatie")

        # 5. Seed Leeftijdscategorieën
        if not AgeCategory.query.filter_by(organisatie_id=default_org.id).first():
            for i, name in enumerate(['Jonger dan 18', '18 - 30', '31 - 60', '60+']):
                db.session.add(AgeCategory(naam=name, actief=True, volgorde=i, organisatie_id=default_org.id))
            db.session.commit()
            print("✓ Leeftijdscategorieën geïnitialiseerd voor standaard organisatie")

        # 6. Seed Toestellen
        if not Device.query.filter_by(organisatie_id=default_org.id).first():
            for i, name in enumerate([
                'Smartphone Android',
                'Smartphone iPhone',
                'Tablet Android',
                'iPad',
                'Laptop Windows',
                'MacBook',
                'Ander toestel'
            ]):
                db.session.add(Device(naam=name, actief=True, volgorde=i, organisatie_id=default_org.id))
            db.session.commit()
            print("✓ Toestellen geïnitialiseerd voor standaard organisatie")

        # 7. Seed Activiteitstypes
        if not ActivityType.query.filter_by(organisatie_id=default_org.id).first():
            for i, name in enumerate(['Digidokters', 'Digicafé', 'Lunchvergadering']):
                db.session.add(ActivityType(naam=name, actief=True, volgorde=i, organisatie_id=default_org.id))
            db.session.commit()
            print("✓ Activiteitstypes geïnitialiseerd voor standaard organisatie")

        # 8. Seed Locaties
        if not Location.query.filter_by(organisatie_id=default_org.id).first():
            for i, name in enumerate(['Bib Londerzeel', 'Buurttafel', 'Brouwerij De Palm']):
                db.session.add(Location(naam=name, actief=True, volgorde=i, organisatie_id=default_org.id))
            db.session.commit()
            print("✓ Locaties geïnitialiseerd voor standaard organisatie")

    # CLI-commando: flask create-org <naam> <slug>
    import click
    @app.cli.command('create-org')
    @click.argument('naam')
    @click.argument('slug')
    def create_org_cli(naam, slug):
        """Maak een nieuwe organisatie aan."""
        from models.organisatie import Organisatie
        if Organisatie.query.filter_by(slug=slug).first():
            print(f'Fout: Organisatie met slug "{slug}" bestaat al.')
            return
        org = Organisatie(naam=naam, slug=slug, actief=True)
        db.session.add(org)
        db.session.commit()
        
        from utils.tenant import seed_organisatie_defaults
        seed_organisatie_defaults(org.id)
        
        print(f'✓ Organisatie "{naam}" aangemaakt met slug "{slug}" (met standaard data)')

    @app.cli.command('clean-audit-logs')
    def clean_audit_logs():
        """Verwijder audit logs ouder dan 365 dagen."""
        from datetime import datetime, timedelta, timezone
        from models.audit import AuditLog
        grens = datetime.now(timezone.utc) - timedelta(days=365)
        try:
            aantal = AuditLog.query.filter(AuditLog.timestamp < grens).delete()
            db.session.commit()
            print(f'✓ Succesvol {aantal} oude audit logs verwijderd.')
        except Exception as e:
            db.session.rollback()
            print(f'Fout bij verwijderen: {str(e)}')

    # Synchroniseer bestaande gebruikers als Digidokter op de achtergrond bij het opstarten
    with app.app_context():
        try:
            from models.organisatie import UserOrganisatie
            from models.digidokter import Digidokter
            memberships = UserOrganisatie.query.all()
            synced = 0
            for m in memberships:
                existing = Digidokter.query.filter_by(organisatie_id=m.organisatie_id, naam=m.user.naam).first()
                if not existing:
                    max_volgorde = db.session.query(db.func.max(Digidokter.volgorde)).filter_by(organisatie_id=m.organisatie_id).scalar() or 0
                    dd = Digidokter(naam=m.user.naam, actief=True, volgorde=max_volgorde + 1, organisatie_id=m.organisatie_id)
                    db.session.add(dd)
                    synced += 1
            if synced > 0:
                db.session.commit()
                print(f"✓ Synchronisatie: {synced} gebruikers gesynchroniseerd als Digidokter")
        except Exception:
            pass

    return app


app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5050, debug=True)