from datetime import datetime, timezone
from extensions import db


class Deelnemer(db.Model):
    """Deelnemer aan activiteiten / workshops."""
    __tablename__ = 'deelnemers'

    id = db.Column(db.Integer, primary_key=True)
    naam = db.Column(db.String(150), nullable=False)
    postcode = db.Column(db.String(20), nullable=True)
    leeftijdscategorie_id = db.Column(db.Integer, db.ForeignKey('age_categories.id', ondelete='SET NULL'), nullable=True, index=True)
    toestel_id = db.Column(db.Integer, db.ForeignKey('devices.id', ondelete='SET NULL'), nullable=True, index=True)
    actief = db.Column(db.Boolean, default=True, nullable=False)
    organisatie_id = db.Column(db.Integer, db.ForeignKey('organisaties.id'), nullable=False, index=True)
    aangemaakt_op = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        db.UniqueConstraint('organisatie_id', 'naam', name='uq_deelnemer_org_naam'),
    )

    # Relaties
    organisatie = db.relationship('Organisatie', backref=db.backref('deelnemers', lazy=True))
    leeftijdscategorie = db.relationship('AgeCategory', backref=db.backref('deelnemers', lazy=True))
    toestel = db.relationship('Device', backref=db.backref('deelnemers', lazy=True))

    @property
    def effectieve_leeftijdscategorie(self):
        return self.leeftijdscategorie.effectieve_naam if self.leeftijdscategorie else None

    @property
    def effectief_toestel(self):
        return self.toestel.effectieve_naam if self.toestel else None

    def __repr__(self):
        return f'<Deelnemer {self.naam}>'
