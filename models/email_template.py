from datetime import datetime, timezone
from extensions import db


class EmailTemplate(db.Model):
    """Aanpasbaar e-mailsjabloon per organisatie of op platformniveau."""
    __tablename__ = 'email_templates'

    id = db.Column(db.Integer, primary_key=True)
    organisatie_id = db.Column(db.Integer, db.ForeignKey('organisaties.id', ondelete='CASCADE'), nullable=True, index=True)
    sleutel = db.Column(db.String(50), nullable=False, index=True)
    naam = db.Column(db.String(100), nullable=False)
    onderwerp = db.Column(db.String(200), nullable=False)
    inhoud = db.Column(db.Text, nullable=False)
    beschrijving = db.Column(db.String(255), nullable=True)
    beschikbare_variabelen = db.Column(db.String(255), nullable=True)
    gewijzigd_op = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                             onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        db.UniqueConstraint('organisatie_id', 'sleutel', name='uq_email_template_org_sleutel'),
    )

    def render(self, context: dict) -> tuple[str, str]:
        """Vervang placeholders zoals {naam}, {email}, {login_url}, {activiteit}, etc. in onderwerp en inhoud."""
        rendered_onderwerp = self.onderwerp
        rendered_inhoud = self.inhoud

        for key, value in context.items():
            placeholder = f"{{{key}}}"
            str_val = str(value) if value is not None else ""
            rendered_onderwerp = rendered_onderwerp.replace(placeholder, str_val)
            rendered_inhoud = rendered_inhoud.replace(placeholder, str_val)

        return rendered_onderwerp, rendered_inhoud

    @classmethod
    def get_default_templates(cls) -> dict:
        """Standaardsjablonen (fabrieksinstellingen)."""
        return {
            'welkomstmail': {
                'naam': 'Welkomstmail nieuwe gebruiker',
                'onderwerp': 'Welkom bij Digidokters!',
                'inhoud': """Beste {naam},

Welkom bij de Digidokters-applicatie!

Er is een nieuw account voor jou aangemaakt. Je kunt de applicatie bereiken via onderstaande URL:
{login_url}

Je inloggegevens:
E-mailadres: {email}
{wachtwoord_blok}
Als bijlage sturen we je alvast de gebruikershandleiding mee. Hierin vind je een duidelijke uitleg over het gebruik van de applicatie (zoals het registreren van bezoeken, de agenda en documentbeheer).

Mocht je vragen of problemen hebben, neem dan gerust contact op met de beheerder via {contact_email}.

Met vriendelijke groet,
Digidokters Team
""",
                'beschrijving': 'Welkomstmail die verzonden wordt naar een nieuw aangemaakte gebruiker met inloginstructies en handleiding.',
                'beschikbare_variabelen': '{naam}, {email}, {login_url}, {wachtwoord_blok}, {contact_email}'
            },
            'evaluatie_uitnodiging': {
                'naam': 'Evaluatie - Uitnodiging',
                'onderwerp': 'Evaluatie: {activiteit} op {datum}',
                'inhoud': """Beste {naam},

Bedankt voor je inzet tijdens het {activiteit} op {datum} van {uur_van} tot {uur_tot} ({locatie})!{omschrijving_blok}

We horen graag hoe de sessie verlopen is. Zou je even de tijd willen nemen om het korte evaluatieformulier in te vullen? Dit helpt ons om de sessies continu te verbeteren.

👉 Klik op onderstaande link om het formulier in te vullen:
{link}

Alvast hartelijk dank voor je feedback en medewerking!

Met vriendelijke groet,
Digidokters Team
""",
                'beschrijving': 'E-mailuitnodiging die na afloop van een sessie verstuurd wordt naar aanwezige digidokters.',
                'beschikbare_variabelen': '{naam}, {activiteit}, {datum}, {uur_van}, {uur_tot}, {locatie}, {omschrijving_blok}, {link}'
            },
            'evaluatie_herinnering': {
                'naam': 'Evaluatie - Herinnering',
                'onderwerp': 'Herinnering: Evaluatie voor {activiteit} op {datum}',
                'inhoud': """Beste {naam},

Dit is een vriendelijke herinnering om het evaluatieformulier in te vullen voor het {activiteit} op {datum} van {uur_van} tot {uur_tot} ({locatie}).{omschrijving_blok}

We hebben je feedback nog niet ontvangen. Jouw ervaringen als vrijwilliger zijn voor ons erg waardevol om de werking van Digidokters te versterken.

👉 Klik op onderstaande link om het formulier alsnog in te vullen:
{link}

Hartelijk dank voor je tijd en toewijding!

Met vriendelijke groet,
Digidokters Team
""",
                'beschrijving': 'Herinneringsmail voor digidokters die de evaluatie na afloop nog niet hebben ingevuld.',
                'beschikbare_variabelen': '{naam}, {activiteit}, {datum}, {uur_van}, {uur_tot}, {locatie}, {omschrijving_blok}, {link}'
            }
        }

    @classmethod
    def get_template_voor_organisatie(cls, sleutel: str, organisatie_id: int | None = None):
        """
        Haalt het sjabloon op voor een specifieke organisatie.
        Valt achtereenvolgens terug op:
        1. Sjabloon van de organisatie zelf
        2. Sjabloon van de Sjabloon-organisatie (slug='sjabloon')
        3. Globaal sjabloon (organisatie_id is None)
        4. Fabrieksinstellingen (hardcoded default)
        """
        if organisatie_id is not None:
            tpl = cls.query.filter_by(organisatie_id=organisatie_id, sleutel=sleutel).first()
            if tpl:
                return tpl

            # Fallback naar sjabloon organisatie
            from models.organisatie import Organisatie
            sjabloon_org = Organisatie.query.filter_by(slug='sjabloon', actief=True).first()
            if sjabloon_org and sjabloon_org.id != organisatie_id:
                tpl = cls.query.filter_by(organisatie_id=sjabloon_org.id, sleutel=sleutel).first()
                if tpl:
                    return tpl

        # Fallback naar globaal sjabloon (organisatie_id is None)
        tpl = cls.query.filter(cls.organisatie_id.is_(None), cls.sleutel == sleutel).first()
        if tpl:
            return tpl

        # Fallback naar eerste willekeurige matching sleutel indien aanwezig
        tpl = cls.query.filter_by(sleutel=sleutel).first()
        if tpl:
            return tpl

        # Fallback naar in-memory default
        defaults = cls.get_default_templates()
        if sleutel in defaults:
            data = defaults[sleutel]
            return cls(
                organisatie_id=organisatie_id,
                sleutel=sleutel,
                naam=data['naam'],
                onderwerp=data['onderwerp'],
                inhoud=data['inhoud'],
                beschrijving=data['beschrijving'],
                beschikbare_variabelen=data['beschikbare_variabelen']
            )
        return None

    def __repr__(self):
        return f'<EmailTemplate {self.sleutel} (org_id={self.organisatie_id})>'


def ensure_default_email_templates(organisatie_id=None):
    """Zorgt dat de standaardsjablonen bestaan in de database voor de gegeven organisatie (of globaal)."""
    try:
        defaults = EmailTemplate.get_default_templates()
        for sleutel, data in defaults.items():
            if organisatie_id is not None:
                tpl = EmailTemplate.query.filter_by(organisatie_id=organisatie_id, sleutel=sleutel).first()
            else:
                tpl = EmailTemplate.query.filter(EmailTemplate.organisatie_id.is_(None), EmailTemplate.sleutel == sleutel).first()

            if not tpl:
                tpl = EmailTemplate(
                    organisatie_id=organisatie_id,
                    sleutel=sleutel,
                    naam=data['naam'],
                    onderwerp=data['onderwerp'],
                    inhoud=data['inhoud'],
                    beschrijving=data['beschrijving'],
                    beschikbare_variabelen=data['beschikbare_variabelen']
                )
                db.session.add(tpl)
        db.session.commit()
    except Exception:
        db.session.rollback()

