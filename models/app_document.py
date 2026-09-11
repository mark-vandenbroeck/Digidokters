from datetime import datetime, timezone
from extensions import db


class AppFolder(db.Model):
    """Map binnen de globale app-documentatie structuur (gemeenschappelijk voor alle organisaties)."""
    __tablename__ = 'app_mappen'

    id = db.Column(db.Integer, primary_key=True)
    parent_id = db.Column(db.Integer, db.ForeignKey('app_mappen.id', ondelete='CASCADE'), nullable=True, index=True)
    naam = db.Column(db.String(100), nullable=False)
    aangemaakt_op = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    aangemaakt_door_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    # Relaties
    aangemaakt_door = db.relationship('User', foreign_keys=[aangemaakt_door_id])

    # Self-referencing relatie voor hiërarchie
    parent = db.relationship('AppFolder', remote_side=[id], backref=db.backref('children', cascade='all, delete-orphan', lazy=True))

    def __repr__(self):
        return f'<AppFolder {self.naam} (ID: {self.id})>'


class AppDocument(db.Model):
    """Document / bestand opgeslagen in globale app-documentatie."""
    __tablename__ = 'app_documenten'

    id = db.Column(db.Integer, primary_key=True)
    map_id = db.Column(db.Integer, db.ForeignKey('app_mappen.id', ondelete='CASCADE'), nullable=True, index=True)

    bestandsnaam = db.Column(db.String(255), nullable=False)
    omschrijving = db.Column(db.Text, nullable=True)
    type = db.Column(db.String(20), nullable=False)  # bijv. 'pdf', 'docx', 'xlsx', 'png'
    mime_type = db.Column(db.String(100), nullable=False)  # bijv. 'application/pdf'
    bestandsgrootte = db.Column(db.Integer, nullable=False)  # in bytes
    inhoud = db.Column(db.LargeBinary, nullable=False)  # Binaire inhoud van het document
    tekst_inhoud = db.Column(db.Text, nullable=True)  # Geëxtraheerde platte tekst voor zoekindex
    versie = db.Column(db.Integer, default=1, nullable=False)

    aangemaakt_op = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    aangemaakt_door_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    gewijzigd_op = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    gewijzigd_door_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # Relaties
    map = db.relationship('AppFolder', backref=db.backref('documenten', lazy=True, cascade='all, delete-orphan'))
    aangemaakt_door = db.relationship('User', foreign_keys=[aangemaakt_door_id])
    gewijzigd_door = db.relationship('User', foreign_keys=[gewijzigd_door_id])

    def __repr__(self):
        return f'<AppDocument {self.bestandsnaam} v{self.versie} (ID: {self.id})>'
