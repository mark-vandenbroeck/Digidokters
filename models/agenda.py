from extensions import db

agenda_digidokters = db.Table(
    'agenda_digidokters',
    db.Column('agenda_item_id', db.Integer, db.ForeignKey('agenda_items.id', ondelete='CASCADE'), primary_key=True),
    db.Column('digidokter_id', db.Integer, db.ForeignKey('digidokters.id', ondelete='CASCADE'), primary_key=True)
)

class AgendaItem(db.Model):
    """Agenda-item / Activiteit."""
    __tablename__ = 'agenda_items'

    id = db.Column(db.Integer, primary_key=True)
    datum = db.Column(db.Date, nullable=False)
    uur_van = db.Column(db.String(5), nullable=False)  # HH:MM format
    uur_tot = db.Column(db.String(5), nullable=False)  # HH:MM format
    type_id = db.Column(db.Integer, db.ForeignKey('activity_types.id'), nullable=False)
    locatie_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=False)
    omschrijving = db.Column(db.Text, nullable=True)
    organisatie_id = db.Column(db.Integer, db.ForeignKey('organisaties.id'), nullable=False)

    # Relationships
    type = db.relationship('ActivityType', backref=db.backref('agenda_items', lazy=True))
    locatie = db.relationship('Location', backref=db.backref('agenda_items', lazy=True))
    digidokters = db.relationship('Digidokter', secondary=agenda_digidokters, backref=db.backref('agenda_items', lazy='dynamic'))

    def __repr__(self):
        return f'<AgendaItem {self.datum} {self.uur_van}-{self.uur_tot}>'
