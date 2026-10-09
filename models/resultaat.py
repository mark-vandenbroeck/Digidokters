from sqlalchemy.ext.hybrid import hybrid_property
from extensions import db


class Resultaat(db.Model):
    """Resultaat van het bezoek (bijvoorbeeld: Vraag beantwoord, Bezoeker doorverwezen, etc.)."""
    __tablename__ = 'resultaten'

    id = db.Column(db.Integer, primary_key=True)
    omschrijving = db.Column(db.String(100), nullable=False)
    actief = db.Column(db.Boolean, default=True, nullable=False)
    volgorde = db.Column(db.Integer, default=0, nullable=False)
    organisatie_id = db.Column(db.Integer, db.ForeignKey('organisaties.id'), nullable=False)

    __table_args__ = (
        db.UniqueConstraint('organisatie_id', 'omschrijving', name='uq_resultaat_org_omschrijving'),
    )

    # Relatie naar registraties
    registraties = db.relationship('Registration', backref='resultaat', lazy=True)

    @hybrid_property
    def naam(self):
        """Alias voor omschrijving t.b.v. generieke stamgegevens-helpers en templates."""
        return self.omschrijving

    @naam.setter
    def naam(self, value):
        self.omschrijving = value

    def __repr__(self):
        return f'<Resultaat {self.omschrijving}>'
