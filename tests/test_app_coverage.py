from unittest.mock import patch
from datetime import datetime, timezone, timedelta
from werkzeug.exceptions import Forbidden, InternalServerError
from tests.base import BaseTestCase
from extensions import db
from models.user import User
from models.organisatie import Organisatie, UserOrganisatie
from models.audit import AuditLog

class TestAppCoverage(BaseTestCase):
    def test_cli_seed(self):
        runner = self.app.test_cli_runner()
        result = runner.invoke(args=['seed'])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Digidokters", result.output)

    def test_cli_create_org(self):
        runner = self.app.test_cli_runner()
        # First creation
        res1 = runner.invoke(args=['create-org', 'CLI Test Org', 'cli-test-org'])
        self.assertEqual(res1.exit_code, 0)
        self.assertIn("aangemaakt met slug", res1.output)

        # Duplicate creation
        res2 = runner.invoke(args=['create-org', 'CLI Test Org', 'cli-test-org'])
        self.assertEqual(res2.exit_code, 0)
        self.assertIn("bestaat al", res2.output)

    def test_cli_clean_audit_logs(self):
        # Create an old audit log
        old_time = datetime.now(timezone.utc) - timedelta(days=400)
        log = AuditLog(
            tabel="registraties",
            operatie="DELETE",
            gebruiker="Mark",
            timestamp=old_time
        )
        db.session.add(log)
        db.session.commit()

        runner = self.app.test_cli_runner()
        res = runner.invoke(args=['clean-audit-logs'])
        self.assertEqual(res.exit_code, 0)
        self.assertIn("Succesvol", res.output)

    def test_cli_seed_vraagcategorieen(self):
        runner = self.app.test_cli_runner()
        res = runner.invoke(args=['seed-vraagcategorieen'])
        self.assertEqual(res.exit_code, 0)
        self.assertIn("vraagcategorieën", res.output)

    def test_cli_seed_vragenanalyse(self):
        runner = self.app.test_cli_runner()
        with patch('utils.ai_classifier.seed_retroactieve_classificaties', return_value=(3, 0)):
            res = runner.invoke(args=['seed-vragenanalyse'])
            self.assertEqual(res.exit_code, 0)
            self.assertIn("Voltooid: 3 consultaties", res.output)

    def test_error_handlers(self):
        # 404 handler via client
        resp_404 = self.client.get('/deze-pagina-bestaat-absoluut-niet-404')
        self.assertEqual(resp_404.status_code, 404)

        with self.app.test_request_context('/'):
            # 403 handler
            handler_403 = self.app.error_handler_spec[None][403][Forbidden]
            res_403, code_403 = handler_403(Forbidden())
            self.assertEqual(code_403, 403)

            # 500 handler
            with patch('utils.mail.stuur_fout_email') as mock_foutmail:
                handler_500 = self.app.error_handler_spec[None][500][InternalServerError]
                res_500, code_500 = handler_500(InternalServerError("Crash 500"))
                self.assertEqual(code_500, 500)
                mock_foutmail.assert_called_once()

            # Unhandled Exception handler
            with patch('utils.mail.stuur_fout_email') as mock_foutmail2:
                handler_ex = self.app.error_handler_spec[None][None][Exception]
                res_ex, code_ex = handler_ex(RuntimeError("Onverwachte crash"))
                self.assertEqual(code_ex, 500)
                mock_foutmail2.assert_called_once()

    def test_pwa_routes(self):
        resp_sw = self.client.get('/sw.js')
        self.assertEqual(resp_sw.status_code, 200)
        self.assertIn('application/javascript', resp_sw.content_type)

    def test_before_request_redirects(self):
        # Logged in but without active organisation in session
        self.login("AdminMark", "password123")
        with self.client.session_transaction() as sess:
            sess.pop('organisatie_id', None)

        resp = self.client.get('/registraties/', follow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/select-organisatie', resp.location)

        # User in organisation 'sjabloon' accessing restricted route
        sjabloon_org = Organisatie.query.filter_by(slug='sjabloon').first()
        if not sjabloon_org:
            sjabloon_org = Organisatie(naam='Sjabloon Organisatie', slug='sjabloon', actief=True)
            db.session.add(sjabloon_org)
            db.session.commit()

        membership = UserOrganisatie(user_id=self.admin_user.id, organisatie_id=sjabloon_org.id, rol='beheerder', actief=True)
        db.session.add(membership)
        db.session.commit()

        with self.client.session_transaction() as sess:
            sess['organisatie_id'] = sjabloon_org.id

        resp_sjab = self.client.get('/registraties/nieuw', follow_redirects=False)
        self.assertEqual(resp_sjab.status_code, 302)

    def test_platformbeheerder_before_request_and_test_mail(self):
        # Create platform admin
        from werkzeug.security import generate_password_hash
        p_admin = User(
            naam="SuperAdminMark",
            email="superadminmark@example.com",
            wachtwoord_hash=generate_password_hash("password123"),
            rol="platformbeheerder",
            actief=True,
            moet_wachtwoord_wijzigen=False
        )
        db.session.add(p_admin)
        db.session.commit()

        self.login("SuperAdminMark", "password123")
        with self.client.session_transaction() as sess:
            sess['organisatie_id'] = self.org.id

        # 1. Access route with ?org_id=... parameter
        resp_org_switch = self.client.get(f'/registraties?org_id={self.org.id}', follow_redirects=True)
        self.assertEqual(resp_org_switch.status_code, 200)

        # 2. Test /test-mail without ?to=
        resp_nomail = self.client.get('/test-mail')
        self.assertEqual(resp_nomail.status_code, 400)

        # 3. Test /test-mail with ?to=
        with patch('utils.mail.verstuur_email', return_value=(True, "Verzonden")):
            resp_mail_ok = self.client.get('/test-mail?to=recipient@example.com')
            self.assertEqual(resp_mail_ok.status_code, 200)
            self.assertIn("success", resp_mail_ok.get_json()['status'])

        # 4. Test /test-mail as regular user
        self.logout()
        self.login("AdminMark", "password123")
        with self.client.session_transaction() as sess:
            sess['organisatie_id'] = self.org.id
        resp_forbidden = self.client.get('/test-mail')
        self.assertEqual(resp_forbidden.status_code, 403)

