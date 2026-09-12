from extensions import db


class Device(db.Model):
    """Toestel waarmee de bezoeker geholpen werd."""
    __tablename__ = 'devices'

    id = db.Column(db.Integer, primary_key=True)
    naam = db.Column(db.String(100), nullable=False)
    actief = db.Column(db.Boolean, default=True, nullable=False)
    volgorde = db.Column(db.Integer, default=0, nullable=False)
    organisatie_id = db.Column(db.Integer, db.ForeignKey('organisaties.id'), nullable=False)
    mapped_to_id = db.Column(db.Integer, db.ForeignKey('devices.id'), nullable=True)

    __table_args__ = (
        db.UniqueConstraint('organisatie_id', 'naam', name='uq_device_org_naam'),
    )

    # Relaties
    registraties = db.relationship('Registration', backref='toestel', lazy=True)
    mapped_to = db.relationship('Device', remote_side=[id], backref=db.backref('mapped_from', lazy='dynamic'))

    @property
    def effectieve_naam(self):
        """Geeft de naam van de gemapte actieve optie indien inactief en gemapt."""
        item = self
        seen = {self.id}
        while not item.actief and item.mapped_to:
            item = item.mapped_to
            if item.id in seen:
                break
            seen.add(item.id)
        return item.naam

    @property
    def effectief_toestel(self):
        """Geeft het effectieve (gemapte) toestel-object terug."""
        item = self
        seen = {self.id}
        while not item.actief and item.mapped_to:
            item = item.mapped_to
            if item.id in seen:
                break
            seen.add(item.id)
        return item

    def __repr__(self):
        return f'<Device {self.naam}>'
