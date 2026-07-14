from app import db


class Digidokter(db.Model):
    """Vrijwilliger / Digidokter."""
    __tablename__ = 'digidokters'

    id = db.Column(db.Integer, primary_key=True)
    naam = db.Column(db.String(100), nullable=False)
    actief = db.Column(db.Boolean, default=True, nullable=False)
    volgorde = db.Column(db.Integer, default=0, nullable=False)

    # Relatie
    registraties = db.relationship('Registration', backref='digidokter', lazy=True)

    def __repr__(self):
        return f'<Digidokter {self.naam}>'
