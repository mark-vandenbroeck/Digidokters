from tests.base import BaseTestCase
from flask import session
from extensions import db
from models.user import User
from models.audit import AuditLog
from datetime import datetime, timezone
from flask_login import login_user

class TestAudit(BaseTestCase):
    def test_audit_logs_created_on_update(self):
        # Update user name (regular update)
        self.medewerker_user.email = "newemail@test.com"
        db.session.commit()

        # Check that an AuditLog entry was created
        log = AuditLog.query.filter_by(tabel='users', operatie='UPDATE', record_id=self.medewerker_user.id).first()
        self.assertIsNotNone(log)
        self.assertIn("email", log.details)
        self.assertIn("newemail@test.com", log.details)

    def test_audit_logs_login_filtering(self):
        # 1. Log in admin via test client session
        self.login("AdminMark", "password123")
        self.select_organisatie(self.org.id)

        # 2. Perform updates within a request context so listeners capture the session's organisation context
        with self.app.test_request_context():
            session['organisatie_id'] = self.org.id
            login_user(self.admin_user)
            
            # Fetch user in current session context
            u = db.session.get(User, self.medewerker_user.id)
            
            # Scenario A: login-only update
            u.laatste_login = datetime.now(timezone.utc)
            db.session.commit()
            
            # Scenario B: regular update
            u.naam = "UpdatedTim"
            db.session.commit()

        # 3. Request logs through test client
        # Scenario A: toon_logins=false (default behavior) -> should hide the login update
        response_default = self.client.get('/beheer/audit-log?toon_logins=false')
        self.assertEqual(response_default.status_code, 200)
        html_default = response_default.data.decode('utf-8')
        
        # Check that the name update is visible, but the login update details are NOT
        self.assertIn("UpdatedTim", html_default)
        self.assertNotIn("laatste_login", html_default)

        # Scenario B: toon_logins=true -> should show all updates including the login
        response_all = self.client.get('/beheer/audit-log?toon_logins=true')
        self.assertEqual(response_all.status_code, 200)
        html_all = response_all.data.decode('utf-8')
        
        self.assertIn("UpdatedTim", html_all)
        self.assertIn("laatste_login", html_all)
