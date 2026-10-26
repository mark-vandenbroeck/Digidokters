from datetime import datetime, date, timedelta, timezone
from unittest.mock import patch
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
