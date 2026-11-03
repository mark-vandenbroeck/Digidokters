from unittest.mock import patch
from tests.base import BaseTestCase, TEST_PASSWORD_HASH
from flask import session
from extensions import db
from models.user import User

class TestAuth(BaseTestCase):
    def test_login_success(self):
        # Test successful login of a medewerker
        response = self.login("UserTim", "password123")
        self.assertEqual(response.status_code, 200)
        # Should redirect/show registrations list page or choose org
        self.assertIn("registraties", response.data.decode('utf-8').lower())

    def test_login_invalid_password(self):
        # Test login with invalid password
        response = self.login("tim@test.com", "wrongpassword")
        self.assertEqual(response.status_code, 200)
        self.assertIn("ongeldig e-mailadres of wachtwoord", response.data.decode('utf-8').lower())

    def test_login_inactive_user(self):
        # Deactivate user and attempt login
        from extensions import db
        self.medewerker_user.actief = False
        db.session.commit()

        response = self.login("tim@test.com", "password123")
        self.assertEqual(response.status_code, 200)
        self.assertIn("gedeactiveerd", response.data.decode('utf-8').lower())

    def test_logout(self):
        # Log in first
        self.login("tim@test.com", "password123")
        
        # Log out
        response = self.logout()
        self.assertEqual(response.status_code, 200)
        # Should show login page again
        self.assertIn("inloggen", response.data.decode('utf-8').lower())

    def test_select_organisatie_success(self):
        # Log in and select organization
        self.login("admin@test.com", "password123")
        response = self.select_organisatie(self.org.id)
        self.assertEqual(response.status_code, 200)
        
        # Session should contain the organisation_id
        with self.client.session_transaction() as sess:
            self.assertEqual(sess.get('organisatie_id'), self.org.id)

    @patch('utils.mail.verstuur_email')
    def test_password_reset_lockout(self, mock_verstuur_email):
        mock_verstuur_email.return_value = None
        # 1. Request reset code for tim@test.com
        response = self.client.post('/wachtwoord-vergeten', data={'email': 'tim@test.com'}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("herstelcode", response.data.decode('utf-8').lower())

        # Retrieve user from DB to get the generated code
        from extensions import db
        user = User.query.filter_by(naam="UserTim").first()
        self.assertIsNotNone(user.reset_code)
        self.assertEqual(user.reset_pogingen, 0)

        # 2. Try verifying with wrong code 4 times
        for i in range(1, 5):
            res_wrong = self.client.post('/wachtwoord-vergeten/verifieer', data={
                'code': '000000', # wrong code
                'nieuw_wachtwoord': 'Password123!',
                'bevestig_wachtwoord': 'Password123!'
            }, follow_redirects=True)
            self.assertEqual(res_wrong.status_code, 200)
            self.assertIn(f"nog {5 - i} pogingen", res_wrong.data.decode('utf-8').lower())
            
            db.session.refresh(user)
            self.assertEqual(user.reset_pogingen, i)
            self.assertIsNotNone(user.reset_code)

        # 3. 5th failed attempt should trigger lockout
        res_lockout = self.client.post('/wachtwoord-vergeten/verifieer', data={
            'code': '000000', # wrong code
            'nieuw_wachtwoord': 'Password123!',
            'bevestig_wachtwoord': 'Password123!'
        }, follow_redirects=True)
        self.assertEqual(res_lockout.status_code, 200)
        self.assertIn("te veel mislukte pogingen", res_lockout.data.decode('utf-8').lower())

        # Refresh user from DB - code and attempts should be cleared
        db.session.refresh(user)
        self.assertIsNone(user.reset_code)
        self.assertIsNone(user.reset_code_verloopt_op)
        self.assertEqual(user.reset_pogingen, 0)

    def test_csrf_error_redirects_to_login(self):
        # Enable CSRF temporarily for this test
        self.app.config['WTF_CSRF_ENABLED'] = True
        
        # Make a POST request without a CSRF token
        response = self.client.post('/beheer/audit-log/opschonen', data={}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        
        # Verify redirect to login page with warning message
        self.assertIn("sessie is verlopen", response.data.decode('utf-8').lower())
        self.assertIn("inloggen", response.data.decode('utf-8').lower())

    def test_medewerker_sidebar_shows_data_section(self):
        # Medewerker logs in and views page
        self.login("tim@test.com", "password123")
        response = self.client.get('/registraties')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        # Data section header must be visible in sidebar
        self.assertIn('data-bs-target="#nav-data"', html)
        self.assertIn('Data', html)
        # Exporteren, Statistieken and Privacy must be visible
        self.assertIn('Exporteren', html)
        self.assertIn('Statistieken', html)
        self.assertIn('Privacy & AVG', html)
        # Importeren should NOT be visible for medewerker
        self.assertNotIn('Importeren', html)
        # Beheer section should NOT be visible for medewerker
        self.assertNotIn('data-bs-target="#nav-beheer"', html)

    def test_privacy_modal_comprehensive_sections(self):
        self.login("tim@test.com", "password123")
        response = self.client.get('/registraties')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        self.assertIn('1. Richtlijn voor Bezoekersregistratie', html)
        self.assertIn('2. Uw gegevens als Vrijwilliger / Medewerker', html)
        self.assertIn('3. Evaluaties & Kwaliteitsmeting', html)
        self.assertIn('4. Feedback & Schermafbeeldingen', html)
        self.assertIn('5. Documentbeheer', html)
        self.assertIn('6. Recht op Vergetelheid & Inzage', html)

    def test_sidebar_collapsible_sections(self):
        self.login("AdminMark", "password123")
        response = self.client.get('/registraties')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')

        # Controleer aanwezigheid van inklapbare rubrieken voor beheerder
        expected_sections = [
            ('#nav-registraties', 'Registraties'),
            ('#nav-documentbeheer', 'Documentbeheer'),
            ('#nav-beheer', 'Beheer'),
            ('#nav-data', 'Data'),
            ('#nav-algemeen', 'Algemeen')
        ]
        for target, title in expected_sections:
            self.assertIn(f'data-bs-target="{target}"', html)
            self.assertIn(f'id="{target[1:]}"', html)
            self.assertIn(title, html)

        self.assertIn('dd-nav-chevron', html)
        self.assertIn('sidebar_collapse_', html)

    def test_moet_wachtwoord_wijzigen_login_en_wijzig_flow(self):
        from extensions import db
        # Zet gebruiker op moet_wachtwoord_wijzigen = True
        self.medewerker_user.moet_wachtwoord_wijzigen = True
        db.session.commit()

        # Inloggen met huidig wachtwoord
        res = self.client.post('/login', data={
            'email': 'tim@test.com',
            'wachtwoord': 'password123'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        # Wachtwoord wijzigen zonder huidig_wachtwoord mee te sturen
        res_change = self.client.post('/wachtwoord', data={
            'nieuw_wachtwoord': 'NieuwPass123!',
            'bevestig_wachtwoord': 'NieuwPass123!',
            'email': 'tim@test.com'
        }, follow_redirects=True)
        self.assertEqual(res_change.status_code, 200)
        self.assertIn("Wachtwoord succesvol gewijzigd", res_change.get_data(as_text=True))

        # Controleer dat moet_wachtwoord_wijzigen nu False is
        db.session.refresh(self.medewerker_user)
        self.assertFalse(self.medewerker_user.moet_wachtwoord_wijzigen)

    def test_select_org_and_header_displays_groepen_instead_of_rol(self):
        """Test dat select_org en de header de toegekende groepen tonen i.p.v. statische rol."""
        from extensions import db
        from models.group import Group, UserGroup
        from utils.permissions import seed_standaard_groepen_voor_organisatie

        groepen = seed_standaard_groepen_voor_organisatie(self.org.id)
        existing_ug = UserGroup.query.filter_by(user_id=self.admin_user.id, groep_id=groepen['beheerders'].id).first()
        if not existing_ug:
            ug = UserGroup(user_id=self.admin_user.id, groep_id=groepen['beheerders'].id)
            db.session.add(ug)
            db.session.commit()

        # 1. Bekijk /select-organisatie
        self.login("admin@test.com", "password123")
        res_sel = self.client.get('/select-organisatie')
        self.assertEqual(res_sel.status_code, 200)
        html_sel = res_sel.get_data(as_text=True)
        self.assertIn("Beheerders", html_sel)

        # 2. Selecteer organisatie en bekijk header/sidebar
        res_main = self.select_organisatie(self.org.id)
        self.assertEqual(res_main.status_code, 200)
        html_main = res_main.get_data(as_text=True)
        self.assertIn("Beheerders", html_main)

    def test_switch_organisatie_retains_current_menu_choice(self):
        from extensions import db
        from models.organisatie import Organisatie
        from tests.base import TEST_PASSWORD_HASH

        # Create a second organization and platform admin
        org2 = Organisatie(naam="Tweede Org", slug="tweede-org", actief=True)
        platform_user = User(
            naam="PBMark",
            email="pb@test.com",
            wachtwoord_hash=TEST_PASSWORD_HASH,
            rol="platformbeheerder",
            actief=True
        )
        db.session.add_all([org2, platform_user])
        db.session.commit()

        self.login("pb@test.com", "password123")

        # 1. On Statistieken -> switches org -> stays on Statistieken
        res = self.client.post('/switch-organisatie', data={
            'organisatie_id': org2.id,
            'current_endpoint': 'stats.overzicht',
            'next': '/statistieken?jaar=2024'
        }, follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.headers['Location'], '/statistieken?jaar=2024')

        # 2. On Agenda -> switches org -> stays on Agenda
        res = self.client.post('/switch-organisatie', data={
            'organisatie_id': self.org.id,
            'current_endpoint': 'agenda.lijst',
            'next': '/agenda'
        }, follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.headers['Location'], '/agenda')

        # 3. On Platform Dashboard -> switches org -> stays on Platform Dashboard
        res = self.client.post('/switch-organisatie', data={
            'organisatie_id': org2.id,
            'current_endpoint': 'platform.dashboard',
            'next': '/platform/dashboard'
        }, follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.headers['Location'], '/platform/dashboard')

        # 4. On Locaties -> switches org -> stays on Locaties
        res = self.client.post('/switch-organisatie', data={
            'organisatie_id': self.org.id,
            'current_endpoint': 'admin.locaties',
            'next': '/beheer/locaties'
        }, follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.headers['Location'], '/beheer/locaties')

        # 5. On an edit page (e.g. reg.wijzigen) -> switches org -> safely redirects to reg.lijst overview
        res = self.client.post('/switch-organisatie', data={
            'organisatie_id': org2.id,
            'current_endpoint': 'reg.wijzigen',
            'next': '/registraties/42/wijzig'
        }, follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.headers['Location'], '/registraties')

        # 6. On an admin sub-page (e.g. admin.locatie_wijzigen) -> safely redirects to admin.locaties overview
        res = self.client.post('/switch-organisatie', data={
            'organisatie_id': self.org.id,
            'current_endpoint': 'admin.locatie_wijzigen',
            'next': '/beheer/locaties/3/wijzigen'
        }, follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.headers['Location'], '/beheer/locaties')

        # 7. With Referer header only (no form hidden inputs) -> infers and stays on menu choice
        res = self.client.post('/switch-organisatie', data={
            'organisatie_id': org2.id,
        }, headers={'Referer': 'http://localhost/statistieken'}, follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.headers['Location'], '/statistieken')

        # 8. Switch to Sjabloon from stats.overzicht -> redirected to admin.leeftijdscategorieën
        sjabloon = Organisatie(naam="Sjabloon", slug="sjabloon", actief=True)
        db.session.add(sjabloon)
        db.session.commit()

        res = self.client.post('/switch-organisatie', data={
            'organisatie_id': sjabloon.id,
            'current_endpoint': 'stats.overzicht',
            'next': '/statistieken'
        }, follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.headers['Location'], '/beheer/leeftijdscategorie%C3%ABn')

        # 9. Switch to Sjabloon from an allowed page (e.g. admin.toestellen) -> stays on admin.toestellen
        res = self.client.post('/switch-organisatie', data={
            'organisatie_id': sjabloon.id,
            'current_endpoint': 'admin.toestellen',
            'next': '/beheer/toestellen'
        }, follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.headers['Location'], '/beheer/toestellen')

        # 10. Switch away from Sjabloon to regular org -> retains menu choice (e.g. admin.toestellen)
        res = self.client.post('/switch-organisatie', data={
            'organisatie_id': org2.id,
            'current_endpoint': 'admin.toestellen',
            'next': '/beheer/toestellen'
        }, follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.headers['Location'], '/beheer/toestellen')

        # 11. Without any context or referrer -> falls back to reg.lijst
        res = self.client.post('/switch-organisatie', data={
            'organisatie_id': self.org.id,
        }, follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.headers['Location'], '/registraties')

        # 12. Platformbeheerder switcht naar niet-bestaande organisatie
        res_invalid_org = self.client.post('/switch-organisatie', data={
            'organisatie_id': 999999,
        }, follow_redirects=True)
        self.assertIn('Ongeldige organisatie.', res_invalid_org.data.decode('utf-8'))
        self.logout()

        # 13. Reguliere gebruiker switcht naar organisatie waar hij wel en geen lid van is
        self.login("AdminMark", "password123")
        res_user_switch = self.client.post('/switch-organisatie', data={
            'organisatie_id': self.org.id,
        }, follow_redirects=True)
        self.assertIn('Gewisseld naar organisatie', res_user_switch.data.decode('utf-8'))

        res_unauth_switch = self.client.post('/switch-organisatie', data={
            'organisatie_id': org2.id,
        }, follow_redirects=True)
        self.assertIn('U heeft geen toegang tot deze organisatie.', res_unauth_switch.data.decode('utf-8'))

    def test_wachtwoord_vergeten_en_verifieer_volledige_flow(self):
        """Test alle scenario's van wachtwoord vergeten en verificatiecode validatie."""
        from datetime import datetime, timezone, timedelta
        from unittest.mock import patch

        # 1. Al ingelogd -> redirect naar /registraties
        self.login("AdminMark", "password123")
        res = self.client.get('/wachtwoord-vergeten', follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertIn('/registraties', res.headers['Location'])

        res_v = self.client.get('/wachtwoord-vergeten/verifieer', follow_redirects=False)
        self.assertEqual(res_v.status_code, 302)
        self.assertIn('/registraties', res_v.headers['Location'])
        self.logout()

        # 2. POST /wachtwoord-vergeten zonder email
        res_no_email = self.client.post('/wachtwoord-vergeten', data={'email': ''}, follow_redirects=True)
        self.assertIn('Vul uw e-mailadres in.', res_no_email.data.decode('utf-8'))

        # 3. POST /wachtwoord-vergeten met onbekend email
        res_unknown = self.client.post('/wachtwoord-vergeten', data={'email': 'onbekend@test.be'}, follow_redirects=True)
        self.assertIn('E-mailadres is niet bekend.', res_unknown.data.decode('utf-8'))

        # 4. POST /wachtwoord-vergeten met gedeactiveerde gebruiker
        inactieve_u = User(
            naam="InactiefVoorReset",
            email="inactief_reset@test.com",
            wachtwoord_hash=TEST_PASSWORD_HASH,
            rol="medewerker",
            actief=False
        )
        db.session.add(inactieve_u)
        db.session.commit()
        res_inactief = self.client.post('/wachtwoord-vergeten', data={'email': 'inactief_reset@test.com'}, follow_redirects=True)
        self.assertIn('Uw account is gedeactiveerd.', res_inactief.data.decode('utf-8'))

        # 5. POST /wachtwoord-vergeten waarbij e-mail versturen faalt
        with patch('utils.mail.verstuur_email') as mock_mail:
            mock_mail.side_effect = Exception("SMTP Offline")
            res_fail = self.client.post('/wachtwoord-vergeten', data={'email': 'tim@test.com'}, follow_redirects=True)
            self.assertIn('Fout bij het versturen van de e-mail.', res_fail.data.decode('utf-8'))

        # 6. POST /wachtwoord-vergeten succesvol
        with patch('utils.mail.verstuur_email') as mock_mail:
            mock_mail.return_value = (True, "OK")
            res_succes = self.client.post('/wachtwoord-vergeten', data={'email': 'tim@test.com'}, follow_redirects=False)
            self.assertEqual(res_succes.status_code, 302)
            self.assertIn('/wachtwoord-vergeten/verifieer', res_succes.headers['Location'])

        # 7. GET /wachtwoord-vergeten/verifieer zonder reset_username in sessie
        with self.client.session_transaction() as sess:
            sess.pop('reset_username', None)
        res_no_sess = self.client.get('/wachtwoord-vergeten/verifieer', follow_redirects=False)
        self.assertEqual(res_no_sess.status_code, 302)
        self.assertIn('/wachtwoord-vergeten', res_no_sess.headers['Location'])

        # 8. POST /wachtwoord-vergeten/verifieer ontbrekende velden en mismatch
        with self.client.session_transaction() as sess:
            sess['reset_username'] = self.medewerker_user.naam

        res_miss = self.client.post('/wachtwoord-vergeten/verifieer', data={'code': '123456'}, follow_redirects=True)
        self.assertIn('Vul alle velden in.', res_miss.data.decode('utf-8'))

        res_mismatch = self.client.post('/wachtwoord-vergeten/verifieer', data={
            'code': '123456',
            'nieuw_wachtwoord': 'Wachtwoord1!',
            'bevestig_wachtwoord': 'Wachtwoord2!'
        }, follow_redirects=True)
        self.assertIn('De nieuwe wachtwoorden komen niet overeen.', res_mismatch.data.decode('utf-8'))

        # 9. Verlopen code
        self.medewerker_user.reset_code = '123456'
        self.medewerker_user.reset_code_verloopt_op = datetime.now(timezone.utc) - timedelta(minutes=5)
        db.session.commit()
        res_expired = self.client.post('/wachtwoord-vergeten/verifieer', data={
            'code': '123456',
            'nieuw_wachtwoord': 'NieuwPass123!',
            'bevestig_wachtwoord': 'NieuwPass123!'
        }, follow_redirects=True)
        self.assertIn('De herstelcode is verlopen.', res_expired.data.decode('utf-8'))

        # 10. Verkeerde code en mislukte pogingen teller
        self.medewerker_user.reset_code_verloopt_op = datetime.now(timezone.utc) + timedelta(minutes=15)
        self.medewerker_user.reset_pogingen = 0
        db.session.commit()
        res_wrong = self.client.post('/wachtwoord-vergeten/verifieer', data={
            'code': '999999',
            'nieuw_wachtwoord': 'NieuwPass123!',
            'bevestig_wachtwoord': 'NieuwPass123!'
        }, follow_redirects=True)
        self.assertIn('Ongeldige herstelcode.', res_wrong.data.decode('utf-8'))

        # 11. Te veel mislukte pogingen (>= 5)
        self.medewerker_user.reset_pogingen = 4
        db.session.commit()
        res_locked = self.client.post('/wachtwoord-vergeten/verifieer', data={
            'code': '999999',
            'nieuw_wachtwoord': 'NieuwPass123!',
            'bevestig_wachtwoord': 'NieuwPass123!'
        }, follow_redirects=True)
        self.assertIn('Te veel mislukte pogingen.', res_locked.data.decode('utf-8'))

        # 12. Succesvol wachtwoord herstellen
        with self.client.session_transaction() as sess:
            sess['reset_username'] = self.medewerker_user.naam
        self.medewerker_user.reset_code = '654321'
        self.medewerker_user.reset_code_verloopt_op = datetime.now(timezone.utc) + timedelta(minutes=15)
        self.medewerker_user.reset_pogingen = 0
        db.session.commit()

        # Te zwak wachtwoord
        res_weak = self.client.post('/wachtwoord-vergeten/verifieer', data={
            'code': '654321',
            'nieuw_wachtwoord': 'kort',
            'bevestig_wachtwoord': 'kort'
        }, follow_redirects=True)
        self.assertIn('minstens 8 tekens', res_weak.data.decode('utf-8'))

        # Sterk wachtwoord
        res_success = self.client.post('/wachtwoord-vergeten/verifieer', data={
            'code': '654321',
            'nieuw_wachtwoord': 'VeiligWachtwoord123!',
            'bevestig_wachtwoord': 'VeiligWachtwoord123!'
        }, follow_redirects=False)
        self.assertEqual(res_success.status_code, 302)
        self.assertIn('/login', res_success.headers['Location'])

    def test_login_extra_scenarios(self):
        """Test extra scenario's bij login: inactieve gebruiker, geen lidmaatschap, 2 lidmaatschappen."""
        from models.organisatie import Organisatie, UserOrganisatie
        # 1. Inloggen met inactieve gebruiker
        inactief_u = User(
            naam="InactiefLogin",
            email="inactief_login@test.com",
            wachtwoord_hash=TEST_PASSWORD_HASH,
            rol="medewerker",
            actief=False
        )
        db.session.add(inactief_u)
        db.session.commit()
        res_inactief = self.client.post('/login', data={'email': 'inactief_login@test.com', 'wachtwoord': 'password123'}, follow_redirects=True)
        self.assertIn('Uw account is gedeactiveerd.', res_inactief.data.decode('utf-8'))

        # 2. Gebruiker zonder actieve organisatielidmaatschappen
        geen_org_u = User(
            naam="GeenOrgUser",
            email="geen_org@test.com",
            wachtwoord_hash=TEST_PASSWORD_HASH,
            rol="medewerker",
            actief=True
        )
        db.session.add(geen_org_u)
        db.session.commit()
        res_no_org = self.client.post('/login', data={'email': 'geen_org@test.com', 'wachtwoord': 'password123'}, follow_redirects=True)
        self.assertIn('niet gekoppeld aan een actieve organisatie', res_no_org.data.decode('utf-8'))

        # 3. Gebruiker met 2 organisatielidmaatschappen -> redirect naar select_org
        org2 = Organisatie(naam="Gemeente Twee", slug="gemeente-twee", actief=True)
        db.session.add(org2)
        db.session.commit()
        uo1 = UserOrganisatie(user_id=geen_org_u.id, organisatie_id=self.org.id, rol="medewerker", actief=True)
        uo2 = UserOrganisatie(user_id=geen_org_u.id, organisatie_id=org2.id, rol="medewerker", actief=True)
        db.session.add_all([uo1, uo2])
        db.session.commit()

        res_two_orgs = self.client.post('/login', data={'email': 'geen_org@test.com', 'wachtwoord': 'password123'}, follow_redirects=False)
        self.assertEqual(res_two_orgs.status_code, 302)
        self.assertIn('/select-organisatie', res_two_orgs.headers['Location'])
