from datetime import datetime, timezone
from extensions import db


class Organisatie(db.Model):
    """Organisatie (Tenant) binnen het Digidokters platform."""
    __tablename__ = 'organisaties'

    id = db.Column(db.Integer, primary_key=True)
    naam = db.Column(db.String(150), nullable=False)
    slug = db.Column(db.String(80), unique=True, nullable=False, index=True)
    actief = db.Column(db.Boolean, default=True, nullable=False)
    aangemaakt_op = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    user_organisaties = db.relationship('UserOrganisatie', back_populates='organisatie', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Organisatie {self.naam}>'


class UserOrganisatie(db.Model):
    """Koppeltabel tussen User en Organisatie (Many-to-Many met metadata)."""
    __tablename__ = 'user_organisaties'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    organisatie_id = db.Column(db.Integer, db.ForeignKey('organisaties.id'), nullable=False)
    rol = db.Column(db.String(20), nullable=False, default='medewerker')  # 'beheerder' | 'medewerker'
    actief = db.Column(db.Boolean, default=True, nullable=False)
    aangemaakt_op = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Unique constraint om dubbele koppelingen te voorkomen
    __table_args__ = (
        db.UniqueConstraint('user_id', 'organisatie_id', name='uq_user_organisatie'),
    )

    # Relationships
    user = db.relationship('User', back_populates='user_organisaties')
    organisatie = db.relationship('Organisatie', back_populates='user_organisaties')

    def __repr__(self):
        return f'<UserOrganisatie user_id={self.user_id} org_id={self.organisatie_id}>'
