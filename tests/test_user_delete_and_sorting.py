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

    def test_cross_tenant_gebruiker_verwijderen_geblokkeerd(self):
        from models.organisatie import Organisatie
        self.login_admin()

        # Maak org 2 met een gebruiker die uitsluitend in org 2 zit
        org2 = Organisatie(naam="Gemeente B", slug="gemeente-b", actief=True)
        db.session.add(org2)
        db.session.commit()

        u_org2 = User(
            naam="UserOrg2",
            email="user.org2@test.be",
            wachtwoord_hash=generate_password_hash("password123"),
            rol="medewerker",
            actief=True
        )
        db.session.add(u_org2)
        db.session.commit()
        db.session.add(UserOrganisatie(user_id=u_org2.id, organisatie_id=org2.id, rol="medewerker", actief=True))
        db.session.commit()

        # Admin van org 1 probeert gebruiker van org 2 te verwijderen -> 404
        res = self.client.post(f'/beheer/gebruikers/{u_org2.id}/verwijderen')
        self.assertEqual(res.status_code, 404)
        # Gebruiker bestaat nog
        self.assertIsNotNone(db.session.get(User, u_org2.id))

    def test_verwijder_multi_organisatie_gebruiker_ontkoppelt_alleen(self):
        from models.organisatie import Organisatie
        self.login_admin()

        # Maak org 2
        org2 = Organisatie(naam="Gemeente C", slug="gemeente-c", actief=True)
        db.session.add(org2)
        db.session.commit()

        # Maak gebruiker gekoppeld aan ZOWEL org 1 als org 2
        u_multi = User(
            naam="MultiOrgUser",
            email="multi@test.be",
            wachtwoord_hash=generate_password_hash("password123"),
            rol="medewerker",
            actief=True
        )
        db.session.add(u_multi)
        db.session.commit()
        db.session.add(UserOrganisatie(user_id=u_multi.id, organisatie_id=self.org.id, rol="medewerker", actief=True))
        db.session.add(UserOrganisatie(user_id=u_multi.id, organisatie_id=org2.id, rol="medewerker", actief=True))
        db.session.commit()

        # Verwijderen in org 1 ontkoppelt alleen org 1
        res = self.client.post(f'/beheer/gebruikers/{u_multi.id}/verwijderen', follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn("is ontkoppeld van deze organisatie. Het gebruikersaccount blijft behouden voor andere organisaties.", res.get_data(as_text=True))

        # Koppeling met org 1 is weg
        self.assertIsNone(UserOrganisatie.query.filter_by(user_id=u_multi.id, organisatie_id=self.org.id).first())
        # Maar account en koppeling met org 2 bestaan nog!
        self.assertIsNotNone(UserOrganisatie.query.filter_by(user_id=u_multi.id, organisatie_id=org2.id).first())
        self.assertIsNotNone(db.session.get(User, u_multi.id))

    def test_verwijder_gebruiker_met_documenten_en_feedback(self):
        from models.document import Folder, Document
        from models.feedback import FeedbackItem, FeedbackVote, FeedbackComment
        self.login_admin()

        u = User(
            naam="ContentCreator",
            email="creator@test.be",
            wachtwoord_hash=generate_password_hash("password123"),
            rol="medewerker",
            actief=True
        )
        db.session.add(u)
        db.session.commit()
        db.session.add(UserOrganisatie(user_id=u.id, organisatie_id=self.org.id, rol="medewerker", actief=True))

        # Maak map en document aan door deze gebruiker
        folder = Folder(naam="Creator Map", organisatie_id=self.org.id, aangemaakt_door_id=u.id)
        db.session.add(folder)
        db.session.commit()

        doc = Document(
            bestandsnaam="creator_doc.pdf",
            type="pdf",
            mime_type="application/pdf",
            bestandsgrootte=100,
            inhoud=b"ABC",
            organisatie_id=self.org.id,
            map_id=folder.id,
            aangemaakt_door_id=u.id
        )
        db.session.add(doc)

        # Maak feedback item en comment door deze gebruiker
        fb = FeedbackItem(
            organisatie_id=self.org.id,
            user_id=u.id,
            type="voorstel",
            onderwerp="Mijn idee",
            beschrijving="Mijn omschrijving"
        )
        db.session.add(fb)
        db.session.commit()

        vote = FeedbackVote(feedback_id=fb.id, user_id=u.id, stem=1)
        comment = FeedbackComment(feedback_id=fb.id, user_id=u.id, tekst="Mijn reactie")
        db.session.add_all([vote, comment])
        db.session.commit()

        u_id = u.id
        doc_id = doc.id
        folder_id = folder.id

        # Verwijder gebruiker -> mag NIET falen op foreign keys en moet documenten re-attribueren
        res = self.client.post(f'/beheer/gebruikers/{u_id}/verwijderen', follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn("is succesvol verwijderd", res.get_data(as_text=True))

        # Gebruiker is weg
        self.assertIsNone(db.session.get(User, u_id))
        # Documenten bestaan nog, maar zijn geherattribueerd naar de uitvoerende beheerder
        refreshed_doc = db.session.get(Document, doc_id)
        self.assertEqual(refreshed_doc.aangemaakt_door_id, self.admin_user.id)
        refreshed_folder = db.session.get(Folder, folder_id)
        self.assertEqual(refreshed_folder.aangemaakt_door_id, self.admin_user.id)

    def test_gebruiker_wijzigen_form_renders_organisatie_rol_en_autocomplete(self):
        self.login_admin()

        # Maak gebruiker aan met globale rol 'medewerker', maar organisatie-rol 'beheerder'
        u = User(
            naam="Geert",
            email="geert@test.com",
            wachtwoord_hash=generate_password_hash("password123"),
            rol="medewerker",
            actief=True
        )
        db.session.add(u)
        db.session.commit()

        uo = UserOrganisatie(user_id=u.id, organisatie_id=self.org.id, rol="beheerder", actief=True)
        db.session.add(uo)
        db.session.commit()

        # GET op wijzigen pagina: controleer dat beheerder geselecteerd is en autocomplete aanwezig is
        res = self.client.get(f'/beheer/gebruikers/{u.id}/wijzig')
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)
        self.assertIn('<option value="beheerder" selected>Beheerder</option>', html)
        self.assertIn('autocomplete="new-password"', html)

