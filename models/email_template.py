from datetime import datetime, timezone
from extensions import db


class EmailTemplate(db.Model):
    """Aanpasbaar e-mailsjabloon voor platformbeheer."""
    __tablename__ = 'email_templates'

    id = db.Column(db.Integer, primary_key=True)
    sleutel = db.Column(db.String(50), unique=True, nullable=False, index=True)
    naam = db.Column(db.String(100), nullable=False)
    onderwerp = db.Column(db.String(200), nullable=False)
    inhoud = db.Column(db.Text, nullable=False)
    beschrijving = db.Column(db.String(255), nullable=True)
    beschikbare_variabelen = db.Column(db.String(255), nullable=True)
    gewijzigd_op = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                             onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    def render(self, context: dict) -> tuple[str, str]:
        """Vervang placeholders zoals {naam}, {activiteit}, etc. in onderwerp en inhoud."""
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

    def __repr__(self):
        return f'<EmailTemplate {self.sleutel}>'


def ensure_default_email_templates():
    """Zorgt dat de standaardsjablonen bestaan in de database."""
    try:
        defaults = EmailTemplate.get_default_templates()
        for sleutel, data in defaults.items():
            tpl = EmailTemplate.query.filter_by(sleutel=sleutel).first()
            if not tpl:
                tpl = EmailTemplate(
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

