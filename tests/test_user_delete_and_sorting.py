from tests.base import BaseTestCase
from extensions import db
from models.user import User
from models.organisatie import UserOrganisatie
from models.digidokter import Digidokter
from models.registration import Registration
from werkzeug.security import generate_password_hash
from datetime import date


class TestUserDeleteAndSorting(BaseTestCase):
    def login_admin(self):
        with self.client.session_transaction() as sess:
            sess['organisatie_id'] = self.org.id
        self.client.post('/login', data={
            'email': 'admin@test.com',
            'wachtwoord': 'password123'
        }, follow_redirects=True)

    def test_verwijder_gebruiker_zonder_registraties(self):
        self.login_admin()

        # Maak een nieuwe testgebruiker aan zonder registraties
        u = User(
            naam="VerwijderMij",
            email="verwijder@test.com",
            wachtwoord_hash=generate_password_hash("password123"),
            rol="medewerker",
            actief=True
        )
        db.session.add(u)
        db.session.commit()

        uo = UserOrganisatie(user_id=u.id, organisatie_id=self.org.id, rol="medewerker", actief=True)
        db.session.add(uo)
        db.session.commit()

        u_id = u.id
        res = self.client.post(f'/beheer/gebruikers/{u_id}/verwijderen', follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"is succesvol verwijderd", res.data)
        self.assertIsNone(db.session.get(User, u_id))

    def test_verwijder_gebruiker_met_gekoppelde_digidokter_geblokkeerd(self):
        self.login_admin()

        u = User(
            naam="HeeftDigidokter",
            email="dduser@test.com",
            wachtwoord_hash=generate_password_hash("password123"),
            rol="medewerker",
            actief=True
        )
        db.session.add(u)
        db.session.commit()

        uo = UserOrganisatie(user_id=u.id, organisatie_id=self.org.id, rol="medewerker", actief=True)
        dd = Digidokter(naam="HeeftDigidokter", user_id=u.id, organisatie_id=self.org.id, actief=True)
        db.session.add_all([uo, dd])
        db.session.commit()

        u_id = u.id
        res = self.client.post(f'/beheer/gebruikers/{u_id}/verwijderen', follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"kan niet worden verwijderd omdat er nog een Digidokter aan dit account is gekoppeld", res.data)
        self.assertIsNotNone(db.session.get(User, u_id))

    def test_verwijder_eigen_account_geblokkeerd(self):
        self.login_admin()
        res = self.client.post(f'/beheer/gebruikers/{self.admin_user.id}/verwijderen', follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"U kunt uw eigen account niet verwijderen", res.data)

    def test_gebruikers_sortering(self):
        self.login_admin()
        res = self.client.get('/beheer/gebruikers?sort_by=naam&direction=desc')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"AdminMark", res.data)

        res_email = self.client.get('/beheer/gebruikers?sort_by=email&direction=asc')
        self.assertEqual(res_email.status_code, 200)

    def test_registraties_sortering(self):
        self.login_admin()
        res = self.client.get('/registraties?sort_by=client&direction=asc')
        self.assertEqual(res.status_code, 200)

        res_nr = self.client.get('/registraties?sort_by=nummer&direction=desc')
        self.assertEqual(res_nr.status_code, 200)

    def test_koppelingen_sortering(self):
        self.admin_user.rol = 'platformbeheerder'
        db.session.commit()
        self.login_admin()
        res = self.client.get('/platform/koppelingen?sort_by=organisatie&direction=desc')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Bestaande koppelingen", res.data)
