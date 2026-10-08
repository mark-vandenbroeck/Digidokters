"""
Unit tests voor multitenant e-mailsjablonen en welkomstmails.
"""
from unittest.mock import patch
from werkzeug.security import generate_password_hash
from tests.base import BaseTestCase
from extensions import db
from models.user import User
from models.organisatie import Organisatie, UserOrganisatie
from models.digidokter import Digidokter
from models.activity_type import ActivityType
from models.location import Location
from models.agenda import AgendaItem
from models.evaluation import EvaluationForm, EvaluationQuestion, EvaluationInvitation
from models.email_template import EmailTemplate, ensure_default_email_templates
from utils.mail import stuur_welkomst_email


class TestEmailTemplatesMultitenant(BaseTestCase):

    def setUp(self):
        super().setUp()
        # Maak 2 organisaties aan
        self.org1 = Organisatie(naam="Organisatie Alpha", slug="org-alpha", actief=True)
        self.org2 = Organisatie(naam="Organisatie Beta", slug="org-beta", actief=True)
        db.session.add_all([self.org1, self.org2])
        db.session.commit()

        # Users voor org 1
        self.admin1 = User(
            naam="Admin Alpha",
            email="admin.alpha@test.be",
            wachtwoord_hash=generate_password_hash("AdminPass123!"),
            rol="beheerder",
            actief=True,
            moet_wachtwoord_wijzigen=False
        )
        db.session.add(self.admin1)
        db.session.commit()
        db.session.add(UserOrganisatie(user_id=self.admin1.id, organisatie_id=self.org1.id, rol="beheerder", actief=True))

        # Users voor org 2
        self.admin2 = User(
            naam="Admin Beta",
            email="admin.beta@test.be",
            wachtwoord_hash=generate_password_hash("AdminPass123!"),
            rol="beheerder",
            actief=True,
            moet_wachtwoord_wijzigen=False
        )
        db.session.add(self.admin2)
        db.session.commit()
        db.session.add(UserOrganisatie(user_id=self.admin2.id, organisatie_id=self.org2.id, rol="beheerder", actief=True))

        # Medewerker in org 1
        self.medewerker1 = User(
            naam="Medewerker Alpha",
            email="medewerker.alpha@test.be",
            wachtwoord_hash=generate_password_hash("MedewerkerPass123!"),
            rol="medewerker",
            actief=True,
            moet_wachtwoord_wijzigen=False
        )
        db.session.add(self.medewerker1)
        db.session.commit()
        db.session.add(UserOrganisatie(user_id=self.medewerker1.id, organisatie_id=self.org1.id, rol="medewerker", actief=True))

        db.session.commit()

        # Zorg dat beide organisaties templates hebben
        ensure_default_email_templates(self.org1.id)
        ensure_default_email_templates(self.org2.id)

    def login_as(self, email, password, org_id):
        res = self.client.post('/login', data={
            'email': email,
            'wachtwoord': password
        }, follow_redirects=True)
        self.select_organisatie(org_id)
        return res

    def test_admin_can_view_and_edit_org_templates(self):
        """Test dat beheerder van org 1 zijn templates ziet en kan bewerken."""
        self.login_as("admin.alpha@test.be", "AdminPass123!", self.org1.id)

        # 1. Overzichtspagina
        resp = self.client.get('/beheer/emailsjablonen')
        self.assertEqual(resp.status_code, 200)
        content = resp.get_data(as_text=True)
        self.assertIn("E-mailsjablonen", content)
        self.assertIn("Welkomstmail nieuwe gebruiker", content)
        self.assertIn("Evaluatie - Uitnodiging", content)
        self.assertIn("Evaluatie - Herinnering", content)

        # 2. Wijzig welkomstmail voor org 1
        tpl1 = EmailTemplate.query.filter_by(organisatie_id=self.org1.id, sleutel='welkomstmail').first()
        self.assertIsNotNone(tpl1)

        resp = self.client.post(f'/beheer/emailsjablonen/{tpl1.id}/wijzig', data={
            'onderwerp': 'Welkom bij Organisatie Alpha!',
            'inhoud': 'Hallo {naam}, welkom bij Alpha! Je login is {email}. Wachtwoord: {wachtwoord_blok}'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("succesvol opgeslagen", resp.get_data(as_text=True))

        db.session.refresh(tpl1)
        self.assertEqual(tpl1.onderwerp, 'Welkom bij Organisatie Alpha!')

        # Controleer dat org 2 sjabloon NIET is aangepast (multitenant isolatie)
        tpl2 = EmailTemplate.query.filter_by(organisatie_id=self.org2.id, sleutel='welkomstmail').first()
        self.assertEqual(tpl2.onderwerp, 'Welkom bij Digidokters!')

    def test_admin_cannot_edit_other_org_template(self):
        """Test dat admin van org 1 niet het sjabloon van org 2 kan wijzigen."""
        self.login_as("admin.alpha@test.be", "AdminPass123!", self.org1.id)

        tpl2 = EmailTemplate.query.filter_by(organisatie_id=self.org2.id, sleutel='welkomstmail').first()
        resp = self.client.post(f'/beheer/emailsjablonen/{tpl2.id}/wijzig', data={
            'onderwerp': 'Gehackt!',
            'inhoud': 'Gehackte inhoud'
        }, follow_redirects=True)
        self.assertIn("Sjabloon behoort niet tot de huidige organisatie", resp.get_data(as_text=True))

        db.session.refresh(tpl2)
        self.assertNotEqual(tpl2.onderwerp, 'Gehackt!')

    def test_medewerker_cannot_access_email_templates(self):
        """Test dat een gewone medewerker geen toegang heeft tot e-mailsjablonen."""
        self.login_as("medewerker.alpha@test.be", "MedewerkerPass123!", self.org1.id)

        resp = self.client.get('/beheer/emailsjablonen', follow_redirects=True)
        self.assertIn("U heeft geen toegang tot deze pagina", resp.get_data(as_text=True))

    def test_stuur_welkomst_email_uses_org_template_and_shows_email(self):
        """Test dat welkomstmail verzonden wordt met het specifieke organisatiesjabloon en het e-mailadres toont."""
        tpl1 = EmailTemplate.query.filter_by(organisatie_id=self.org1.id, sleutel='welkomstmail').first()
        tpl1.onderwerp = "UNIEK_ONDERWERP_ALPHA"
        tpl1.inhoud = "Beste {naam},\nLogin via {email}\n{wachtwoord_blok}"
        db.session.commit()

        with patch('utils.mail.verstuur_email') as mock_send:
            mock_send.return_value = (True, "OK")

            success, msg = stuur_welkomst_email(
                gebruiker_email="piet@test.be",
                gebruiker_naam="Piet Pienter",
                tijdelijk_wachtwoord="PietPass123!",
                organisatie_id=self.org1.id
            )
            self.assertTrue(success)
            mock_send.assert_called_once()
            _, kwargs = mock_send.call_args
            self.assertEqual(kwargs.get('ontvangers'), ["piet@test.be"])
            self.assertEqual(kwargs.get('onderwerp'), "UNIEK_ONDERWERP_ALPHA")
            body = kwargs.get('inhoud_tekst', '')
            self.assertIn("Login via piet@test.be", body)
            self.assertIn("PietPass123!", body)

    def test_stuur_welkomst_email_fallback_shows_email_not_username(self):
        """Test dat zelfs zonder template in DB, de fallback het e-mailadres toont."""
        with patch('models.email_template.EmailTemplate.get_template_voor_organisatie', return_value=None):
            with patch('utils.mail.verstuur_email') as mock_send:
                mock_send.return_value = (True, "OK")

                success, msg = stuur_welkomst_email(
                    gebruiker_email="sarah@test.be",
                    gebruiker_naam="Sarah Slim",
                    tijdelijk_wachtwoord="SarahPass123!",
                    organisatie_id=self.org1.id
                )
                self.assertTrue(success)
                _, kwargs = mock_send.call_args
                body = kwargs.get('inhoud_tekst', '')
                self.assertIn("E-mailadres: sarah@test.be", body)
                self.assertNotIn("Gebruikersnaam: Sarah Slim", body)

    def test_admin_reset_template_to_default(self):
        """Test herstel naar fabrieksinstellingen voor een organisatiesjabloon."""
        self.login_as("admin.alpha@test.be", "AdminPass123!", self.org1.id)

        tpl1 = EmailTemplate.query.filter_by(organisatie_id=self.org1.id, sleutel='welkomstmail').first()
        tpl1.onderwerp = "Aangepast onderwerp"
        db.session.commit()

        resp = self.client.post(f'/beheer/emailsjablonen/{tpl1.id}/herstel', follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("hersteld naar de standaardtekst", resp.get_data(as_text=True))

        db.session.refresh(tpl1)
        self.assertEqual(tpl1.onderwerp, "Welkom bij Digidokters!")

    def test_stuur_welkomst_email_attaches_app_document_guide(self):
        """Test dat de actuele handleiding uit AppDocumenten (App documentatie -> Gebruikershandleidingen) als bijlage meegestuurd wordt."""
        from models.app_document import AppFolder, AppDocument
        
        folder = AppFolder(naam="Gebruikershandleidingen", aangemaakt_door_id=self.admin1.id)
        db.session.add(folder)
        db.session.flush()

        doc_bytes = b"BINARY_HANDLEIDING_CONTENT_V2"
        doc = AppDocument(
            map_id=folder.id,
            bestandsnaam="Digidokters_Gebruikershandleiding.docx",
            omschrijving="Actuele handleiding",
            type="docx",
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            bestandsgrootte=len(doc_bytes),
            inhoud=doc_bytes,
            aangemaakt_door_id=self.admin1.id
        )
        db.session.add(doc)
        db.session.commit()

        with patch('utils.mail.verstuur_email') as mock_send:
            mock_send.return_value = (True, "OK")

            success, msg = stuur_welkomst_email(
                gebruiker_email="johan@test.be",
                gebruiker_naam="Johan",
                tijdelijk_wachtwoord="JohanPass123!",
                organisatie_id=self.org1.id
            )
            self.assertTrue(success)
            _, kwargs = mock_send.call_args
            bijlagen = kwargs.get('bijlagen', [])
            self.assertEqual(len(bijlagen), 1)
            self.assertEqual(bijlagen[0]['naam'], "Digidokters_Gebruikershandleiding.docx")
            self.assertEqual(bijlagen[0]['content_bytes'], b"BINARY_HANDLEIDING_CONTENT_V2")

