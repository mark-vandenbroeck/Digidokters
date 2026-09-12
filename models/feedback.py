from datetime import datetime, timezone
from extensions import db


class FeedbackItem(db.Model):
    """Feedback item ingediend door een gebruiker (Foutje? of Voorstel)."""
    __tablename__ = 'feedback_items'

    id = db.Column(db.Integer, primary_key=True)
    organisatie_id = db.Column(db.Integer, db.ForeignKey('organisaties.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    type = db.Column(db.String(30), nullable=False, default='voorstel')  # 'foutje' | 'voorstel'
    onderwerp = db.Column(db.String(200), nullable=False)
    beschrijving = db.Column(db.Text, nullable=False)

    # Screenshot opslag
    screenshot_naam = db.Column(db.String(255), nullable=True)
    screenshot_mime = db.Column(db.String(100), nullable=True)
    screenshot_data = db.Column(db.LargeBinary, nullable=True)

    # Statusbeheer (afgesloten door beheerder)
    is_afgesloten = db.Column(db.Boolean, default=False, nullable=False, index=True)
    afgesloten_op = db.Column(db.DateTime, nullable=True)
    afgesloten_door_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # Timestamps
    aangemaakt_op = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    gewijzigd_op = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                             onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relaties
    organisatie = db.relationship('Organisatie', backref=db.backref('feedback_items', lazy=True, cascade='all, delete-orphan'))
    user = db.relationship('User', foreign_keys=[user_id], backref=db.backref('ingediende_feedbacks', lazy=True))
    afgesloten_door = db.relationship('User', foreign_keys=[afgesloten_door_id])
    stemmen = db.relationship('FeedbackVote', backref='feedback', lazy=True, cascade='all, delete-orphan')
    reacties = db.relationship('FeedbackComment', backref='feedback', lazy=True, cascade='all, delete-orphan',
                               order_by='FeedbackComment.aangemaakt_op.asc()')

    @property
    def type_label(self):
        return 'Foutje?' if self.type == 'foutje' else 'Voorstel'

    @property
    def stemmen_voor(self):
        """Aantal duimpjes omhoog (+1)."""
        return sum(1 for s in self.stemmen if s.stem == 1)

    @property
    def stemmen_tegen(self):
        """Aantal duimpjes omlaag (-1)."""
        return sum(1 for s in self.stemmen if s.stem == -1)

    def gebruiker_stem(self, user_id):
        """Geeft de stemwaarde van een specifieke gebruiker (+1, -1 of None)."""
        for s in self.stemmen:
            if s.user_id == user_id:
                return s.stem
        return None

    def __repr__(self):
        return f'<FeedbackItem {self.id}: {self.onderwerp} ({self.type})>'


class FeedbackVote(db.Model):
    """Stem van een gebruiker op een feedback-item (duim omhoog of omlaag)."""
    __tablename__ = 'feedback_stemmen'

    id = db.Column(db.Integer, primary_key=True)
    feedback_id = db.Column(db.Integer, db.ForeignKey('feedback_items.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    stem = db.Column(db.SmallInteger, nullable=False)  # +1 (duim omhoog) of -1 (duim omlaag)
    aangemaakt_op = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        db.UniqueConstraint('feedback_id', 'user_id', name='uq_feedback_user_stem'),
    )

    user = db.relationship('User', foreign_keys=[user_id])

    def __repr__(self):
        return f'<FeedbackVote feedback={self.feedback_id} user={self.user_id} stem={self.stem}>'


class FeedbackComment(db.Model):
    """Bijdrage aan de conversatie van een feedback-item."""
    __tablename__ = 'feedback_reacties'

    id = db.Column(db.Integer, primary_key=True)
    feedback_id = db.Column(db.Integer, db.ForeignKey('feedback_items.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    tekst = db.Column(db.Text, nullable=False)
    aangemaakt_op = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user = db.relationship('User', foreign_keys=[user_id])

    def __repr__(self):
        return f'<FeedbackComment {self.id} on Feedback {self.feedback_id}>'


class FeedbackView(db.Model):
    """Houdt bij wanneer een gebruiker een feedback-pagina voor het laatst bekeken heeft.
    
    Als feedback_id None is, betreft het de algemene feedback-overzichtspagina (/feedback/).
    Als feedback_id gevuld is, betreft het de detailpagina van dat specifieke feedback-item (/feedback/<id>).
    """
    __tablename__ = 'feedback_views'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    feedback_id = db.Column(db.Integer, db.ForeignKey('feedback_items.id', ondelete='CASCADE'), nullable=True, index=True)
    bekeken_op = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'feedback_id', name='uq_user_feedback_view'),
    )

    user = db.relationship('User', foreign_keys=[user_id], backref=db.backref('feedback_views', lazy=True, cascade='all, delete-orphan'))
    feedback = db.relationship('FeedbackItem', foreign_keys=[feedback_id], backref=db.backref('views', lazy=True, cascade='all, delete-orphan'))

    def __repr__(self):
        return f'<FeedbackView user={self.user_id} feedback={self.feedback_id} bekeken_op={self.bekeken_op}>'

