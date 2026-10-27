from datetime import datetime, timezone
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
    datum = db.Column(db.Date, nullable=False, index=True)
    uur_van = db.Column(db.String(5), nullable=False)  # HH:MM format
    uur_tot = db.Column(db.String(5), nullable=False)  # HH:MM format
    type_id = db.Column(db.Integer, db.ForeignKey('activity_types.id'), nullable=False, index=True)
    locatie_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=False, index=True)
    omschrijving = db.Column(db.Text, nullable=True)
    organisatie_id = db.Column(db.Integer, db.ForeignKey('organisaties.id'), nullable=False, index=True)
    
    # Velden voor terugkerende reeksen
    reeks_id = db.Column(db.String(50), nullable=True)
    is_terugkerend = db.Column(db.Boolean, default=False, nullable=False)
    interval = db.Column(db.String(20), nullable=True)  # 'dagelijks', 'wekelijks', 'maandelijks'
    einddatum = db.Column(db.Date, nullable=True)
    gewijzigd_op = db.Column(db.DateTime, nullable=True)

    # Relationships
    type = db.relationship('ActivityType', backref=db.backref('agenda_items', lazy=True))
    locatie = db.relationship('Location', backref=db.backref('agenda_items', lazy=True))
    digidokters = db.relationship('Digidokter', secondary=agenda_digidokters, backref=db.backref('agenda_items', lazy='dynamic'))
    edit_lock = db.relationship('AgendaItemLock', back_populates='agenda_item', uselist=False, cascade='all, delete-orphan')

    __table_args__ = (
        db.Index('ix_agenda_items_org_datum', 'organisatie_id', 'datum'),
    )

    def __repr__(self):
        return f'<AgendaItem {self.datum} {self.uur_van}-{self.uur_tot}>'


class AgendaItemLock(db.Model):
    """Vergrendeling voor gelijktijdige bewerking van aanwezigheden op een agenda-item."""
    __tablename__ = 'agenda_item_locks'

    id = db.Column(db.Integer, primary_key=True)
    agenda_item_id = db.Column(db.Integer, db.ForeignKey('agenda_items.id', ondelete='CASCADE'), nullable=False, unique=True, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    user_naam = db.Column(db.String(100), nullable=False)
    locked_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)

    agenda_item = db.relationship('AgendaItem', back_populates='edit_lock')
    user = db.relationship('User')

    def is_expired(self) -> bool:
        now = datetime.now(timezone.utc)
        exp = self.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return exp < now

    def __repr__(self):
        return f'<AgendaItemLock item={self.agenda_item_id} user={self.user_naam} expires={self.expires_at}>'


