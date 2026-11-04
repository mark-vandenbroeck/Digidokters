from datetime import datetime, timezone
from extensions import db


class Deelnemer(db.Model):
    """Deelnemer aan activiteiten / workshops."""
    __tablename__ = 'deelnemers'

    id = db.Column(db.Integer, primary_key=True)
    naam = db.Column(db.String(150), nullable=False)
    actief = db.Column(db.Boolean, default=True, nullable=False)
    organisatie_id = db.Column(db.Integer, db.ForeignKey('organisaties.id'), nullable=False, index=True)
    aangemaakt_op = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        db.UniqueConstraint('organisatie_id', 'naam', name='uq_deelnemer_org_naam'),
    )

    # Relatie
    organisatie = db.relationship('Organisatie', backref=db.backref('deelnemers', lazy=True))

    def __repr__(self):
        return f'<Deelnemer {self.naam}>'

