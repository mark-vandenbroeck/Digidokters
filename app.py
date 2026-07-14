from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from config import Config
import os

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)

    # Flask-Login configuratie
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Gelieve in te loggen om deze pagina te bekijken.'
    login_manager.login_message_category = 'warning'

    # Maak upload/log mappen aan
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['IMPORT_LOG_FOLDER'], exist_ok=True)

    # Importeer modellen zodat Flask-Migrate ze detecteert
    from models import user, digidokter, age_category, device, registration  # noqa: F401

    # Registreer blueprints
    from routes.auth import auth_bp
    from routes.registrations import reg_bp
    from routes.admin import admin_bp
    from routes.import_export import ie_bp
    from routes.stats import stats_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(reg_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(ie_bp)
    app.register_blueprint(stats_bp)

    # CLI-commando: flask seed
    @app.cli.command('seed')
    def seed():
        """Maak de standaard beheerder en initiële lijsten aan."""
        from models.user import User
        from models.digidokter import Digidokter
        from models.age_category import AgeCategory
        from models.device import Device
        from werkzeug.security import generate_password_hash

        admin_email = 'mark.vandenbroeck@gmail.com'
        if not User.query.filter_by(email=admin_email).first():
            admin = User(
                naam='Mark',
                email=admin_email,
                wachtwoord_hash=generate_password_hash('Digidokter2024!'),
                rol='beheerder',
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

        # Seed Digidokters
        if not Digidokter.query.first():
            for i, name in enumerate(['Mark', 'Jan', 'Els']):
                db.session.add(Digidokter(naam=name, actief=True, volgorde=i))
            db.session.commit()
            print("✓ Digidokters geïnitialiseerd")

        # Seed Leeftijdscategorieën
        if not AgeCategory.query.first():
            for i, name in enumerate(['Jonger dan 18', '18 - 30', '31 - 60', '60+']):
                db.session.add(AgeCategory(naam=name, actief=True, volgorde=i))
            db.session.commit()
            print("✓ Leeftijdscategorieën geïnitialiseerd")

        # Seed Toestellen
        if not Device.query.first():
            for i, name in enumerate([
                'Smartphone Android',
                'Smartphone iPhone',
                'Tablet Android',
                'iPad',
                'Laptop Windows',
                'MacBook',
                'Ander toestel'
            ]):
                db.session.add(Device(naam=name, actief=True, volgorde=i))
            db.session.commit()
            print("✓ Toestellen geïnitialiseerd")

    return app


app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5050, debug=True)
