from tests.base import BaseTestCase
from extensions import db
from models.user import User
from models.organisatie import Organisatie, UserOrganisatie
from models.digidokter import Digidokter
from werkzeug.security import generate_password_hash


class TestDigidokterEmailValidation(BaseTestCase):
    def setUp(self):
        super().setUp()
        # 1. Login as Admin
        with self.client.session_transaction() as sess:
            sess['organisatie_id'] = self.org.id
        self.client.post('/login', data={'email': 'admin@test.com', 'wachtwoord': 'password123'}, follow_redirects=True)

        # 2. Create second organization for multi-tenant testing
        self.org2 = Organisatie(naam="Organisatie 2", slug="org-2", actief=True)
        db.session.add(self.org2)
        db.session.commit()

        # 3. Create extra user member of Org 1 and Org 2
        self.vrijwilliger_user = User(
            naam="VrijwilligerJan",
            email="jan.vrijwilliger@test.com",
            wachtwoord_hash=generate_password_hash("password123"),
            rol="medewerker",
            actief=True
        )
        db.session.add(self.vrijwilliger_user)
        db.session.commit()

        # Link to Org 1 and Org 2
        uo1 = UserOrganisatie(user_id=self.vrijwilliger_user.id, organisatie_id=self.org.id, rol="medewerker", actief=True)
        uo2 = UserOrganisatie(user_id=self.vrijwilliger_user.id, organisatie_id=self.org2.id, rol="medewerker", actief=True)
        admin_uo2 = UserOrganisatie(user_id=self.admin_user.id, organisatie_id=self.org2.id, rol="beheerder", actief=True)
        db.session.add_all([uo1, uo2, admin_uo2])
        db.session.commit()

    def test_digidokter_aanmaken_met_bestaand_email_succes(self):
        res = self.client.post('/beheer/digidokters/nieuw', data={'email': 'jan.vrijwilliger@test.com', 'actief': 'on'}, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"succesvol toegevoegd", res.data)

        # Controleer dat de digidokter is aangemaakt en gekoppeld aan de gebruiker
        dd = Digidokter.query.filter_by(organisatie_id=self.org.id, user_id=self.vrijwilliger_user.id).first()
        self.assertIsNotNone(dd)
        self.assertEqual(dd.naam, "VrijwilligerJan")
        self.assertEqual(dd.email, "jan.vrijwilliger@test.com")

    def test_digidokter_aanmaken_met_niet_bestaand_email_geblokkeerd(self):
        res = self.client.post('/beheer/digidokters/nieuw', data={'email': 'bestaatniet@test.com', 'actief': 'on'}, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Er bestaat geen gebruiker met e-mailadres", res.data)

    def test_digidokter_dubbel_binnen_zelfde_organisatie_geblokkeerd(self):
        # Maak 1e digidokter aan
        self.client.post('/beheer/digidokters/nieuw', data={'email': 'jan.vrijwilliger@test.com', 'actief': 'on'}, follow_redirects=True)

        # Probeer 2e digidokter met hetzelfde e-mailadres aan te maken in de zelfde organisatie
        res = self.client.post('/beheer/digidokters/nieuw', data={'email': 'jan.vrijwilliger@test.com', 'actief': 'on'}, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Er bestaat in deze organisatie al een Digidokter", res.data)

    def test_digidokter_zelfde_email_in_andere_organisatie_toegestaan(self):
        # 1. Digidokter in Org 1
        self.client.post('/beheer/digidokters/nieuw', data={'email': 'jan.vrijwilliger@test.com', 'actief': 'on'}, follow_redirects=True)

        # 2. Switch sessie naar Org 2
        with self.client.session_transaction() as sess:
            sess['organisatie_id'] = self.org2.id

        # 3. Digidokter in Org 2 aanmaken met hetzelfde e-mailadres (toegestaan voor multi-tenant)
        res = self.client.post('/beheer/digidokters/nieuw', data={'email': 'jan.vrijwilliger@test.com', 'actief': 'on'}, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"succesvol toegevoegd", res.data)

        # Verifieer dat in beide organisaties een Digidokter gekoppeld staat
        dd1 = Digidokter.query.filter_by(organisatie_id=self.org.id, user_id=self.vrijwilliger_user.id).first()
        dd2 = Digidokter.query.filter_by(organisatie_id=self.org2.id, user_id=self.vrijwilliger_user.id).first()
        self.assertIsNotNone(dd1)
        self.assertIsNotNone(dd2)
        self.assertNotEqual(dd1.id, dd2.id)

    def test_digidokter_verwijderen_zonder_registraties_toegestaan(self):
        self.client.post('/beheer/digidokters/nieuw', data={'email': 'jan.vrijwilliger@test.com', 'actief': 'on'}, follow_redirects=True)
        dd = Digidokter.query.filter_by(organisatie_id=self.org.id, user_id=self.vrijwilliger_user.id).first()
        self.assertIsNotNone(dd)

        res = self.client.post(f'/beheer/digidokters/{dd.id}/verwijderen', follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"is succesvol verwijderd", res.data)
        self.assertIsNone(db.session.get(Digidokter, dd.id))

    def test_digidokter_verwijderen_met_registraties_geblokkeerd(self):
        from models.registration import Registration
        from models.age_category import AgeCategory
        from models.device import Device

        self.client.post('/beheer/digidokters/nieuw', data={'email': 'jan.vrijwilliger@test.com', 'actief': 'on'}, follow_redirects=True)
        dd = Digidokter.query.filter_by(organisatie_id=self.org.id, user_id=self.vrijwilliger_user.id).first()

        cat = AgeCategory.query.filter_by(organisatie_id=self.org.id).first()
        dev = Device.query.filter_by(organisatie_id=self.org.id).first()
        reg = Registration(
            registratienummer="2026-0001",
            client="Test Client",
            digidokter_id=dd.id,
            leeftijdscategorie_id=cat.id,
            toestel_id=dev.id,
            onderwerp="Hulpvraag",
            organisatie_id=self.org.id
        )
        db.session.add(reg)
        db.session.commit()

        res = self.client.post(f'/beheer/digidokters/{dd.id}/verwijderen', follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"kan niet worden verwijderd omdat er nog", res.data)
        self.assertIsNotNone(db.session.get(Digidokter, dd.id))

    def test_digidokter_naam_behouden_bij_koppelen_email(self):
        briek = Digidokter(naam="Briek", actief=True, volgorde=99, organisatie_id=self.org.id)
        db.session.add(briek)
        db.session.commit()

        res = self.client.post(f'/beheer/digidokters/{briek.id}/wijzig', data={'email': 'jan.vrijwilliger@test.com', 'actief': 'on'}, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        briek_db = db.session.get(Digidokter, briek.id)
        self.assertEqual(briek_db.naam, "Briek")
        self.assertEqual(briek_db.user_id, self.vrijwilliger_user.id)
        self.assertEqual(briek_db.email, "jan.vrijwilliger@test.com")
