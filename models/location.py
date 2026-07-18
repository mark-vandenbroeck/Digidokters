from extensions import db

class Location(db.Model):
    """Locatie van activiteit (bijv. Bib Londerzeel, Buurttafel, Brouwerij De Palm)."""
    __tablename__ = 'locations'

    id = db.Column(db.Integer, primary_key=True)
    naam = db.Column(db.String(150), nullable=False)
    actief = db.Column(db.Boolean, default=True, nullable=False)
    volgorde = db.Column(db.Integer, default=0, nullable=False)
    organisatie_id = db.Column(db.Integer, db.ForeignKey('organisaties.id'), nullable=False)

    __table_args__ = (
        db.UniqueConstraint('organisatie_id', 'naam', name='uq_location_org_naam'),
    )

    def __repr__(self):
        return f'<Location {self.naam}>'
