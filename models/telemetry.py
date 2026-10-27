"""Modellen voor telemetrie, paginagebruik en foutmonitoring."""
from datetime import datetime, timezone, date
from extensions import db


class PageViewStat(db.Model):
    """Geaggregeerde statistieken van paginabezoeken per dag en endpoint."""
    __tablename__ = 'page_view_stats'

    id = db.Column(db.Integer, primary_key=True)
    datum = db.Column(db.Date, default=date.today, nullable=False, index=True)
    endpoint = db.Column(db.String(100), nullable=False, index=True)
    pad = db.Column(db.String(255), nullable=True)
    label = db.Column(db.String(100), nullable=True)
    organisatie_id = db.Column(db.Integer, db.ForeignKey('organisaties.id', ondelete='CASCADE'), nullable=True, index=True)
    aantal_hits = db.Column(db.Integer, default=1, nullable=False)

    organisatie = db.relationship('Organisatie')

    __table_args__ = (
        db.UniqueConstraint('datum', 'endpoint', 'organisatie_id', name='uq_pageview_datum_endpoint_org'),
    )

    def __repr__(self):
        return f'<PageViewStat {self.datum} {self.endpoint} ({self.aantal_hits}x)>'


class SystemErrorLog(db.Model):
    """Log van applicatiefouten, rate-limits en beveiligingsincidenten voor monitoring."""
    __tablename__ = 'system_error_logs'

    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    status_code = db.Column(db.Integer, nullable=False, default=500, index=True)
    type_fout = db.Column(db.String(100), nullable=True)  # '500_Error', 'RateLimit', 'LoginFailed', 'AuthError'
    bericht = db.Column(db.Text, nullable=True)
    stacktrace = db.Column(db.Text, nullable=True)
    endpoint = db.Column(db.String(100), nullable=True)
    pad = db.Column(db.String(255), nullable=True)
    methode = db.Column(db.String(10), nullable=True)
    ip_adres = db.Column(db.String(50), nullable=True)
    gebruiker = db.Column(db.String(100), nullable=True)
    organisatie_id = db.Column(db.Integer, db.ForeignKey('organisaties.id', ondelete='SET NULL'), nullable=True)
    is_opgelost = db.Column(db.Boolean, default=False, nullable=False, index=True)
    opgelost_op = db.Column(db.DateTime, nullable=True)
    opgelost_door = db.Column(db.String(100), nullable=True)

    organisatie = db.relationship('Organisatie')

    def __repr__(self):
        return f'<SystemErrorLog {self.status_code} {self.type_fout} op {self.timestamp}>'
