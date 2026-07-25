from datetime import datetime, date, timezone
from extensions import db


class Registration(db.Model):
    """Registratie van een bezoek aan de Digidokters."""
    __tablename__ = 'registrations'

    id = db.Column(db.Integer, primary_key=True)
    registratienummer = db.Column(db.String(20), nullable=False, index=True)
    datum = db.Column(db.Date, nullable=False, default=date.today)
    client = db.Column(db.String(150), nullable=False)
    digidokter_id = db.Column(db.Integer, db.ForeignKey('digidokters.id'), nullable=False)
    nieuwe_klant = db.Column(db.Boolean, default=False, nullable=False)
    herkomst_id = db.Column(db.Integer, db.ForeignKey('herkomst.id'), nullable=True)
    geslacht = db.Column(db.String(10), nullable=True)
    onderwerp = db.Column(db.Text, nullable=False)
    leeftijdscategorie_id = db.Column(db.Integer, db.ForeignKey('age_categories.id'), nullable=False)
    toestel_id = db.Column(db.Integer, db.ForeignKey('devices.id'), nullable=False)
    aangemaakt_door_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    aangemaakt_op = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    gewijzigd_op = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                             onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    organisatie_id = db.Column(db.Integer, db.ForeignKey('organisaties.id'), nullable=False)

    __table_args__ = (
        db.UniqueConstraint('organisatie_id', 'registratienummer', name='uq_registration_org_num'),
    )

    def __repr__(self):
        return f'<Registration {self.registratienummer}>'

    @staticmethod
    def genereer_registratienummer(organisatie_id, jaar=None):
        """Genereer een uniek registratienummer: YYYY-NNNN voor de specifieke organisatie."""
        if jaar is None:
            jaar = date.today().year
        # Zoek het hoogste nummer van dit jaar in de organisatie
        pattern = f"{jaar}-%"
        max_num = db.session.query(db.func.max(Registration.registratienummer)).filter(
            Registration.organisatie_id == organisatie_id,
            Registration.registratienummer.like(pattern)
        ).scalar()
        
        if max_num:
            try:
                sequence_part = int(max_num.split('-')[1])
                next_seq = sequence_part + 1
            except (ValueError, IndexError):
                next_seq = 1
        else:
            next_seq = 1
            
        return f"{jaar}-{next_seq:04d}"