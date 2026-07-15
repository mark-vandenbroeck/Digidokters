from extensions import db


class AgeCategory(db.Model):
    """Leeftijdscategorie van de bezoeker."""
    __tablename__ = 'age_categories'

    id = db.Column(db.Integer, primary_key=True)
    naam = db.Column(db.String(100), nullable=False)
    actief = db.Column(db.Boolean, default=True, nullable=False)
    volgorde = db.Column(db.Integer, default=0, nullable=False)
    organisatie_id = db.Column(db.Integer, db.ForeignKey('organisaties.id'), nullable=False)

    __table_args__ = (
        db.UniqueConstraint('organisatie_id', 'naam', name='uq_age_category_org_naam'),
    )

    # Relatie
    registraties = db.relationship('Registration', backref='leeftijdscategorie', lazy=True)

    def __repr__(self):
        return f'<AgeCategory {self.naam}>'
