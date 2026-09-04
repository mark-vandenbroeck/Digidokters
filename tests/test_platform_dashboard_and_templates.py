from datetime import datetime, date, timezone
from unittest.mock import patch
from tests.base import BaseTestCase
from extensions import db
from models.user import User
from models.organisatie import Organisatie, UserOrganisatie
from models.digidokter import Digidokter
from models.agenda import AgendaItem
from models.activity_type import ActivityType
from models.location import Location
from models.registration import Registration
from models.age_category import AgeCategory
from models.device import Device
from models.email_template import EmailTemplate, ensure_default_email_templates
from models.evaluation import EvaluationForm, EvaluationQuestion, EvaluationInvitation
from werkzeug.security import generate_password_hash


class TestPlatformDashboardAndEmailTemplates(BaseTestCase):
    def setUp(self):
        super().setUp()
        ensure_default_email_templates()

        # Maak een platformbeheerder
        self.platform_admin = User(
            naam="MarkPlatformAdmin",
            email="platformadmin@test.be",
            wachtwoord_hash=generate_password_hash("adminpass123"),
            rol="platformbeheerder",
            actief=True
        )
        db.session.add(self.platform_admin)
        db.session.commit()

        # Koppel platformbeheerder aan org 1
        uo = UserOrganisatie(user_id=self.platform_admin.id, organisatie_id=1, rol="beheerder", actief=True)
        db.session.add(uo)
        db.session.commit()

    def test_dashboard_access_control(self):
        # 1. Niet ingelogd -> redirect naar login
        resp = self.client.get('/platform/dashboard')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login', resp.headers['Location'])

        # 2. Reguliere medewerker -> toegang geweigerd
        self.login("tim@test.com", "password123")
        resp = self.client.get('/platform/dashboard', follow_redirects=True)
        self.assertIn('U heeft geen toegang tot deze pagina.', resp.get_data(as_text=True))
        self.logout()

        # 3. Platformbeheerder -> succesvol 200
        self.login("platformadmin@test.be", "adminpass123")
        resp = self.client.get('/platform/dashboard')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Platform Dashboard', resp.get_data(as_text=True))
        self.assertIn('Spreiding over Gemeenten & Organisaties', resp.get_data(as_text=True))

    def test_dashboard_aggregates_and_spreiding(self):
        # Maak twee extra organisaties
        org_a = Organisatie(naam="Gemeente Antwerpen", slug="antwerpen", actief=True)
        org_b = Organisatie(naam="Gemeente Gent", slug="gent", actief=True)
        db.session.add_all([org_a, org_b])
        db.session.commit()

        # Voeg vrijwilligers toe
        dd1 = Digidokter(naam="Vrijwilliger 1", organisatie_id=org_a.id, actief=True)
        dd2 = Digidokter(naam="Vrijwilliger 2", organisatie_id=org_a.id, actief=True)
        dd3 = Digidokter(naam="Vrijwilliger 3", organisatie_id=org_b.id, actief=True)
        dd_inactief = Digidokter(naam="Inactieve Vrijwilliger", organisatie_id=org_b.id, actief=False)
        db.session.add_all([dd1, dd2, dd3, dd_inactief])
        db.session.commit()

        # Stamgegevens voor registraties
        cat = AgeCategory(naam="65+", actief=True, organisatie_id=org_a.id)
        dev = Device(naam="Laptop", actief=True, organisatie_id=org_a.id)
        db.session.add_all([cat, dev])
        db.session.commit()

        # Voeg consultaties (registraties) toe
        reg1 = Registration(
            registratienummer="2026-0001",
            datum=date(2026, 3, 1),
            client="Klant 1",
            digidokter_id=dd1.id,
            organisatie_id=org_a.id,
            onderwerp="Vraag over Itsme",
            leeftijdscategorie_id=cat.id,
            toestel_id=dev.id
        )
        reg2 = Registration(
            registratienummer="2026-0002",
            datum=date(2026, 3, 2),
            client="Klant 2",
            digidokter_id=dd2.id,
            organisatie_id=org_a.id,
            onderwerp="Vraag over eBox",
            leeftijdscategorie_id=cat.id,
            toestel_id=dev.id
        )
        reg3 = Registration(
            registratienummer="2026-0001",
            datum=date(2025, 5, 10),
            client="Klant 3",
            digidokter_id=dd3.id,
            organisatie_id=org_b.id,
            onderwerp="Vraag over smartphone",
            leeftijdscategorie_id=cat.id,
            toestel_id=dev.id
        )
        db.session.add_all([reg1, reg2, reg3])
        db.session.commit()

        self.login("platformadmin@test.be", "adminpass123")

        # Totaal weergave (alle jaren)
        resp = self.client.get('/platform/dashboard')
        data = resp.get_data(as_text=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Gemeente Antwerpen', data)
        self.assertIn('Gemeente Gent', data)
        # 3 consultaties in totaal
        self.assertIn('Totaal Consultaties', data)

        # Filter op jaar 2026
        resp_2026 = self.client.get('/platform/dashboard?jaar=2026')
        self.assertEqual(resp_2026.status_code, 200)
        data_2026 = resp_2026.get_data(as_text=True)
        self.assertIn('Gemeente Antwerpen', data_2026)

    def test_email_templates_crud_and_validation(self):
        self.login("platformadmin@test.be", "adminpass123")

        # 1. Overzicht van e-mailsjablonen
        resp = self.client.get('/platform/emailsjablonen')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_data(as_text=True)
        self.assertIn('Aanpasbare E-mailsjablonen', data)
        self.assertIn('Evaluatie - Uitnodiging', data)
        self.assertIn('Evaluatie - Herinnering', data)

        # Haal sjabloon op
        tpl = EmailTemplate.query.filter_by(sleutel='evaluatie_uitnodiging').first()
        self.assertIsNotNone(tpl)

        # 2. Bewerkformulier laden
        resp = self.client.get(f'/platform/emailsjablonen/{tpl.id}/wijzig')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Live Voorbeeldweergave', resp.get_data(as_text=True))

        # 3. Validatiefout bij leeg onderwerp of inhoud
        resp = self.client.post(f'/platform/emailsjablonen/{tpl.id}/wijzig', data={
            'onderwerp': '',
            'inhoud': 'Enige inhoud'
        }, follow_redirects=True)
        self.assertIn('Onderwerp en inhoud zijn verplicht.', resp.get_data(as_text=True))

        # 4. Succesvol bijwerken
        nieuwe_onderwerp = "Jouw feedback over {activiteit} op {datum} gevraagd!"
        nieuwe_inhoud = "Beste {naam},\n\nHartelijk dank voor jouw hulp op {datum} bij {locatie}.\nLink: {link}"
        resp = self.client.post(f'/platform/emailsjablonen/{tpl.id}/wijzig', data={
            'onderwerp': nieuwe_onderwerp,
            'inhoud': nieuwe_inhoud
        }, follow_redirects=True)
        self.assertIn('succesvol opgeslagen', resp.get_data(as_text=True))

        db.session.refresh(tpl)
        self.assertEqual(tpl.onderwerp, nieuwe_onderwerp)
        self.assertEqual(tpl.inhoud, nieuwe_inhoud)

        # 5. Herstel naar fabrieksinstellingen
        resp = self.client.post(f'/platform/emailsjablonen/{tpl.id}/herstel', follow_redirects=True)
        self.assertIn('hersteld naar de standaardtekst', resp.get_data(as_text=True))

        db.session.refresh(tpl)
        self.assertEqual(tpl.onderwerp, "Evaluatie: {activiteit} op {datum}")

    def test_invitation_and_reminder_email_sending_uses_custom_template(self):
        # Maak activiteitstype met evaluatie
        act_type = ActivityType(naam="Digidokter Spreekuur", actief=True, heeft_evaluatie=True, organisatie_id=1)
        loc = Location(naam="Sociaal Huis", actief=True, organisatie_id=1)
        db.session.add_all([act_type, loc])
        db.session.commit()

        # Maak digidokter met user
        user_dd = User(naam="Karel Digidokter", email="karel.dd@test.be", wachtwoord_hash="hash", rol="medewerker")
        db.session.add(user_dd)
        db.session.commit()
        dd = Digidokter(naam="Karel", user_id=user_dd.id, actief=True, organisatie_id=1)
        db.session.add(dd)
        db.session.commit()

        # Maak evaluatieformulier
        form = EvaluationForm(organisatie_id=1, activity_type_id=act_type.id, titel="Evaluatie", actief=True)
        db.session.add(form)
        db.session.commit()
        vr = EvaluationQuestion(form_id=form.id, vraag_tekst="Hoe ging het?", type="multiple_choice", volgorde=1)
        db.session.add(vr)
        db.session.commit()

        # Maak agenda-item in het verleden
        agenda_item = AgendaItem(
            organisatie_id=1,
            type_id=act_type.id,
            locatie_id=loc.id,
            datum=date(2026, 3, 1),
            uur_van="10:00",
            uur_tot="12:00",
            omschrijving="Sessie ondersteuning senioren"
        )
        agenda_item.digidokters.append(dd)
        db.session.add(agenda_item)
        db.session.commit()

        # Pas sjabloon aan met unieke teststring
        tpl_uitnodiging = EmailTemplate.query.filter_by(sleutel='evaluatie_uitnodiging').first()
        tpl_uitnodiging.onderwerp = "UNIEK_ONDERWERP_UITNODIGING: {activiteit}"
        tpl_uitnodiging.inhoud = "UNIEKE_INHOUD_UITNODIGING voor {naam} op link: {link}"

        tpl_herinnering = EmailTemplate.query.filter_by(sleutel='evaluatie_herinnering').first()
        tpl_herinnering.onderwerp = "UNIEK_ONDERWERP_HERINNERING: {activiteit}"
        tpl_herinnering.inhoud = "UNIEKE_INHOUD_HERINNERING voor {naam} op link: {link}"
        db.session.commit()

        # Test versturen uitnodiging
        from routes.evaluations import verstuur_uitnodigingen_voor_sessie, verstuur_herinneringen_voor_sessie

        with patch('routes.evaluations.verstuur_email') as mock_email:
            mock_email.return_value = (True, "OK")

            aantal, namen, fouten = verstuur_uitnodigingen_voor_sessie(agenda_item, host_url="http://localhost:5000")
            self.assertEqual(aantal, 1)
            self.assertEqual(len(fouten), 0)

            # Controleer dat mock_email aangeroepen werd met aangepaste sjabloontekst
            args, _ = mock_email.call_args
            ontvangers, subj, body = args
            self.assertIn("karel.dd@test.be", ontvangers)
            self.assertIn("UNIEK_ONDERWERP_UITNODIGING: Digidokter Spreekuur", subj)
            self.assertIn("UNIEKE_INHOUD_UITNODIGING voor Karel op link:", body)

            inv = EvaluationInvitation.query.filter_by(agenda_item_id=agenda_item.id, digidokter_id=dd.id).first()
            self.assertIsNotNone(inv)
            self.assertFalse(inv.is_ingevuld)
            self.assertEqual(inv.herinnering_aantal, 0)

        # Test versturen herinnering
        with patch('routes.evaluations.verstuur_email') as mock_reminder_email:
            mock_reminder_email.return_value = (True, "OK")

            aantal_her, namen_her, fouten_her = verstuur_herinneringen_voor_sessie(agenda_item, host_url="http://localhost:5000")
            self.assertEqual(aantal_her, 1)
            self.assertEqual(len(fouten_her), 0)

            # Controleer dat mock_email aangeroepen werd met herinneringssjabloon
            args, _ = mock_reminder_email.call_args
            ontvangers, subj, body = args
            self.assertIn("karel.dd@test.be", ontvangers)
            self.assertIn("UNIEK_ONDERWERP_HERINNERING: Digidokter Spreekuur", subj)
            self.assertIn("UNIEKE_INHOUD_HERINNERING voor Karel op link:", body)

            # Controleer tracking op EvaluationInvitation
            db.session.refresh(inv)
            self.assertEqual(inv.herinnering_aantal, 1)
            self.assertIsNotNone(inv.herinnering_verzonden_op)

        # Test route voor herinneringen via POST
        self.login("admin@test.com", "password123")
        with patch('routes.evaluations.verstuur_email') as mock_route_email:
            mock_route_email.return_value = (True, "OK")
            resp = self.client.post(f'/agenda/{agenda_item.id}/verstuur-herinneringen', follow_redirects=True)
            self.assertIn('Evaluatie-herinnering succesvol verstuurd', resp.get_data(as_text=True))
