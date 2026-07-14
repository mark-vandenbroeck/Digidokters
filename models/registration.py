from datetime import datetime, date, timezone
from extensions import db


class Registration(db.Model):
    """Registratie van een bezoek aan de Digidokters."""
    __tablename__ = 'registrations'

    id = db.Column(db.Integer, primary_key=True)
    registratienummer = db.Column(db.String(20), unique=True, nullable=False, index=True)
    datum = db.Column(db.Date, nullable=False, default=date.today)
    client = db.Column(db.String(150), nullable=False)
    digidokter_id = db.Column(db.Integer, db.ForeignKey('digidokters.id'), nullable=False)
    nieuwe_klant = db.Column(db.Boolean, default=False, nullable=False)
    herkomst = db.Column(db.String(200), nullable=True)
    onderwerp = db.Column(db.Text, nullable=False)
    leeftijdscategorie_id = db.Column(db.Integer, db.ForeignKey('age_categories.id'), nullable=False)
    toestel_id = db.Column(db.Integer, db.ForeignKey('devices.id'), nullable=False)
    aangemaakt_door_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    aangemaakt_op = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    gewijzigd_op = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                             onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    def __repr__(self):
        return f'<Registration {self.registratienummer}>'

    @staticmethod
    def genereer_registratienummer(jaar=None):
        """Genereer een uniek registratienummer: YYYY-NNNN."""
        if jaar is None:
            jaar = date.today().year
        # Tel bestaande registraties voor dit jaar
        from sqlalchemy import extract
        aantal = db.session.query(Registration).filter(
            extract('year', Registration.datum) == jaar
        ).count()
        return f"{jaar}-{aantal + 1:04d}"