"""Modellen voor Groepen, Groepspermissies en Gebruiker-Groep koppelingen per organisatie."""
from datetime import datetime, timezone
from extensions import db
from models.constants import (
    ACCESS_NONE, ACCESS_READ, ACCESS_WRITE, ACCESS_LEVELS,
    ALL_FEATURES
)


class Group(db.Model):
    """Groep binnen een specifieke organisatie."""
    __tablename__ = 'groups'

    id = db.Column(db.Integer, primary_key=True)
    organisatie_id = db.Column(db.Integer, db.ForeignKey('organisaties.id', ondelete='CASCADE'), nullable=False, index=True)
    naam = db.Column(db.String(100), nullable=False)
    beschrijving = db.Column(db.String(255), nullable=True)
    is_standaard = db.Column(db.Boolean, default=False, nullable=False)  # Systeemgroep (bijv. lezers, medewerkers, beheerders)
    alleen_eigen_registraties = db.Column(db.Boolean, default=False, nullable=False)  # Beperk digidokter tot enkel eigen registraties
    actief = db.Column(db.Boolean, default=True, nullable=False)
    aangemaakt_op = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        db.UniqueConstraint('organisatie_id', 'naam', name='uq_group_organisatie_naam'),
    )

    # Relationships
    organisatie = db.relationship('Organisatie', backref=db.backref('groepen', cascade='all, delete-orphan', lazy='dynamic'))
    permissies = db.relationship('GroupPermission', back_populates='groep', cascade='all, delete-orphan')
    user_groepen = db.relationship('UserGroup', back_populates='groep', cascade='all, delete-orphan', overlaps='groepen,users')
    users = db.relationship(
        'User',
        secondary='user_groups',
        primaryjoin='Group.id == UserGroup.groep_id',
        secondaryjoin='User.id == UserGroup.user_id',
        back_populates='groepen',
        lazy='dynamic',
        overlaps='user_groepen,groepen'
    )

    def get_permission(self, feature: str) -> str:
        """Haal het toegangsniveau op voor een specifieke functionaliteit ('geen', 'lezen', 'schrijven')."""
        for p in self.permissies:
            if p.functionaliteit == feature:
                return p.toegangsniveau
        return ACCESS_NONE

    def set_permission(self, feature: str, level: str):
        """Stel het toegangsniveau in voor een functionaliteit."""
        if level not in ACCESS_LEVELS:
            level = ACCESS_NONE
        for p in self.permissies:
            if p.functionaliteit == feature:
                p.toegangsniveau = level
                return p
        new_perm = GroupPermission(groep_id=self.id, functionaliteit=feature, toegangsniveau=level)
        self.permissies.append(new_perm)
        return new_perm

    def to_dict(self):
        return {
            'id': self.id,
            'organisatie_id': self.organisatie_id,
            'naam': self.naam,
            'beschrijving': self.beschrijving,
            'is_standaard': self.is_standaard,
            'alleen_eigen_registraties': self.alleen_eigen_registraties,
            'actief': self.actief,
            'leden_aantal': self.users.count(),
            'permissies': {p.functionaliteit: p.toegangsniveau for p in self.permissies}
        }

    def __repr__(self):
        return f'<Group {self.naam} (org_id={self.organisatie_id})>'


class GroupPermission(db.Model):
    """Permissie per functionaliteit voor een specifieke groep."""
    __tablename__ = 'group_permissions'

    id = db.Column(db.Integer, primary_key=True)
    groep_id = db.Column(db.Integer, db.ForeignKey('groups.id', ondelete='CASCADE'), nullable=False, index=True)
    functionaliteit = db.Column(db.String(50), nullable=False)
    toegangsniveau = db.Column(db.String(20), default=ACCESS_NONE, nullable=False)  # 'geen', 'lezen', 'schrijven'

    __table_args__ = (
        db.UniqueConstraint('groep_id', 'functionaliteit', name='uq_group_permission_feature'),
    )

    groep = db.relationship('Group', back_populates='permissies')

    def __repr__(self):
        return f'<GroupPermission groep_id={self.groep_id} {self.functionaliteit}={self.toegangsniveau}>'


class UserGroup(db.Model):
    """Koppeltabel tussen User en Group (meervoudig groepslidmaatschap)."""
    __tablename__ = 'user_groups'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    groep_id = db.Column(db.Integer, db.ForeignKey('groups.id', ondelete='CASCADE'), nullable=False, index=True)
    toegekend_op = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    toegekend_door_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'groep_id', name='uq_user_group'),
    )

    user = db.relationship('User', back_populates='user_groepen', foreign_keys=[user_id], overlaps='groepen,users')
    groep = db.relationship('Group', back_populates='user_groepen', foreign_keys=[groep_id], overlaps='groepen,users')
    toegekend_door = db.relationship('User', foreign_keys=[toegekend_door_id])

    def __repr__(self):
        return f'<UserGroup user_id={self.user_id} groep_id={self.groep_id}>'
