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

    def test_audit_logs_sorting_headers(self):
        """Controleer dat alle kolommen sorteerbaar zijn en sort links bevatten."""
        self.login("AdminMark", "password123")
        self.select_organisatie(self.org.id)

        response = self.client.get('/beheer/audit-log?sort_by=gebruiker&direction=asc')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')

        # Controleer de sorteerlinks in de tabelkoppen
        self.assertIn("sort_by=timestamp", html)
        self.assertIn("sort_by=gebruiker", html)
        self.assertIn("sort_by=operatie", html)
        self.assertIn("sort_by=tabel", html)
        self.assertIn("sort_by=record_id", html)

        # Actieve kolom pijl indicator (voor gebruiker asc)
        self.assertIn("bi-arrow-up-short", html)

    def test_audit_logs_sorting_by_columns(self):
        """Test dat sorteren op verschillende kolommen correct werkt."""
        from datetime import timedelta
        from models.organisatie import Organisatie

        self.login("AdminMark", "password123")
        self.select_organisatie(self.org.id)

        # Verwijder achtergrondlogs van setup/login zodat de test hermetisch is
        AuditLog.query.delete()
        db.session.commit()

        now = datetime.now(timezone.utc)
        # Maak test audit logs aan
        log_a = AuditLog(tabel="activiteiten", operatie="CREATE", record_id=10, gebruiker="Alice", timestamp=now - timedelta(minutes=10), organisatie_id=self.org.id)
        log_b = AuditLog(tabel="bezoeken", operatie="UPDATE", record_id=20, gebruiker="Bob", timestamp=now - timedelta(minutes=5), organisatie_id=self.org.id)
        log_c = AuditLog(tabel="cliënten", operatie="DELETE", record_id=30, gebruiker="Charlie", timestamp=now, organisatie_id=self.org.id)
        db.session.add_all([log_a, log_b, log_c])
        db.session.commit()

        # 1. Sorteer op gebruiker asc
        resp_gebruiker_asc = self.client.get('/beheer/audit-log?sort_by=gebruiker&direction=asc')
        html_g_asc = resp_gebruiker_asc.data.decode('utf-8')
        pos_alice = html_g_asc.find("Alice")
        pos_bob = html_g_asc.find("Bob")
        pos_charlie = html_g_asc.find("Charlie")
        self.assertTrue(pos_alice < pos_bob < pos_charlie)

        # 2. Sorteer op gebruiker desc
        resp_gebruiker_desc = self.client.get('/beheer/audit-log?sort_by=gebruiker&direction=desc')
        html_g_desc = resp_gebruiker_desc.data.decode('utf-8')
        pos_alice = html_g_desc.find("Alice")
        pos_bob = html_g_desc.find("Bob")
        pos_charlie = html_g_desc.find("Charlie")
        self.assertTrue(pos_charlie < pos_bob < pos_alice)

        # 3. Sorteer op operatie asc (CREATE, DELETE, UPDATE)
        resp_op_asc = self.client.get('/beheer/audit-log?sort_by=operatie&direction=asc')
        self.assertEqual(resp_op_asc.status_code, 200)

        # 4. Sorteer op tabel asc (activiteiten, bezoeken, cliënten)
        resp_tabel_asc = self.client.get('/beheer/audit-log?sort_by=tabel&direction=asc')
        html_t_asc = resp_tabel_asc.data.decode('utf-8')
        pos_act = html_t_asc.find("activiteiten")
        pos_bez = html_t_asc.find("bezoeken")
        self.assertTrue(pos_act < pos_bez)

        # 5. Sorteer op record_id desc (30, 20, 10)
        resp_id_desc = self.client.get('/beheer/audit-log?sort_by=record_id&direction=desc')
        html_id_desc = resp_id_desc.data.decode('utf-8')
        pos_30 = html_id_desc.find("<td>30</td>")
        pos_20 = html_id_desc.find("<td>20</td>")
        pos_10 = html_id_desc.find("<td>10</td>")
        self.assertTrue(pos_30 < pos_20 < pos_10)

        # 6. Sorteer op timestamp asc (oudste eerst: log_a, log_b, log_c)
        resp_time_asc = self.client.get('/beheer/audit-log?sort_by=timestamp&direction=asc')
        html_time_asc = resp_time_asc.data.decode('utf-8')
        pos_alice = html_time_asc.find("Alice")
        pos_charlie = html_time_asc.find("Charlie")
        self.assertTrue(pos_alice < pos_charlie)

    def test_audit_logs_sorting_organisatie_for_platform_admin(self):
        """Platformbeheerders kunnen ook sorteren op de kolom Organisatie."""
        from models.organisatie import Organisatie, UserOrganisatie
        from werkzeug.security import generate_password_hash

        # Maak platformbeheerder
        pb = User(
            naam="SuperAdminAudit",
            email="superadminaudit@test.be",
            wachtwoord_hash=generate_password_hash("pass123"),
            rol="platformbeheerder",
            actief=True
        )
        db.session.add(pb)
        db.session.commit()

        # Maak twee organisaties
        org_a = Organisatie(naam="Alpha Gemeente", slug="alpha", actief=True)
        org_z = Organisatie(naam="Zulu Gemeente", slug="zulu", actief=True)
        db.session.add_all([org_a, org_z])
        db.session.commit()

        uo = UserOrganisatie(user_id=pb.id, organisatie_id=org_a.id, rol="beheerder", actief=True)
        db.session.add(uo)
        db.session.commit()

        # Schoon eerdere logs op
        AuditLog.query.delete()
        db.session.commit()

        now = datetime.now(timezone.utc)
        log1 = AuditLog(tabel="users", operatie="UPDATE", record_id=1, gebruiker="Admin", timestamp=now, organisatie_id=org_z.id)
        log2 = AuditLog(tabel="users", operatie="UPDATE", record_id=2, gebruiker="Admin", timestamp=now, organisatie_id=org_a.id)
        db.session.add_all([log1, log2])
        db.session.commit()

        self.login("superadminaudit@test.be", "pass123")
        self.select_organisatie(org_a.id)

        # Sorteer op organisatie asc (Alpha voor Zulu)
        resp_org_asc = self.client.get('/beheer/audit-log?sort_by=organisatie&direction=asc')
        self.assertEqual(resp_org_asc.status_code, 200)
        html_org_asc = resp_org_asc.data.decode('utf-8')
        self.assertIn("sort_by=organisatie", html_org_asc)
        tbody_asc = html_org_asc.split("<tbody>")[1].split("</tbody>")[0]
        pos_alpha = tbody_asc.find("Alpha Gemeente")
        pos_zulu = tbody_asc.find("Zulu Gemeente")
        self.assertTrue(pos_alpha < pos_zulu)

        # Sorteer op organisatie desc (Zulu voor Alpha)
        resp_org_desc = self.client.get('/beheer/audit-log?sort_by=organisatie&direction=desc')
        html_org_desc = resp_org_desc.data.decode('utf-8')
        tbody_desc = html_org_desc.split("<tbody>")[1].split("</tbody>")[0]
        pos_alpha = tbody_desc.find("Alpha Gemeente")
        pos_zulu = tbody_desc.find("Zulu Gemeente")
        self.assertTrue(pos_zulu < pos_alpha)
