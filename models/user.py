from datetime import datetime, timezone
from flask_login import UserMixin
from extensions import db, login_manager


class User(UserMixin, db.Model):
    """Gebruiker van de applicatie (medewerker of beheerder)."""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    naam = db.Column(db.String(100), nullable=False)
    gebruikersnaam = db.Column(db.String(50), unique=True, nullable=False, index=True)
    email = db.Column(db.String(150), unique=True, nullable=False, index=True)
    wachtwoord_hash = db.Column(db.String(256), nullable=False)
    rol = db.Column(db.String(20), nullable=False, default='medewerker')  # 'medewerker' | 'beheerder'
    actief = db.Column(db.Boolean, default=True, nullable=False)
    moet_wachtwoord_wijzigen = db.Column(db.Boolean, default=False, nullable=False)
    aangemaakt_op = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    laatste_login = db.Column(db.DateTime, nullable=True)

    # Relatie: registraties aangemaakt door deze gebruiker
    registraties = db.relationship('Registration', backref='aangemaakt_door_user', lazy=True,
                                   foreign_keys='Registration.aangemaakt_door_id')

    def is_beheerder(self):
        return self.rol == 'beheerder'

    def __repr__(self):
        return f'<User {self.gebruikersnaam}>'


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))