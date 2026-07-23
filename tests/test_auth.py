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
