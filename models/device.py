from app import db


class Device(db.Model):
    """Toestel waarmee de bezoeker geholpen werd."""
    __tablename__ = 'devices'

    id = db.Column(db.Integer, primary_key=True)
    naam = db.Column(db.String(100), nullable=False)
    actief = db.Column(db.Boolean, default=True, nullable=False)
    volgorde = db.Column(db.Integer, default=0, nullable=False)

    # Relatie
    registraties = db.relationship('Registration', backref='toestel', lazy=True)

    def __repr__(self):
        return f'<Device {self.naam}>'
