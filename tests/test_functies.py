from tests.base import BaseTestCase
from extensions import db
from models.functie import Functie, user_functies
from models.user import User
from models.organisatie import Organisatie, UserOrganisatie
from utils.tenant import seed_organisatie_defaults


class TestFuncties(BaseTestCase):
    def test_seeding_defaults_creates_three_functies(self):
        org = Organisatie(naam="Test Organisatie Functies", slug="test-org-functies", actief=True)
        db.session.add(org)
        db.session.commit()

        seed_organisatie_defaults(org.id)

        functies = Functie.query.filter_by(organisatie_id=org.id).order_by(Functie.volgorde).all()
        self.assertEqual(len(functies), 3)
        namen = [f.naam for f in functies]
        self.assertEqual(namen, ["Digidokter", "Digihelper", "Lesgever"])
        for f in functies:
            self.assertTrue(f.actief)

    def test_admin_functies_crud(self):
        self.login("AdminMark", "password123")
        self.select_organisatie(self.org.id)

        # 1. Bekijk lijst
        res = self.client.get('/beheer/functies')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        self.assertIn("Functies", html)
        self.assertIn("Digidokter", html)
        self.assertIn("Digihelper", html)
        self.assertIn("Lesgever", html)

        # 2. Voeg nieuwe functie toe
        res_add = self.client.post('/beheer/functies/nieuw', data={
            'naam': 'Digicoach',
            'actief': 'on'
        }, follow_redirects=True)
        self.assertEqual(res_add.status_code, 200)
        self.assertIn('Digicoach', res_add.data.decode('utf-8'))

        coach = Functie.query.filter_by(organisatie_id=self.org.id, naam='Digicoach').first()
        self.assertIsNotNone(coach)
        self.assertTrue(coach.actief)

        # 3. Wijzig functie
        res_edit = self.client.post(f'/beheer/functies/{coach.id}/wijzig', data={
            'naam': 'Senior Digicoach',
            'actief': 'on'
        }, follow_redirects=True)
        self.assertEqual(res_edit.status_code, 200)
        self.assertIn('Senior Digicoach', res_edit.data.decode('utf-8'))

        coach_updated = db.session.get(Functie, coach.id)
        self.assertEqual(coach_updated.naam, 'Senior Digicoach')

        # 4. Toggle status
        res_toggle = self.client.get(f'/beheer/functies/{coach.id}/toggle', follow_redirects=True)
        self.assertEqual(res_toggle.status_code, 200)
        self.assertFalse(coach_updated.actief)

        # 5. Volgorde
        helper = Functie.query.filter_by(organisatie_id=self.org.id, naam='Digihelper').first()
        self.client.get(f'/beheer/functies/{helper.id}/volgorde/omhoog', follow_redirects=True)
        dok = Functie.query.filter_by(organisatie_id=self.org.id, naam='Digidokter').first()
        self.assertLess(db.session.get(Functie, helper.id).volgorde, db.session.get(Functie, dok.id).volgorde)

        # 6. Verwijderen
        res_del = self.client.post(f'/beheer/functies/{coach.id}/verwijderen', follow_redirects=True)
        self.assertEqual(res_del.status_code, 200)
        self.assertIsNone(db.session.get(Functie, coach.id))

    def test_user_creation_with_functies_and_phone(self):
        self.login("AdminMark", "password123")
        self.select_organisatie(self.org.id)

        fn_dok = Functie.query.filter_by(organisatie_id=self.org.id, naam='Digidokter').first()
        fn_les = Functie.query.filter_by(organisatie_id=self.org.id, naam='Lesgever').first()

        # Maak nieuwe gebruiker aan met 2 functies en een telefoonnummer
        res = self.client.post('/beheer/gebruikers/nieuw', data={
            'naam': 'Karel Vrijwilliger',
            'email': 'karel@test.com',
            'telefoonnummer': '+32 470 99 88 77',
            'rol': 'medewerker',
            'wachtwoord': 'Tijdelijk123!',
            'actief': 'on',
            'functie_ids': [str(fn_dok.id), str(fn_les.id)]
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        user = User.query.filter_by(email='karel@test.com').first()
        self.assertIsNotNone(user)
        self.assertEqual(user.telefoonnummer, '+32 470 99 88 77')

        user_fns = user.get_functies_voor_organisatie(self.org.id)
        self.assertEqual(len(user_fns), 2)
        fn_namen = [f.naam for f in user_fns]
        self.assertIn('Digidokter', fn_namen)
        self.assertIn('Lesgever', fn_namen)

        # Controleer weergave in gebruikerslijst
        res_list = self.client.get('/beheer/gebruikers')
        self.assertEqual(res_list.status_code, 200)
        html_list = res_list.data.decode('utf-8')
        self.assertIn('+32 470 99 88 77', html_list)
        self.assertIn('Digidokter', html_list)
        self.assertIn('Lesgever', html_list)

        # Wijzig functies en telefoonnummer
        fn_help = Functie.query.filter_by(organisatie_id=self.org.id, naam='Digihelper').first()
        res_edit = self.client.post(f'/beheer/gebruikers/{user.id}/wijzig', data={
            'naam': 'Karel Vrijwilliger',
            'email': 'karel@test.com',
            'telefoonnummer': '+32 470 11 22 33',
            'rol': 'medewerker',
            'actief': 'on',
            'functie_ids': [str(fn_help.id)]
        }, follow_redirects=True)
        self.assertEqual(res_edit.status_code, 200)

        user_updated = db.session.get(User, user.id)
        self.assertEqual(user_updated.telefoonnummer, '+32 470 11 22 33')
        user_fns_updated = user_updated.get_functies_voor_organisatie(self.org.id)
        self.assertEqual(len(user_fns_updated), 1)
        self.assertEqual(user_fns_updated[0].naam, 'Digihelper')

    def test_delete_functie_blocked_when_assigned_to_user(self):
        self.login("AdminMark", "password123")
        self.select_organisatie(self.org.id)

        fn_dok = Functie.query.filter_by(organisatie_id=self.org.id, naam='Digidokter').first()
        self.medewerker_user.functies.append(fn_dok)
        db.session.commit()

        # Probeer functie te verwijderen
        res_del = self.client.post(f'/beheer/functies/{fn_dok.id}/verwijderen', follow_redirects=True)
        self.assertEqual(res_del.status_code, 200)
        self.assertIn('kan niet worden verwijderd omdat deze nog is toegekend aan', res_del.data.decode('utf-8'))
        self.assertIsNotNone(db.session.get(Functie, fn_dok.id))

    def test_user_self_service_profile_phone_and_functies(self):
        self.login("UserTim", "password123")
        self.select_organisatie(self.org.id)

        fn_dok = Functie.query.filter_by(organisatie_id=self.org.id, naam='Digidokter').first()
        fn_les = Functie.query.filter_by(organisatie_id=self.org.id, naam='Lesgever').first()
        self.medewerker_user.functies.append(fn_dok)
        db.session.commit()

        # GET profielpagina
        res_get = self.client.get('/wachtwoord')
        self.assertEqual(res_get.status_code, 200)
        html_get = res_get.data.decode('utf-8')
        self.assertIn('Digidokter', html_get)
        self.assertIn('Lesgever', html_get)
        self.assertIn(f'value="{fn_dok.id}"', html_get)

        # POST profiel update met telefoonnummer en gewijzigde functies (Digihelper & Lesgever)
        fn_help = Functie.query.filter_by(organisatie_id=self.org.id, naam='Digihelper').first()
        res_post = self.client.post('/wachtwoord', data={
            'email': 'usertim@nieuwedomein.be',
            'telefoonnummer': '+32 499 12 34 56',
            'functie_ids': [str(fn_help.id), str(fn_les.id)]
        }, follow_redirects=True)
        self.assertEqual(res_post.status_code, 200)

        tim = db.session.get(User, self.medewerker_user.id)
        self.assertEqual(tim.email, 'usertim@nieuwedomein.be')
        self.assertEqual(tim.telefoonnummer, '+32 499 12 34 56')
        tim_fns = tim.get_functies_voor_organisatie(self.org.id)
        self.assertEqual(len(tim_fns), 2)
        tim_fn_namen = [f.naam for f in tim_fns]
        self.assertIn('Digihelper', tim_fn_namen)
        self.assertIn('Lesgever', tim_fn_namen)
        self.assertNotIn('Digidokter', tim_fn_namen)
