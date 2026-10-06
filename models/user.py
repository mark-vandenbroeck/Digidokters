from datetime import datetime, timezone
from flask_login import UserMixin
from extensions import db, login_manager
from models.constants import ROLE_PLATFORMBEHEERDER, ROLE_BEHEERDER, ROLE_MEDEWERKER, ROLE_LEZER


class User(UserMixin, db.Model):
    """Gebruiker van de applicatie (medewerker of beheerder)."""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    naam = db.Column(db.String(100), unique=True, nullable=False, index=True)
    email = db.Column(db.String(150), unique=True, nullable=True, index=True)
    telefoonnummer = db.Column(db.String(30), nullable=True)
    wachtwoord_hash = db.Column(db.String(256), nullable=False)
    rol = db.Column(db.String(20), nullable=False, default=ROLE_MEDEWERKER)
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
    functies = db.relationship('Functie', secondary='user_functies', backref=db.backref('users', lazy='dynamic'))
    user_groepen = db.relationship('UserGroup', back_populates='user', cascade='all, delete-orphan', foreign_keys='UserGroup.user_id')
    groepen = db.relationship(
        'Group',
        secondary='user_groups',
        primaryjoin='User.id == UserGroup.user_id',
        secondaryjoin='Group.id == UserGroup.groep_id',
        back_populates='users',
        lazy='dynamic',
        overlaps='user_groepen,users'
    )

    def get_functies_voor_organisatie(self, org_id):
        """Haal de toegekende functies van deze gebruiker op binnen een specifieke organisatie."""
        return [f for f in self.functies if f.organisatie_id == org_id]

    def get_groepen_voor_organisatie(self, org_id):
        """Haal de toegekende actieve groepen van deze gebruiker op binnen een specifieke organisatie."""
        from models.group import Group, UserGroup
        return Group.query.join(UserGroup, Group.id == UserGroup.groep_id)\
            .filter(UserGroup.user_id == self.id, Group.organisatie_id == org_id, Group.actief == True)\
            .order_by(Group.naam).all()

    def has_permission(self, feature, required_level='read', org_id=None):
        """Controleert of de gebruiker de vereiste permissie heeft voor een functionaliteit."""
        from utils.permissions import has_permission
        return has_permission(feature, required_level, user=self, org_id=org_id)

    def is_beheerder(self):
        if self.rol == ROLE_PLATFORMBEHEERDER:
            return True
        from flask import session, has_request_context
        if has_request_context():
            org_id = session.get('organisatie_id')
            if org_id:
                # Eerst controleren via dynamische permissies (heeft write op 'gebruikers')
                from utils.permissions import has_permission
                if has_permission('gebruikers', 'write', user=self, org_id=org_id):
                    return True
                for uo in self.user_organisaties:
                    if uo.organisatie_id == org_id and uo.rol == ROLE_BEHEERDER and uo.actief:
                        return True
                return False
        return self.rol == ROLE_BEHEERDER

    def is_lezer(self):
        if self.rol == ROLE_PLATFORMBEHEERDER:
            return False
        from flask import session, has_request_context
        if has_request_context():
            org_id = session.get('organisatie_id')
            if org_id:
                for uo in self.user_organisaties:
                    if uo.organisatie_id == org_id and uo.actief:
                        return uo.rol == ROLE_LEZER
                return False
        return self.rol == ROLE_LEZER

    def __repr__(self):
        return f'<User {self.naam}>'


@login_manager.user_loader
def load_user(user_id):
    from sqlalchemy.orm import joinedload
    from models.organisatie import UserOrganisatie
    return User.query.options(
        joinedload(User.user_organisaties).joinedload(UserOrganisatie.organisatie)
    ).filter_by(id=int(user_id)).first()