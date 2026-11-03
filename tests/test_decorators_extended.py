"""
Unit tests voor utils.decorators:
- admin_required
- actief_required
- platform_admin_required
- writer_required
"""
from flask import session
from tests.base import BaseTestCase, TEST_PASSWORD_HASH
from extensions import db
from models.user import User
from models.organisatie import Organisatie, UserOrganisatie
from models.constants import ROLE_PLATFORMBEHEERDER, ROLE_BEHEERDER, ROLE_MEDEWERKER, ROLE_LEZER
from utils.permissions import seed_standaard_groepen_voor_organisatie
from utils.decorators import admin_required, actief_required, platform_admin_required, writer_required


class TestDecoratorsExtended(BaseTestCase):
    def setUp(self):
        super().setUp()
        seed_standaard_groepen_voor_organisatie(self.org.id)

        # Registreer tijdelijke testroutes op de app
        @self.app.route('/test-admin-req')
        @admin_required
        def dummy_admin():
            return "OK_ADMIN"

        @self.app.route('/test-actief-req')
        @actief_required
        def dummy_actief():
            return "OK_ACTIEF"

        @self.app.route('/test-platform-req')
        @platform_admin_required
        def dummy_platform():
            return "OK_PLATFORM"

        @self.app.route('/test-writer-req')
        @writer_required
        def dummy_writer():
            return "OK_WRITER"

    def test_admin_required_branches(self):
        # 1. Niet ingelogd
        res = self.client.get('/test-admin-req')
        self.assertEqual(res.status_code, 302)
        self.assertIn('/login', res.headers['Location'])

        # 2. Platformbeheerder (altijd toegang)
        platform_user = User(
            naam="PlatformBoss",
            email="platform@test.be",
            wachtwoord_hash=TEST_PASSWORD_HASH,
            rol=ROLE_PLATFORMBEHEERDER,
            actief=True
        )
        db.session.add(platform_user)
        db.session.commit()

        self.login("platform@test.be", "password123")
        with self.client.session_transaction() as sess:
            sess['organisatie_id'] = self.org.id
        res = self.client.get('/test-admin-req')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data.decode(), "OK_ADMIN")
        self.logout()

        # 3. Gewone beheerder zonder organisatie in sessie
        self.login("AdminMark", "password123")
        with self.client.session_transaction() as sess:
            sess.pop('organisatie_id', None)
        res = self.client.get('/test-admin-req')
        self.assertEqual(res.status_code, 302)
        self.assertIn('/select-organisatie', res.headers['Location'])

        # 4. Gewone beheerder met organisatie in sessie en schrijfrechten
        self.select_organisatie(self.org.id)
        res = self.client.get('/test-admin-req')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data.decode(), "OK_ADMIN")
        self.logout()

        # 6. Directe aanroep admin_required zonder org_id in sessie
        def dummy_a():
            return "OK"
        dec_admin = admin_required(dummy_a)
        with self.app.test_request_context('/'):
            from flask_login import login_user
            login_user(self.admin_user)
            resp = dec_admin()
            self.assertEqual(resp.status_code, 302)
            self.assertIn('/select-organisatie', resp.headers['Location'])

        # 7. Directe aanroep admin_required zonder schrijfrechten (bijv. medewerker)
        with self.app.test_request_context('/'):
            from flask_login import login_user
            login_user(self.medewerker_user)
            session['organisatie_id'] = self.org.id
            resp = dec_admin()
            self.assertEqual(resp.status_code, 302)
            self.assertIn('/registraties', resp.headers['Location'])

    def test_actief_required_branches(self):
        # 1. Niet ingelogd -> mag doorgaan naar de pagina
        res = self.client.get('/test-actief-req')
        self.assertEqual(res.status_code, 200)

        # 2. Ingelogd maar inactief account (inloggen terwijl actief, daarna deactiveren om decorator te testen)
        temp_user = User(
            naam="WordtInactief",
            email="wordtinactief@test.be",
            wachtwoord_hash=TEST_PASSWORD_HASH,
            rol=ROLE_MEDEWERKER,
            actief=True
        )
        db.session.add(temp_user)
        db.session.commit()
        uo_temp = UserOrganisatie(user_id=temp_user.id, organisatie_id=self.org.id, rol=ROLE_MEDEWERKER, actief=True)
        db.session.add(uo_temp)
        db.session.commit()

        self.login("wordtinactief@test.be", "password123")
        temp_user.actief = False
        db.session.commit()

        res = self.client.get('/test-actief-req', follow_redirects=True)
        self.assertIn('Uw account is gedeactiveerd.', res.data.decode())
        self.logout()

    def test_platform_admin_required_branches(self):
        # 1. Niet ingelogd
        res = self.client.get('/test-platform-req')
        self.assertEqual(res.status_code, 302)
        self.assertIn('/login', res.headers['Location'])

        # 2. Ingelogd als reguliere beheerder
        self.login("AdminMark", "password123")
        res = self.client.get('/test-platform-req', follow_redirects=True)
        self.assertIn('U heeft geen toegang tot deze pagina.', res.data.decode())
        self.logout()

        # 3. Ingelogd als platformbeheerder
        p_user = User(
            naam="PAdmin",
            email="padmin@test.be",
            wachtwoord_hash=TEST_PASSWORD_HASH,
            rol=ROLE_PLATFORMBEHEERDER,
            actief=True
        )
        db.session.add(p_user)
        db.session.commit()
        self.login("padmin@test.be", "password123")
        res = self.client.get('/test-platform-req')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data.decode(), "OK_PLATFORM")
        self.logout()

    def test_writer_required_branches(self):
        # 1. Niet ingelogd
        res = self.client.get('/test-writer-req')
        self.assertEqual(res.status_code, 302)
        self.assertIn('/login', res.headers['Location'])

        # 2. Platformbeheerder
        p_user = User(
            naam="PAdminWriter",
            email="padminwriter@test.be",
            wachtwoord_hash=TEST_PASSWORD_HASH,
            rol=ROLE_PLATFORMBEHEERDER,
            actief=True
        )
        db.session.add(p_user)
        db.session.commit()
        self.login("padminwriter@test.be", "password123")
        with self.client.session_transaction() as sess:
            sess['organisatie_id'] = self.org.id
        res = self.client.get('/test-writer-req')
        self.assertEqual(res.status_code, 200)
        self.logout()

        # 3. Directe aanroep van de decorator functie binnen request context
        def dummy():
            return "OK"

        dec_writer = writer_required(dummy)

        # a) Niet ingelogd
        with self.app.test_request_context('/'):
            resp = dec_writer()
            self.assertEqual(resp.status_code, 302)
            self.assertIn('/login', resp.headers['Location'])

        # b) Ingelogd als platformbeheerder
        with self.app.test_request_context('/'):
            from flask_login import login_user
            login_user(p_user)
            resp = dec_writer()
            self.assertEqual(resp, "OK")

        # c) Geen organisatie in sessie
        with self.app.test_request_context('/'):
            from flask_login import login_user
            login_user(self.admin_user)
            resp = dec_writer()
            self.assertEqual(resp.status_code, 302)
            self.assertIn('/select-organisatie', resp.headers['Location'])

        # d) Geen lidmaatschap in actieve organisatie
        org2 = Organisatie(naam="Tweede Org", slug="tweede-org", actief=True)
        db.session.add(org2)
        db.session.commit()
        with self.app.test_request_context('/'):
            from flask_login import login_user
            login_user(self.admin_user)
            session['organisatie_id'] = org2.id
            resp = dec_writer()
            self.assertEqual(resp.status_code, 302)
            self.assertIn('/registraties', resp.headers['Location'])

        # e) Alleen-lezer (geen enkel schrijfrecht)
        lezer_user = User(
            naam="AlleenLezer",
            email="lezer@test.be",
            wachtwoord_hash=TEST_PASSWORD_HASH,
            rol=ROLE_LEZER,
            actief=True
        )
        db.session.add(lezer_user)
        db.session.commit()
        uo_lezer = UserOrganisatie(user_id=lezer_user.id, organisatie_id=self.org.id, rol=ROLE_LEZER, actief=True)
        db.session.add(uo_lezer)
        db.session.commit()

        with self.app.test_request_context('/'):
            from flask_login import login_user
            login_user(lezer_user)
            session['organisatie_id'] = self.org.id
            resp = dec_writer()
            self.assertEqual(resp.status_code, 302)
            self.assertIn('/registraties', resp.headers['Location'])

        # f) Schrijfrecht aanwezig
        with self.app.test_request_context('/'):
            from flask_login import login_user
            login_user(self.admin_user)
            session['organisatie_id'] = self.org.id
            resp = dec_writer()
            self.assertEqual(resp, "OK")
