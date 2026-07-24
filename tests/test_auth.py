from tests.base import BaseTestCase
from flask import session
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
        response = self.login("UserTim", "wrongpassword")
        self.assertEqual(response.status_code, 200)
        self.assertIn("ongeldige naam of wachtwoord", response.data.decode('utf-8').lower())

    def test_login_inactive_user(self):
        # Deactivate user and attempt login
        from extensions import db
        self.medewerker_user.actief = False
        db.session.commit()

        response = self.login("UserTim", "password123")
        self.assertEqual(response.status_code, 200)
        self.assertIn("gedeactiveerd", response.data.decode('utf-8').lower())

    def test_logout(self):
        # Log in first
        self.login("UserTim", "password123")
        
        # Log out
        response = self.logout()
        self.assertEqual(response.status_code, 200)
        # Should show login page again
        self.assertIn("inloggen", response.data.decode('utf-8').lower())

    def test_select_organisatie_success(self):
        # Log in and select organization
        self.login("AdminMark", "password123")
        response = self.select_organisatie(self.org.id)
        self.assertEqual(response.status_code, 200)
        
        # Session should contain the organisation_id
        with self.client.session_transaction() as sess:
            self.assertEqual(sess.get('organisatie_id'), self.org.id)

    def test_password_reset_lockout(self):
        # 1. Request reset code for UserTim
        response = self.client.post('/wachtwoord-vergeten', data={'naam': 'UserTim'}, follow_redirects=True)
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
