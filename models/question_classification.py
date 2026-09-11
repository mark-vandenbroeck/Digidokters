from datetime import datetime, timezone
from extensions import db


class QuestionClassification(db.Model):
    """Resultaat van Gemini AI classificatie van een consultatie-onderwerp."""
    __tablename__ = 'question_classifications'

    id = db.Column(db.Integer, primary_key=True)
    registration_id = db.Column(db.Integer, db.ForeignKey('registrations.id', ondelete='CASCADE'), unique=True, nullable=False, index=True)
    category_id = db.Column(db.Integer, db.ForeignKey('question_categories.id', ondelete='SET NULL'), nullable=True, index=True)
    
    zekerheid = db.Column(db.Float, nullable=True)  # bv. 0.95 (95%)
    toelichting = db.Column(db.Text, nullable=True)  # Uitleg/motivatie van Gemini of beheerder
    model_naam = db.Column(db.String(50), nullable=True)  # bv. 'gemini-3.5-flash'
    
    is_handmatig_aangepast = db.Column(db.Boolean, default=False, nullable=False)
    aangepast_door_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    
    geclassificeerd_op = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    gewijzigd_op = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                             onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relaties
    registration = db.relationship('Registration', backref=db.backref('classification', uselist=False, cascade='all, delete-orphan'))
    category = db.relationship('QuestionCategory', back_populates='classificaties')
    aangepast_door = db.relationship('User', foreign_keys=[aangepast_door_id])

    def __repr__(self):
        return f'<QuestionClassification reg={self.registration_id} cat={self.category_id}>'
