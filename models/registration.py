from datetime import datetime, date, timezone
from extensions import db


class Registration(db.Model):
    """Registratie van een bezoek aan de Digidokters."""
    __tablename__ = 'registrations'

    id = db.Column(db.Integer, primary_key=True)
    registratienummer = db.Column(db.String(20), nullable=False, index=True)
    datum = db.Column(db.Date, nullable=False, default=date.today)
    client = db.Column(db.String(150), nullable=False)
    digidokter_id = db.Column(db.Integer, db.ForeignKey('digidokters.id'), nullable=False, index=True)
    nieuwe_klant = db.Column(db.Boolean, default=False, nullable=False)
    herkomst_id = db.Column(db.Integer, db.ForeignKey('herkomst.id'), nullable=True, index=True)
    gender_identity_id = db.Column(db.Integer, db.ForeignKey('gender_identities.id', ondelete='SET NULL'), nullable=True, index=True)
    gender_identity = db.relationship('GenderIdentity', backref=db.backref('registraties', lazy=True))
    onderwerp = db.Column(db.Text, nullable=False)
    leeftijdscategorie_id = db.Column(db.Integer, db.ForeignKey('age_categories.id'), nullable=False, index=True)
    toestel_id = db.Column(db.Integer, db.ForeignKey('devices.id'), nullable=False, index=True)
    locatie_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=True, index=True)
    locatie = db.relationship('Location', backref=db.backref('registraties', lazy=True))
    aangemaakt_door_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    aangemaakt_op = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    gewijzigd_op = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                             onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    organisatie_id = db.Column(db.Integer, db.ForeignKey('organisaties.id'), nullable=False, index=True)
    organisatie = db.relationship('Organisatie', backref=db.backref('registraties', lazy=True))

    def __init__(self, **kwargs):
        if 'organisatie_id' in kwargs:
            self.organisatie_id = kwargs.pop('organisatie_id')
        super().__init__(**kwargs)

    @property
    def geslacht(self):
        return self.gender_identity.naam if self.gender_identity else None

    @geslacht.setter
    def geslacht(self, val):
        if val is None or val == '':
            self.gender_identity_id = None
        elif isinstance(val, int):
            self.gender_identity_id = val
        elif isinstance(val, str):
            val_clean = val.strip()
            if val_clean.isdigit():
                self.gender_identity_id = int(val_clean)
            else:
                from models.gender_identity import GenderIdentity
                query = GenderIdentity.query.filter(
                    db.func.lower(GenderIdentity.naam) == val_clean.lower()
                )
                if self.organisatie_id:
                    query = query.filter(GenderIdentity.organisatie_id == self.organisatie_id)
                g = query.first()
                if g:
                    self.gender_identity_id = g.id

    __table_args__ = (
        db.UniqueConstraint('organisatie_id', 'registratienummer', name='uq_registration_org_num'),
        db.Index('ix_registrations_org_datum', 'organisatie_id', 'datum'),
        db.Index('ix_registrations_org_digidokter', 'organisatie_id', 'digidokter_id'),
        db.Index('ix_registrations_org_locatie', 'organisatie_id', 'locatie_id'),
        db.Index('ix_registrations_org_gender', 'organisatie_id', 'gender_identity_id'),
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