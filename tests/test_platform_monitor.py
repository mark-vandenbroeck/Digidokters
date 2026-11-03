from datetime import datetime, date, timedelta, timezone
from unittest.mock import patch, MagicMock
from tests.base import BaseTestCase
from extensions import db
from models.user import User
from models.organisatie import Organisatie, UserOrganisatie
from models.telemetry import PageViewStat, SystemErrorLog
from utils.health import record_page_view, record_system_error, get_full_platform_health
from werkzeug.security import generate_password_hash


class TestPlatformMonitor(BaseTestCase):
    def setUp(self):
        super().setUp()

        # Maak een platformbeheerder aan
        self.platform_admin = User(
            naam="Super Admin",
            email="superadmin@test.be",
            wachtwoord_hash=generate_password_hash("AdminPass123!"),
            rol="platformbeheerder",
            actief=True
        )
        db.session.add(self.platform_admin)
        db.session.commit()

        # Koppel platformbeheerder aan org 1
        uo = UserOrganisatie(user_id=self.platform_admin.id, organisatie_id=1, rol="beheerder", actief=True)
        db.session.add(uo)
        db.session.commit()

    def test_access_control(self):
        """Alleen platformbeheerders mogen toegang hebben tot de systeemmonitor."""
        # 1. Niet ingelogd -> redirect naar login
        resp = self.client.get('/platform/systeemmonitor')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login', resp.headers['Location'])

        # 2. Gewone gebruiker -> geweigerd
        self.login("tim@test.com", "password123")
        resp = self.client.get('/platform/systeemmonitor', follow_redirects=True)
        self.assertIn('U heeft geen toegang tot deze pagina.', resp.get_data(as_text=True))
        self.logout()

        # 3. Platformbeheerder -> 200 OK
        self.login("superadmin@test.be", "AdminPass123!")
        resp = self.client.get('/platform/systeemmonitor')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Systeemmonitor', resp.get_data(as_text=True))
        self.assertIn('Systeemgezondheid', resp.get_data(as_text=True))

    def test_tab_gezondheid(self):
        """Controleer weergave van subsysteemkaarten in tab Gezondheid."""
        self.login("superadmin@test.be", "AdminPass123!")
        resp = self.client.get('/platform/systeemmonitor?tab=gezondheid')
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn('Database', html)
        self.assertIn('E-mail (SMTP)', html)
        self.assertIn('AI Classificatie', html)
        self.assertIn('Opslag & Schijfruimte', html)
        self.assertIn('Beveiliging & Limiter', html)
        self.assertIn('Systeeminformatie', html)

    def test_tab_live_gebruikers(self):
        """Controleer weergave van live actieve gebruikers en recente logins."""
        # Update laatste activiteit van platform admin
        now = datetime.now(timezone.utc)
        self.platform_admin.laatste_activiteit = now
        self.platform_admin.laatste_login = now
        db.session.commit()

        self.login("superadmin@test.be", "AdminPass123!")
        resp = self.client.get('/platform/systeemmonitor?tab=live')
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn('Live Sessies', html)
        self.assertIn('Super Admin', html)
        self.assertIn('Recente Aanmeldingen', html)

    def test_tab_paginagebruik(self):
        """Controleer paginagebruik en statistieken overzicht."""
        vandaag = date.today()
        stat1 = PageViewStat(datum=vandaag, endpoint='reg.lijst', pad='/registraties', label='Registraties Overzicht', aantal_hits=42, organisatie_id=1)
        stat2 = PageViewStat(datum=vandaag, endpoint='agenda.lijst', pad='/agenda', label='Agenda Overzicht', aantal_hits=15, organisatie_id=1)
        db.session.add_all([stat1, stat2])
        db.session.commit()

        self.login("superadmin@test.be", "AdminPass123!")
        resp = self.client.get('/platform/systeemmonitor?tab=gebruik&periode=7d')
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn('Top Bezochte Schermen', html)
        self.assertIn('Registraties Overzicht', html)
        self.assertIn('reg.lijst', html)
        self.assertIn('57', html)  # 42 + 15 = 57 totaal weergaven
        # Verifieer dat Chart.js met SRI integrity en crossorigin geladen wordt
        self.assertIn('integrity="sha384-NrKB+u6Ts6AtkIhwPixiKTzgSKNblyhlk0Sohlgar9UHUBzai/sgnNNWWd291xqt"', html)
        self.assertIn('crossorigin="anonymous"', html)

    def test_tab_fouten_and_toggle(self):
        """Controleer foutenlogboek en markeren van fouten als opgelost."""
        err = SystemErrorLog(
            timestamp=datetime.now(timezone.utc),
            status_code=500,
            type_fout='ZeroDivisionError',
            bericht='division by zero in calculation',
            stacktrace='Traceback (most recent call last)...',
            endpoint='platform.test',
            pad='/test-err',
            is_opgelost=False
        )
        db.session.add(err)
        db.session.commit()

        self.login("superadmin@test.be", "AdminPass123!")
        resp = self.client.get('/platform/systeemmonitor?tab=fouten&status=onopgelost')
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn('ZeroDivisionError', html)
        self.assertIn('division by zero in calculation', html)

        # Markeer als opgelost via POST
        toggle_resp = self.client.post(
            f'/platform/systeemmonitor/fout/{err.id}/toggle-status',
            headers={'X-Requested-With': 'XMLHttpRequest'}
        )
        self.assertEqual(toggle_resp.status_code, 200)
        data = toggle_resp.get_json()
        self.assertTrue(data['success'])
        self.assertTrue(data['is_opgelost'])
        self.assertEqual(data['opgelost_door'], 'Super Admin')

        # Controleer in database
        db.session.refresh(err)
        self.assertTrue(err.is_opgelost)
        self.assertIsNotNone(err.opgelost_op)

        # Toggle opnieuw naar onopgelost
        toggle_resp2 = self.client.post(f'/platform/systeemmonitor/fout/{err.id}/toggle-status')
        self.assertEqual(toggle_resp2.status_code, 302)
        db.session.refresh(err)
        self.assertFalse(err.is_opgelost)

    def test_api_gezondheid(self):
        """Controleer de JSON gezondheids-API."""
        self.login("superadmin@test.be", "AdminPass123!")
        resp = self.client.get('/platform/systeemmonitor/api/gezondheid')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn('overall_status', data)
        self.assertIn('database', data)
        self.assertIn('email', data)
        self.assertIn('ai', data)
        self.assertIn('storage', data)
        self.assertIn('security', data)
        self.assertIn('system', data)

    def test_record_page_view_and_user_activity(self):
        """Test automatische registratie van activiteit en paginabezoek."""
        self.login("superadmin@test.be", "AdminPass123!")

        # Haal een pagina op (bijv. /platform/dashboard)
        resp = self.client.get('/platform/dashboard')
        self.assertEqual(resp.status_code, 200)

        # Controleer dat de gebruiker een laatste_activiteit timestamp heeft gekregen
        db.session.refresh(self.platform_admin)
        self.assertIsNotNone(self.platform_admin.laatste_activiteit)

        # Controleer dat er een PageViewStat is geregistreerd voor platform.dashboard
        vandaag = date.today()
        stat = PageViewStat.query.filter_by(datum=vandaag, endpoint='platform.dashboard').first()
        self.assertIsNotNone(stat)
        self.assertGreaterEqual(stat.aantal_hits, 1)

    def test_record_failed_login(self):
        """Mislukte logins moeten in SystemErrorLog worden opgenomen."""
        self.client.post('/login', data={
            'email': 'superadmin@test.be',
            'wachtwoord': 'WrongPassword123!'
        })
        err = SystemErrorLog.query.filter_by(type_fout='LoginFailed').first()
        self.assertIsNotNone(err)
        self.assertIn('superadmin@test.be', err.bericht)
        self.assertEqual(err.endpoint, 'auth.login')

    def test_check_email_health_with_brevo_api(self):
        """Test dat check_email_health automatisch de Brevo HTTPS API herkent en controleert via poort 443."""
        import os
        from utils.health import check_email_health

        with patch.dict(os.environ, {'BREVO_API_KEY': 'xkeysib-mock-key-123'}):
            with patch('socket.create_connection') as mock_conn:
                mock_conn.return_value = MagicMock()
                res = check_email_health()
                self.assertTrue(res['is_api'])
                self.assertEqual(res['protocol'], 'Brevo API')
                self.assertEqual(res['server'], 'api.brevo.com')
                self.assertEqual(res['port'], 443)
                self.assertEqual(res['status'], 'ok')
                mock_conn.assert_called_with(('api.brevo.com', 443), timeout=3.0)

        # Controleer weergave op systeemmonitor pagina
        self.login("superadmin@test.be", "AdminPass123!")
        with patch.dict(os.environ, {'BREVO_API_KEY': 'xkeysib-mock-key-123'}):
            with patch('socket.create_connection'):
                resp = self.client.get('/platform/systeemmonitor?tab=gezondheid')
                self.assertEqual(resp.status_code, 200)
                html = resp.get_data(as_text=True)
                self.assertIn('E-mail (Brevo API)', html)
                self.assertIn('api.brevo.com', html)
                self.assertIn('HTTPS', html)

    def test_check_ai_health_gemini(self):
        """Test dat check_ai_health Google Gemini correct herkent wanneer GEMINI_API_KEY is ingesteld."""
        import os
        from utils.health import check_ai_health

        with patch.dict(os.environ, {'GEMINI_API_KEY': 'mock-gemini-key', 'AI_MODEL': 'gemini-3.5-flash'}):
            res = check_ai_health()
            self.assertEqual(res['status'], 'ok')
            self.assertEqual(res['provider'], 'Google Gemini')
            self.assertEqual(res['model'], 'gemini-3.5-flash')
            self.assertTrue(res['has_api_key'])
            self.assertIn('Google Gemini', res['details'])

        # Controleer HTML weergave op systeemmonitor pagina
        self.login("superadmin@test.be", "AdminPass123!")
        with patch.dict(os.environ, {'GEMINI_API_KEY': 'mock-gemini-key'}):
            resp = self.client.get('/platform/systeemmonitor?tab=gezondheid')
            self.assertEqual(resp.status_code, 200)
            html = resp.get_data(as_text=True)
            self.assertIn('Google Gemini', html)
            self.assertIn('Ingesteld', html)
            self.assertIn('Geconfigureerd', html)



    def test_health_module_extended_coverage(self):
        """Test alle edge cases en foutcondities in utils.health."""
        from utils.health import (
            get_friendly_endpoint_label, record_page_view, record_system_error,
            check_database_health, check_email_health, check_ai_health,
            check_storage_health, get_full_platform_health
        )

        # 1. get_friendly_endpoint_label leeg
        self.assertEqual(get_friendly_endpoint_label(""), "Onbekende pagina")
        self.assertEqual(get_friendly_endpoint_label(None), "Onbekende pagina")
        self.assertEqual(get_friendly_endpoint_label("custom.mijn_route"), "Custom Mijn route")

        # 2. record_page_view: genegeerde endpoints
        record_page_view("static.file", "/static/test.css")
        record_page_view("ping", "/ping")
        record_page_view("service_worker", "/sw.js")

        # 3. record_page_view: reeds bestaande stat updaten
        record_page_view("mijn.test.pagina", "/mijn/test", org_id=self.org.id)
        # Tweede keer aanroepen -> stat.aantal_hits += 1
        record_page_view("mijn.test.pagina", "/mijn/test/nieuw", org_id=self.org.id)

        # record_page_view exception rollback
        with patch('extensions.db.session.commit') as mock_commit:
            mock_commit.side_effect = Exception("DB error")
            record_page_view("mijn.fout.pagina", "/fout")

        # 4. record_system_error exception rollback
        with patch('extensions.db.session.commit') as mock_commit:
            mock_commit.side_effect = Exception("DB error")
            record_system_error(500, "Error", "Test")

        # 5. check_database_health: latency warning & exception
        with patch.object(db.engine.dialect, 'name', 'postgresql'):
            with patch('extensions.db.session.execute') as mock_exec:
                mock_scalar = MagicMock()
                mock_scalar.scalar.return_value = 'test_db'
                mock_exec.return_value = mock_scalar
                res_pg = check_database_health()
                self.assertEqual(res_pg['db_type'], 'PostgreSQL')

        with patch('extensions.db.session.execute') as mock_exec:
            mock_exec.side_effect = Exception("DB connection timeout")
            res_err = check_database_health()
            self.assertEqual(res_err['status'], 'danger')
            self.assertIn("DB connection timeout", res_err['error'])

        # 6. check_email_health: Brevo socket fout
        import os
        with patch.dict(os.environ, {'BREVO_API_KEY': 'test-key'}):
            with patch('socket.create_connection') as mock_sock:
                mock_sock.side_effect = Exception("Network unreachable")
                res_brevo_err = check_email_health()
                self.assertEqual(res_brevo_err['status'], 'warning')
                self.assertIn("niet bereikbaar", res_brevo_err['error'])

        # check_email_health: SMTP geconfigureerd met connectie-fout
        with patch.dict(os.environ, {'BREVO_API_KEY': '', 'BREVO_KEY': '', 'SMTP_PASSWORD': ''}):
            with self.app.test_request_context('/'):
                self.app.config['MAIL_SERVER'] = 'smtp.example.org'
                self.app.config['MAIL_PORT'] = 587
                with patch('socket.create_connection') as mock_sock:
                    mock_sock.side_effect = Exception("Connection refused")
                    res_smtp_err = check_email_health()
                    self.assertEqual(res_smtp_err['status'], 'warning')
                    self.assertIn("niet bereikbaar", res_smtp_err['error'])

        # 7. check_ai_health: OpenAI & Custom model
        with patch.dict(os.environ, {
            'OPENAI_API_KEY': 'sk-test',
            'AI_MODEL': 'custom-gpt-5',
            'GEMINI_API_KEY': ''
        }):
            res_ai_custom = check_ai_health()
            self.assertEqual(res_ai_custom['model'], 'custom-gpt-5')
            self.assertEqual(res_ai_custom['status'], 'ok')

        with patch.dict(os.environ, {
            'OPENAI_API_KEY': 'sk-test',
            'AI_MODEL': '',
            'GEMINI_API_KEY': ''
        }):
            res_ai_openai = check_ai_health()
            self.assertEqual(res_ai_openai['model'], 'gpt-4o-mini')

        with patch('utils.ai_classifier.get_actieve_provider') as mock_prov:
            mock_prov.side_effect = Exception("AI crash")
            res_ai_err = check_ai_health()
            self.assertEqual(res_ai_err['status'], 'info')
            self.assertIn("AI crash", res_ai_err['error'])

        # 8. check_storage_health: percentage waarschuwingen en niet-schrijfbaar
        from collections import namedtuple
        DiskUsage = namedtuple('DiskUsage', ['total', 'used', 'free'])
        with patch('shutil.disk_usage') as mock_usage:
            # 96% vol
            mock_usage.return_value = DiskUsage(100 * 1024**3, 96 * 1024**3, 4 * 1024**3)
            with patch('os.access', return_value=False):
                res_storage = check_storage_health()
                self.assertEqual(res_storage['status'], 'danger')

        with patch('shutil.disk_usage') as mock_usage:
            mock_usage.side_effect = Exception("Disk error")
            res_storage_err = check_storage_health()
            self.assertEqual(res_storage_err['status'], 'warning')

        # 9. get_full_platform_health aanroepen
        with self.app.test_request_context('/'):
            full_health = get_full_platform_health()
            self.assertIn('overall_status', full_health)
            self.assertIn('database', full_health)
            self.assertIn('email', full_health)
            self.assertIn('storage', full_health)
