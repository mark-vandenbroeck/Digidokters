from extensions import db


class GenderIdentity(db.Model):
    """Genderidentiteit van de bezoeker (stamgegeven)."""
    __tablename__ = 'gender_identities'

    id = db.Column(db.Integer, primary_key=True)
    naam = db.Column(db.String(100), nullable=False)
    actief = db.Column(db.Boolean, default=True, nullable=False)
    volgorde = db.Column(db.Integer, default=0, nullable=False)
    organisatie_id = db.Column(db.Integer, db.ForeignKey('organisaties.id'), nullable=False)

    __table_args__ = (
        db.UniqueConstraint('organisatie_id', 'naam', name='uq_gender_identity_org_naam'),
    )

    @property
    def omschrijving(self):
        return self.naam

    @omschrijving.setter
    def omschrijving(self, val):
        self.naam = val

    def __repr__(self):
        return f'<GenderIdentity {self.naam}>'
