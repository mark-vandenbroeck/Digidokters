from tests.base import BaseTestCase
from datetime import date
from extensions import db
from models.gender_identity import GenderIdentity
from models.registration import Registration
from models.organisatie import Organisatie
from utils.tenant import seed_organisatie_defaults


class TestGenderIdentity(BaseTestCase):
    def test_seeding_defaults_creates_man_and_vrouw(self):
        # Maak nieuwe organisatie en seed defaults
        org = Organisatie(naam="Test Organisatie Gender", slug="test-org-gender", actief=True)
        db.session.add(org)
        db.session.commit()

        seed_organisatie_defaults(org.id)

        genders = GenderIdentity.query.filter_by(organisatie_id=org.id).order_by(GenderIdentity.volgorde).all()
        self.assertEqual(len(genders), 2)
        self.assertEqual(genders[0].naam, "Man")
        self.assertTrue(genders[0].actief)
        self.assertEqual(genders[1].naam, "Vrouw")
        self.assertTrue(genders[1].actief)
        self.assertEqual(genders[0].omschrijving, "Man")

    def test_admin_genderidentiteiten_crud(self):
        self.login("AdminMark", "password123")
        self.select_organisatie(self.org.id)

        # 1. Bekijk lijst
        res = self.client.get('/beheer/genderidentiteiten')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        self.assertIn("Genderidentiteit", html)
        self.assertIn("Man", html)
        self.assertIn("Vrouw", html)

        # 2. Voeg nieuw item toe
        res_add = self.client.post('/beheer/genderidentiteiten/nieuw', data={
            'naam': 'Non-binair',
            'actief': 'on'
        }, follow_redirects=True)
        self.assertEqual(res_add.status_code, 200)
        self.assertIn('Non-binair', res_add.data.decode('utf-8'))

        nb = GenderIdentity.query.filter_by(organisatie_id=self.org.id, naam='Non-binair').first()
        self.assertIsNotNone(nb)
        self.assertTrue(nb.actief)

        # 3. Wijzig item
        res_edit = self.client.post(f'/beheer/genderidentiteiten/{nb.id}/wijzig', data={
            'naam': 'X / Non-binair',
            'actief': 'on'
        }, follow_redirects=True)
        self.assertEqual(res_edit.status_code, 200)
        self.assertIn('X / Non-binair', res_edit.data.decode('utf-8'))

        nb_updated = db.session.get(GenderIdentity, nb.id)
        self.assertEqual(nb_updated.naam, 'X / Non-binair')

        # 4. Toggle status
        res_toggle = self.client.get(f'/beheer/genderidentiteiten/{nb.id}/toggle', follow_redirects=True)
        self.assertEqual(res_toggle.status_code, 200)
        self.assertFalse(nb_updated.actief)

        # 5. Volgorde wijzigen
        man = GenderIdentity.query.filter_by(organisatie_id=self.org.id, naam='Man').first()
        vrouw = GenderIdentity.query.filter_by(organisatie_id=self.org.id, naam='Vrouw').first()
        self.client.get(f'/beheer/genderidentiteiten/{vrouw.id}/volgorde/omhoog', follow_redirects=True)

        vrouw_refreshed = db.session.get(GenderIdentity, vrouw.id)
        man_refreshed = db.session.get(GenderIdentity, man.id)
        self.assertLess(vrouw_refreshed.volgorde, man_refreshed.volgorde)

        # 6. Verwijderen
        res_del = self.client.post(f'/beheer/genderidentiteiten/{nb.id}/verwijderen', follow_redirects=True)
        self.assertEqual(res_del.status_code, 200)
        self.assertIsNone(db.session.get(GenderIdentity, nb.id))

    def test_verwijderen_geblokkeerd_bij_gekoppelde_registraties(self):
        self.login("AdminMark", "password123")
        self.select_organisatie(self.org.id)

        # Maak registratie met geslacht 'Man'
        reg = Registration(
            registratienummer="2026-9001",
            datum=date(2026, 4, 1),
            client="Jan Tester",
            digidokter_id=self.digidokter.id,
            leeftijdscategorie_id=self.age_category.id,
            toestel_id=self.device.id,
            organisatie_id=self.org.id,
            geslacht="Man",
            onderwerp="Vraag over smartphone"
        )
        db.session.add(reg)
        db.session.commit()

        man = GenderIdentity.query.filter_by(organisatie_id=self.org.id, naam='Man').first()
        res_del = self.client.post(f'/beheer/genderidentiteiten/{man.id}/verwijderen', follow_redirects=True)
        self.assertEqual(res_del.status_code, 200)
        self.assertIn('kan niet worden verwijderd omdat er nog', res_del.data.decode('utf-8'))
        self.assertIsNotNone(db.session.get(GenderIdentity, man.id))

    def test_registratie_gebruikt_genderidentiteit_dropdown(self):
        self.login("UserTim", "password123")
        self.select_organisatie(self.org.id)

        # Voeg custom optie toe via db
        custom_g = GenderIdentity(naam="Andere", actief=True, volgorde=2, organisatie_id=self.org.id)
        db.session.add(custom_g)
        db.session.commit()

        # GET formulier controleert dropdown opties
        res_get = self.client.get('/registraties/nieuw')
        self.assertEqual(res_get.status_code, 200)
        html_get = res_get.data.decode('utf-8')
        self.assertIn('<option value="Man"', html_get)
        self.assertIn('<option value="Vrouw"', html_get)
        self.assertIn('<option value="Andere"', html_get)

        # POST registratie met 'Andere'
        data = {
            'datum': '2026-04-05',
            'client': 'Bezoeker Divers',
            'digidokter_id': self.digidokter.id,
            'nieuwe_klant': 'ja',
            'geslacht': 'Andere',
            'onderwerp': 'Hulp bij eBox en itsme',
            'leeftijdscategorie_id': self.age_category.id,
            'toestel_id': self.device.id
        }
        res_post = self.client.post('/registraties/nieuw', data=data, follow_redirects=True)
        self.assertEqual(res_post.status_code, 200)

        reg = Registration.query.filter_by(client='Bezoeker Divers').first()
        self.assertIsNotNone(reg)
        self.assertEqual(reg.geslacht, 'Andere')

        # Detail pagina bekijken
        res_view = self.client.get(f'/registraties/{reg.id}')
        self.assertEqual(res_view.status_code, 200)
        self.assertIn('Andere', res_view.data.decode('utf-8'))

        # Filter in overzichtslijst
        res_list = self.client.get('/registraties?geslacht=Andere')
        self.assertEqual(res_list.status_code, 200)
        self.assertIn('Bezoeker Divers', res_list.data.decode('utf-8'))
