from datetime import datetime, timezone
from flask_login import UserMixin
from extensions import db, login_manager


class User(UserMixin, db.Model):
    """Gebruiker van de applicatie (medewerker of beheerder)."""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    naam = db.Column(db.String(100), unique=True, nullable=False, index=True)
    email = db.Column(db.String(150), unique=True, nullable=True, index=True)
    wachtwoord_hash = db.Column(db.String(256), nullable=False)
    rol = db.Column(db.String(20), nullable=False, default='medewerker')  # 'medewerker' | 'beheerder'
    actief = db.Column(db.Boolean, default=True, nullable=False)
    moet_wachtwoord_wijzigen = db.Column(db.Boolean, default=False, nullable=False)
    aangemaakt_op = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    laatste_login = db.Column(db.DateTime, nullable=True)

    # Wachtwoord herstel
    reset_code = db.Column(db.String(6), nullable=True)
    reset_code_verloopt_op = db.Column(db.DateTime, nullable=True)
    reset_pogingen = db.Column(db.Integer, default=0, nullable=False)

    # Relatie: registraties aangemaakt door deze gebruiker
    registraties = db.relationship('Registration', backref='aangemaakt_door_user', lazy=True,
                                   foreign_keys='Registration.aangemaakt_door_id')
    user_organisaties = db.relationship('UserOrganisatie', back_populates='user', cascade='all, delete-orphan')


    def is_beheerder(self):
        if self.rol == 'platformbeheerder':
            return True
        from flask import session, has_request_context
        if has_request_context():
            org_id = session.get('organisatie_id')
            if org_id:
                for uo in self.user_organisaties:
                    if uo.organisatie_id == org_id and uo.rol == 'beheerder' and uo.actief:
                        return True
                return False
        return self.rol == 'beheerder'

    def is_lezer(self):
        if self.rol == 'platformbeheerder':
            return False
        from flask import session, has_request_context
        if has_request_context():
            org_id = session.get('organisatie_id')
            if org_id:
                for uo in self.user_organisaties:
                    if uo.organisatie_id == org_id and uo.actief:
                        return uo.rol == 'lezer'
        return self.rol == 'lezer'

    def __repr__(self):
        return f'<User {self.naam}>'


@login_manager.user_loader
def load_user(user_id):
    from sqlalchemy.orm import joinedload
    from models.organisatie import UserOrganisatie
    return User.query.options(
        joinedload(User.user_organisaties).joinedload(UserOrganisatie.organisatie)
    ).filter_by(id=int(user_id)).first()