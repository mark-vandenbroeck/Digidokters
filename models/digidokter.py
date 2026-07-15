from extensions import db


class Digidokter(db.Model):
    """Vrijwilliger / Digidokter."""
    __tablename__ = 'digidokters'

    id = db.Column(db.Integer, primary_key=True)
    naam = db.Column(db.String(100), nullable=False)
    actief = db.Column(db.Boolean, default=True, nullable=False)
    volgorde = db.Column(db.Integer, default=0, nullable=False)
    organisatie_id = db.Column(db.Integer, db.ForeignKey('organisaties.id'), nullable=False)

    __table_args__ = (
        db.UniqueConstraint('organisatie_id', 'naam', name='uq_digidokter_org_naam'),
    )

    # Relatie
    registraties = db.relationship('Registration', backref='digidokter', lazy=True)

    def __repr__(self):
        return f'<Digidokter {self.naam}>'
