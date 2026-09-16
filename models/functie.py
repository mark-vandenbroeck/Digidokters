from extensions import db


# Many-to-Many koppeltabel tussen User en Functie
user_functies = db.Table(
    'user_functies',
    db.Column('user_id', db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
    db.Column('functie_id', db.Integer, db.ForeignKey('functies.id', ondelete='CASCADE'), primary_key=True)
)


class Functie(db.Model):
    """Functie van een gebruiker/vrijwilliger binnen een organisatie (stamgegeven)."""
    __tablename__ = 'functies'

    id = db.Column(db.Integer, primary_key=True)
    naam = db.Column(db.String(100), nullable=False)
    actief = db.Column(db.Boolean, default=True, nullable=False)
    volgorde = db.Column(db.Integer, default=0, nullable=False)
    organisatie_id = db.Column(db.Integer, db.ForeignKey('organisaties.id'), nullable=False)

    __table_args__ = (
        db.UniqueConstraint('organisatie_id', 'naam', name='uq_functie_org_naam'),
    )

    @property
    def omschrijving(self):
        return self.naam

    @omschrijving.setter
    def omschrijving(self, val):
        self.naam = val

    def __repr__(self):
        return f'<Functie {self.naam}>'
