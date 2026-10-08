"""Model voor verzonden communicatieberichten en e-mailhistoriek."""
import json
from datetime import datetime, timezone
from extensions import db


class CommunicatieLog(db.Model):
    """Bewaart verzonden e-mails en mededelingen met metadata en historiek."""
    __tablename__ = 'communicatie_logs'

    id = db.Column(db.Integer, primary_key=True)
    organisatie_id = db.Column(db.Integer, db.ForeignKey('organisaties.id', ondelete='CASCADE'), nullable=True, index=True)
    afzender_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    afzender_naam = db.Column(db.String(150), nullable=False)
    afzender_email = db.Column(db.String(150), nullable=False)
    
    type = db.Column(db.String(50), nullable=False, default='organisatie')  # 'platform' of 'organisatie'
    doelgroep = db.Column(db.String(100), nullable=True)  # bijv. 'alle', 'beheerders', 'medewerkers', 'alle_beheerders'
    onderwerp = db.Column(db.String(255), nullable=False)
    inhoud = db.Column(db.Text, nullable=False)
    
    # JSON-string met ontvangers: [{'naam': ..., 'email': ..., 'organisatie': ...}] of lijst met e-mails
    ontvangers_json = db.Column(db.Text, nullable=False)
    aantal_ontvangers = db.Column(db.Integer, nullable=False, default=0)
    
    status = db.Column(db.String(50), nullable=False, default='verzonden')
    verzonden_op = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    # Relationships
    organisatie = db.relationship('Organisatie', backref=db.backref('communicatie_logs', cascade='all, delete-orphan', lazy='dynamic'))
    afzender = db.relationship('User', backref=db.backref('verzonden_communicatie', lazy='dynamic'))

    @property
    def ontvangers_lijst(self) -> list:
        """Retourneert de gedeserialiseerde lijst van ontvangers."""
        if not self.ontvangers_json:
            return []
        try:
            return json.loads(self.ontvangers_json)
        except Exception:
            return [e.strip() for e in self.ontvangers_json.split(',') if e.strip()]

    @property
    def ontvangers_preview(self) -> str:
        """Korte tekstuele samenvatting van de eerste ontvangers."""
        lijst = self.ontvangers_lijst
        if not lijst:
            return "Geen ontvangers"
        
        namen = []
        for item in lijst:
            if isinstance(item, dict):
                namen.append(item.get('naam') or item.get('email'))
            else:
                namen.append(str(item))
                
        if len(namen) <= 3:
            return ", ".join(namen)
        return f"{', '.join(namen[:3])} en {len(namen) - 3} andere(n)"

    @property
    def geformatteerde_datum(self) -> str:
        """Geformatteerde datum en tijdstip van verzending."""
        if not self.verzonden_op:
            return ""
        return self.verzonden_op.strftime('%d-%m-%Y om %H:%M')

    def __repr__(self):
        return f'<CommunicatieLog id={self.id} type={self.type} onderwerp="{self.onderwerp[:30]}">'
