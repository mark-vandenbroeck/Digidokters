from extensions import db

class ActivityType(db.Model):
    """Type van activiteit (bijv. Digidokters, Digicafé, Lunchvergadering)."""
    __tablename__ = 'activity_types'

    id = db.Column(db.Integer, primary_key=True)
    naam = db.Column(db.String(100), nullable=False)
    actief = db.Column(db.Boolean, default=True, nullable=False)
    volgorde = db.Column(db.Integer, default=0, nullable=False)
    organisatie_id = db.Column(db.Integer, db.ForeignKey('organisaties.id'), nullable=False)

    __table_args__ = (
        db.UniqueConstraint('organisatie_id', 'naam', name='uq_activity_type_org_naam'),
    )

    def __repr__(self):
        return f'<ActivityType {self.naam}>'
