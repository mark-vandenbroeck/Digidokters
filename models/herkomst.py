from extensions import db


class Herkomst(db.Model):
    """Herkomst van de bezoeker (bijvoorbeeld: hoe men bij de Digidokters terecht is gekomen)."""
    __tablename__ = 'herkomst'

    id = db.Column(db.Integer, primary_key=True)
    naam = db.Column(db.String(100), nullable=False)
    actief = db.Column(db.Boolean, default=True, nullable=False)
    volgorde = db.Column(db.Integer, default=0, nullable=False)
    organisatie_id = db.Column(db.Integer, db.ForeignKey('organisaties.id'), nullable=False)

    __table_args__ = (
        db.UniqueConstraint('organisatie_id', 'naam', name='uq_herkomst_org_naam'),
    )

    # Relatie
    registraties = db.relationship('Registration', backref='herkomst', lazy=True)

    def __repr__(self):
        return f'<Herkomst {self.naam}>'
