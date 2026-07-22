from datetime import datetime, timezone
from extensions import db

class AuditLog(db.Model):
    """Audit tabel voor het registreren van database wijzigingen."""
    __tablename__ = 'audit_logs'

    id = db.Column(db.Integer, primary_key=True)
    tabel = db.Column(db.String(100), nullable=False)
    operatie = db.Column(db.String(20), nullable=False)  # 'CREATE', 'UPDATE', 'DELETE'
    record_id = db.Column(db.Integer, nullable=True)
    gebruiker = db.Column(db.String(100), nullable=True)  # Gebruikersnaam of 'Systeem'
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    details = db.Column(db.Text, nullable=True)          # JSON string: { oude_waarden, nieuwe_waarden }
    organisatie_id = db.Column(db.Integer, db.ForeignKey('organisaties.id', ondelete='CASCADE'), nullable=True)

    # Relatie naar Organisatie
    organisatie = db.relationship('Organisatie', backref=db.backref('audit_logs', cascade='all, delete-orphan'))

    def __repr__(self):
        return f'<AuditLog {self.tabel} {self.operatie} op {self.timestamp}>'
