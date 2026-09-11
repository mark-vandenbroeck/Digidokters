from datetime import datetime, timezone
from extensions import db


class QuestionCategory(db.Model):
    """Vaste vraagcategorieën voor AI-analyse, gemeenschappelijk over alle organisaties."""
    __tablename__ = 'question_categories'

    id = db.Column(db.Integer, primary_key=True)
    naam = db.Column(db.String(100), unique=True, nullable=False, index=True)
    omschrijving = db.Column(db.Text, nullable=False)
    volgorde = db.Column(db.Integer, default=0, nullable=False)
    actief = db.Column(db.Boolean, default=True, nullable=False)
    aangemaakt_op = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    gewijzigd_op = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                             onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relatie naar classificaties
    classificaties = db.relationship('QuestionClassification', back_populates='category', lazy=True)

    def __repr__(self):
        return f'<QuestionCategory {self.naam}>'
