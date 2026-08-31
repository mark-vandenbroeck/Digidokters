from datetime import datetime
import json
from extensions import db


class EvaluationForm(db.Model):
    """Evaluatieformulier gekoppeld aan een activiteitstype binnen een organisatie."""
    __tablename__ = 'evaluatie_formulieren'

    id = db.Column(db.Integer, primary_key=True)
    organisatie_id = db.Column(db.Integer, db.ForeignKey('organisaties.id', ondelete='CASCADE'), nullable=False, index=True)
    activity_type_id = db.Column(db.Integer, db.ForeignKey('activity_types.id', ondelete='CASCADE'), nullable=False, index=True)
    titel = db.Column(db.String(150), default='Evaluatieformulier', nullable=False)
    toelichting = db.Column(db.Text, nullable=True)
    actief = db.Column(db.Boolean, default=True, nullable=False)
    aangemaakt_op = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    gewijzigd_op = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.UniqueConstraint('organisatie_id', 'activity_type_id', name='uq_eval_form_org_activity_type'),
    )

    # Relaties
    organisatie = db.relationship('Organisatie', backref=db.backref('evaluatie_formulieren', lazy=True, cascade='all, delete-orphan'))
    activity_type = db.relationship('ActivityType', backref=db.backref('evaluatie_formulier', uselist=False, lazy=True, cascade='all, delete-orphan'))
    vragen = db.relationship('EvaluationQuestion', backref='form', lazy=True, order_by='EvaluationQuestion.volgorde', cascade='all, delete-orphan')
    reacties = db.relationship('EvaluationResponse', backref='form', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<EvaluationForm {self.id}: {self.titel}>'


class EvaluationQuestion(db.Model):
    """Vraag binnen een evaluatieformulier."""
    __tablename__ = 'evaluatie_vragen'

    id = db.Column(db.Integer, primary_key=True)
    form_id = db.Column(db.Integer, db.ForeignKey('evaluatie_formulieren.id', ondelete='CASCADE'), nullable=False, index=True)
    vraag_tekst = db.Column(db.Text, nullable=False)
    type = db.Column(db.String(30), default='multiple_choice', nullable=False)  # 'multiple_choice' of 'open_tekst'
    opties = db.Column(db.JSON, nullable=True)  # List van strings, bv. ["Niet veel", "Een beetje", "Redelijk wat", "Veel", "Heel veel"]
    volgorde = db.Column(db.Integer, default=0, nullable=False)
    verplicht = db.Column(db.Boolean, default=True, nullable=False)

    @property
    def opties_lijst(self):
        if not self.opties:
            return []
        if isinstance(self.opties, list):
            return self.opties
        if isinstance(self.opties, str):
            try:
                parsed = json.loads(self.opties)
                if isinstance(parsed, list):
                    return parsed
            except Exception:
                return [opt.strip() for opt in self.opties.split(',') if opt.strip()]
        return []

    def __repr__(self):
        return f'<EvaluationQuestion {self.id}: {self.vraag_tekst[:30]}>'


class EvaluationResponse(db.Model):
    """Ingevulde evaluatierespons voor een specifieke sessie/activiteit door een digidokter/gebruiker."""
    __tablename__ = 'evaluatie_reacties'

    id = db.Column(db.Integer, primary_key=True)
    organisatie_id = db.Column(db.Integer, db.ForeignKey('organisaties.id', ondelete='CASCADE'), nullable=False, index=True)
    agenda_item_id = db.Column(db.Integer, db.ForeignKey('agenda_items.id', ondelete='CASCADE'), nullable=False, index=True)
    form_id = db.Column(db.Integer, db.ForeignKey('evaluatie_formulieren.id', ondelete='CASCADE'), nullable=False, index=True)
    digidokter_id = db.Column(db.Integer, db.ForeignKey('digidokters.id', ondelete='SET NULL'), nullable=True, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    ingediend_op = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    antwoorden = db.Column(db.JSON, nullable=False)  # Dict: {"<vraag_id>": "antwoord"}

    __table_args__ = (
        db.UniqueConstraint('agenda_item_id', 'digidokter_id', name='uq_eval_response_agenda_digidokter'),
    )

    # Relaties
    organisatie = db.relationship('Organisatie', backref=db.backref('evaluatie_reacties', lazy=True, cascade='all, delete-orphan'))
    agenda_item = db.relationship('AgendaItem', backref=db.backref('evaluatie_reacties', lazy=True, cascade='all, delete-orphan'))
    digidokter = db.relationship('Digidokter', backref=db.backref('evaluatie_reacties', lazy=True))
    user = db.relationship('User', backref=db.backref('evaluatie_reacties', lazy=True))

    def __repr__(self):
        return f'<EvaluationResponse {self.id}: Agenda {self.agenda_item_id} by Digidokter {self.digidokter_id}>'


class EvaluationInvitation(db.Model):
    """Uitnodigingstoken voor een digidokter om een evaluatie in te vullen na afloop van een sessie."""
    __tablename__ = 'evaluatie_uitnodigingen'

    id = db.Column(db.Integer, primary_key=True)
    agenda_item_id = db.Column(db.Integer, db.ForeignKey('agenda_items.id', ondelete='CASCADE'), nullable=False, index=True)
    digidokter_id = db.Column(db.Integer, db.ForeignKey('digidokters.id', ondelete='CASCADE'), nullable=False, index=True)
    token = db.Column(db.String(64), unique=True, nullable=False, index=True)
    verzonden_op = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    is_ingevuld = db.Column(db.Boolean, default=False, nullable=False)

    __table_args__ = (
        db.UniqueConstraint('agenda_item_id', 'digidokter_id', name='uq_eval_invitation_agenda_digidokter'),
    )

    agenda_item = db.relationship('AgendaItem', backref=db.backref('evaluatie_uitnodigingen', lazy=True, cascade='all, delete-orphan'))
    digidokter = db.relationship('Digidokter', backref=db.backref('evaluatie_uitnodigingen', lazy=True, cascade='all, delete-orphan'))

    def __repr__(self):
        return f'<EvaluationInvitation {self.id}: Agenda {self.agenda_item_id} -> Digidokter {self.digidokter_id}>'
