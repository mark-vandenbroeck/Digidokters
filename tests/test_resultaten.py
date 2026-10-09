import json
from datetime import date
from io import BytesIO
from extensions import db
from models.registration import Registration
from models.resultaat import Resultaat
from models.organisatie import Organisatie, UserOrganisatie
from utils.backup_handler import maak_backup, herstel_backup
from utils.export_handler import exporteer_csv, exporteer_xlsx
from utils.tenant import seed_organisatie_defaults
from tests.base import BaseTestCase


class ResultatenTestCase(BaseTestCase):

    def test_model_resultaat(self):
        """Test Resultaat model properties and relationships."""
        res = Resultaat(
            omschrijving="Speciale afloop",
            actief=True,
            volgorde=10,
            organisatie_id=self.org.id
        )
        db.session.add(res)
        db.session.commit()

        self.assertEqual(res.naam, "Speciale afloop")
        self.assertEqual(str(res), "<Resultaat Speciale afloop>")
        self.assertEqual(len(res.registraties), 0)

    def test_seed_organisatie_defaults(self):
        """Test that seed_organisatie_defaults creates the 5 default resultaten."""
        new_org = Organisatie(naam="Nieuwe Org", slug="nieuwe-org", actief=True)
        db.session.add(new_org)
        db.session.commit()

        seed_organisatie_defaults(new_org.id)

        resultaten = Resultaat.query.filter_by(organisatie_id=new_org.id).order_by(Resultaat.volgorde).all()
        expected = [
            'Vraag beantwoord',
            'Bezoeker komt later terug',
            'Bezoeker doorverwezen',
            'Vraag onmogelijk te beantwoorden',
            'Andere'
        ]
        self.assertEqual([r.omschrijving for r in resultaten], expected)

    def test_admin_access_control(self):
        """Test that only beheerder can access /beheer/resultaten."""
        # Niet ingelogd
        resp = self.client.get('/beheer/resultaten')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login', resp.headers['Location'])

        # Medewerker -> access denied (redirect naar /registraties)
        self.login('tim@test.com', 'password123')
        self.select_organisatie(self.org.id)
        resp = self.client.get('/beheer/resultaten')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/registraties', resp.headers['Location'])
        self.logout()

        # Beheerder
        self.login('admin@test.com', 'password123')
        self.select_organisatie(self.org.id)
        resp = self.client.get('/beheer/resultaten')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Resultaten van het bezoek', resp.data)

    def test_admin_crud_resultaten(self):
        """Test full CRUD, toggle and ordering of resultaten by admin."""
        self.login('admin@test.com', 'password123')
        self.select_organisatie(self.org.id)

        # Toevoegen
        resp = self.client.post('/beheer/resultaten/nieuw', data={
            'omschrijving': 'Nieuw Resultaat Type'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        nieuw_res = Resultaat.query.filter_by(omschrijving='Nieuw Resultaat Type', organisatie_id=self.org.id).first()
        self.assertIsNotNone(nieuw_res)

        # Dubbele naam afkeuren
        resp = self.client.post('/beheer/resultaten/nieuw', data={
            'omschrijving': 'Nieuw Resultaat Type'
        }, follow_redirects=True)
        self.assertIn('bestaat al', resp.data.decode('utf-8'))

        # Wijzigen
        resp = self.client.post(f'/beheer/resultaten/{nieuw_res.id}/wijzig', data={
            'omschrijving': 'Gewijzigd Resultaat Type',
            'actief': 'on'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        db.session.refresh(nieuw_res)
        self.assertEqual(nieuw_res.omschrijving, 'Gewijzigd Resultaat Type')
        self.assertTrue(nieuw_res.actief)

        # Deactiveren / Toggle
        resp = self.client.get(f'/beheer/resultaten/{nieuw_res.id}/toggle', follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        db.session.refresh(nieuw_res)
        self.assertFalse(nieuw_res.actief)

        # Reorder
        resp = self.client.get(f'/beheer/resultaten/{nieuw_res.id}/volgorde/omhoog', follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        # Verwijderen zonder gekoppelde registraties
        res_id = nieuw_res.id
        resp = self.client.post(f'/beheer/resultaten/{res_id}/verwijderen', follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(db.session.get(Resultaat, res_id))

    def test_prevent_delete_when_used(self):
        """Test safe delete protection when registrations use the resultaat."""
        self.login('admin@test.com', 'password123')
        self.select_organisatie(self.org.id)

        # Maak registratie met resultaat
        reg = Registration(
            registratienummer="2026-TEST-001",
            datum=date(2026, 10, 1),
            client="Jan Jansen",
            onderwerp="Hulp bij printer",
            resultaat_id=self.resultaat_beantwoord.id,
            digidokter_id=self.digidokter.id,
            leeftijdscategorie_id=self.age_category.id,
            toestel_id=self.device.id,
            organisatie_id=self.org.id,
            aangemaakt_door_id=self.admin_user.id
        )
        db.session.add(reg)
        db.session.commit()

        # Probeer resultaat te verwijderen
        resp = self.client.post(f'/beheer/resultaten/{self.resultaat_beantwoord.id}/verwijderen', follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn('kan niet worden verwijderd omdat er nog 1 registratie(s) aan gekoppeld zijn', resp.data.decode('utf-8'))

        # Verifieer dat resultaat nog bestaat
        db.session.refresh(self.resultaat_beantwoord)
        self.assertIsNotNone(self.resultaat_beantwoord)

    def test_registration_with_resultaat(self):
        """Test creating, editing, viewing, and filtering registrations with resultaat."""
        self.login('tim@test.com', 'password123')
        self.select_organisatie(self.org.id)

        # Formulier openen -> Resultaat veld moet aanwezig zijn
        resp = self.client.get('/registraties/nieuw')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Resultaat', resp.data)
        self.assertIn(b'Vraag beantwoord', resp.data)

        # Nieuwe registratie aanmaken met resultaat
        resp = self.client.post('/registraties/nieuw', data={
            'datum': '2026-10-09',
            'client': 'Piet Peeters',
            'digidokter_id': self.digidokter.id,
            'leeftijdscategorie_id': self.age_category.id,
            'toestel_id': self.device.id,
            'herkomst_id': self.herkomst.id,
            'gender_identity_id': self.gender_man.id,
            'onderwerp': 'Probleem met e-mail instellen',
            'resultaat_id': self.resultaat_beantwoord.id,
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        reg = Registration.query.filter_by(client='Piet Peeters').first()
        self.assertIsNotNone(reg)
        self.assertEqual(reg.resultaat_id, self.resultaat_beantwoord.id)
        self.assertEqual(reg.resultaat.omschrijving, 'Vraag beantwoord')

        # Bekijken pagina tonen
        resp = self.client.get(f'/registraties/{reg.id}')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Vraag beantwoord', resp.data)

        # Wijzigen pagina
        resp = self.client.post(f'/registraties/{reg.id}/wijzig', data={
            'datum': '2026-10-09',
            'client': 'Piet Peeters',
            'digidokter_id': self.digidokter.id,
            'leeftijdscategorie_id': self.age_category.id,
            'toestel_id': self.device.id,
            'herkomst_id': self.herkomst.id,
            'gender_identity_id': self.gender_man.id,
            'onderwerp': 'Probleem met e-mail instellen',
            'resultaat_id': self.resultaat_doorverwezen.id,
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        db.session.refresh(reg)
        self.assertEqual(reg.resultaat_id, self.resultaat_doorverwezen.id)

        # Snelle registratie
        resp = self.client.post('/registraties/snel', data={
            'datum': '2026-10-09',
            'client': 'Anna De Smet',
            'digidokter_id': self.digidokter.id,
            'leeftijdscategorie_id': self.age_category.id,
            'toestel_id': self.device.id,
            'herkomst_id': self.herkomst.id,
            'gender_identity_id': self.gender_vrouw.id,
            'onderwerp': 'Tablet updates',
            'resultaat_id': self.resultaat_terug.id,
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        reg_snel = Registration.query.filter_by(client='Anna De Smet').first()
        self.assertIsNotNone(reg_snel)
        self.assertEqual(reg_snel.resultaat_id, self.resultaat_terug.id)

        # Filteren in lijst
        resp = self.client.get(f'/registraties?resultaat={self.resultaat_doorverwezen.id}')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Piet Peeters', resp.data)
        self.assertNotIn(b'Anna De Smet', resp.data)

    def test_conditional_visibility_when_no_resultaten(self):
        """Test that Resultaat field is NOT rendered when organisation has no resultaten."""
        # Verwijder alle resultaten voor deze test
        Resultaat.query.filter_by(organisatie_id=self.org.id).delete()
        db.session.commit()

        self.login('tim@test.com', 'password123')
        self.select_organisatie(self.org.id)

        resp = self.client.get('/registraties/nieuw')
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(b'name="resultaat_id"', resp.data)

        resp = self.client.get('/registraties/snel')
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(b'name="resultaat_id"', resp.data)

        resp = self.client.get('/exporteer')
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(b'name="resultaat_id"', resp.data)

    def test_statistics_with_resultaat(self):
        """Test outcome statistics calculations in /statistieken."""
        # Maak 2 registraties
        reg1 = Registration(
            registratienummer="2026-STAT-001",
            datum=date(2026, 10, 1),
            client="Klant 1",
            onderwerp="Vraag 1",
            resultaat_id=self.resultaat_beantwoord.id,
            digidokter_id=self.digidokter.id,
            leeftijdscategorie_id=self.age_category.id,
            toestel_id=self.device.id,
            organisatie_id=self.org.id,
            aangemaakt_door_id=self.admin_user.id
        )
        reg2 = Registration(
            registratienummer="2026-STAT-002",
            datum=date(2026, 10, 2),
            client="Klant 2",
            onderwerp="Vraag 2",
            resultaat_id=self.resultaat_doorverwezen.id,
            digidokter_id=self.digidokter.id,
            leeftijdscategorie_id=self.age_category.id,
            toestel_id=self.device.id,
            organisatie_id=self.org.id,
            aangemaakt_door_id=self.admin_user.id
        )
        db.session.add_all([reg1, reg2])
        db.session.commit()

        self.login('admin@test.com', 'password123')
        self.select_organisatie(self.org.id)
        resp = self.client.get('/statistieken?jaar=2026')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Resultaat van het bezoek', resp.data)
        self.assertIn(b'Vraag beantwoord', resp.data)
        self.assertIn(b'Bezoeker doorverwezen', resp.data)

    def test_export_and_backup_with_resultaat(self):
        """Test that CSV, XLSX and JSON backup contain resultaat data."""
        reg = Registration(
            registratienummer="2026-EXP-001",
            datum=date(2026, 10, 1),
            client="Export Test",
            onderwerp="Test export",
            resultaat_id=self.resultaat_beantwoord.id,
            digidokter_id=self.digidokter.id,
            leeftijdscategorie_id=self.age_category.id,
            toestel_id=self.device.id,
            organisatie_id=self.org.id,
            aangemaakt_door_id=self.admin_user.id
        )
        db.session.add(reg)
        db.session.commit()

        self.login('admin@test.com', 'password123')
        self.select_organisatie(self.org.id)

        # CSV Export within active request context
        with self.app.test_request_context():
            from flask import session
            from flask_login import login_user
            login_user(self.admin_user)
            session['organisatie_id'] = self.org.id
            csv_bytes = exporteer_csv()
            self.assertIn(b'Resultaat', csv_bytes)
            self.assertIn('Vraag beantwoord'.encode('utf-8'), csv_bytes)

            # XLSX Export
            xlsx_bytes = exporteer_xlsx()
            self.assertTrue(len(xlsx_bytes) > 0)

        # Backup export
        backup_data = maak_backup(self.org.id)
        self.assertIn('resultaten', backup_data)
        self.assertEqual(len(backup_data['resultaten']), 5)
        self.assertEqual(backup_data['registrations'][0]['resultaat_omschrijving'], 'Vraag beantwoord')

        # Backup restore
        backup_bytes = BytesIO(json.dumps(backup_data).encode('utf-8'))
        success, msg = herstel_backup(self.org.id, backup_bytes, self.admin_user.id)
        self.assertTrue(success)

        restored_reg = Registration.query.filter_by(registratienummer="2026-EXP-001").first()
        self.assertIsNotNone(restored_reg)
        self.assertIsNotNone(restored_reg.resultaat)
        self.assertEqual(restored_reg.resultaat.omschrijving, 'Vraag beantwoord')

    def test_export_filtered_by_resultaat(self):
        """Test exporting registrations filtered by resultaat_id."""
        reg1 = Registration(
            registratienummer="2026-FILT-001",
            datum=date(2026, 10, 1),
            client="Filter Beantwoord",
            onderwerp="Vraag 1",
            resultaat_id=self.resultaat_beantwoord.id,
            digidokter_id=self.digidokter.id,
            leeftijdscategorie_id=self.age_category.id,
            toestel_id=self.device.id,
            organisatie_id=self.org.id,
            aangemaakt_door_id=self.admin_user.id
        )
        reg2 = Registration(
            registratienummer="2026-FILT-002",
            datum=date(2026, 10, 2),
            client="Filter Doorverwezen",
            onderwerp="Vraag 2",
            resultaat_id=self.resultaat_doorverwezen.id,
            digidokter_id=self.digidokter.id,
            leeftijdscategorie_id=self.age_category.id,
            toestel_id=self.device.id,
            organisatie_id=self.org.id,
            aangemaakt_door_id=self.admin_user.id
        )
        db.session.add_all([reg1, reg2])
        db.session.commit()

        self.login('admin@test.com', 'password123')
        self.select_organisatie(self.org.id)

        # GET /exporteer form view includes resultaat dropdown
        resp = self.client.get('/exporteer')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'name="resultaat_id"', resp.data)
        self.assertIn(b'Vraag beantwoord', resp.data)

        # POST /exporteer with resultaat_id filter for CSV
        resp = self.client.post('/exporteer', data={
            'formaat': 'csv',
            'resultaat_id': self.resultaat_beantwoord.id
        })
        self.assertEqual(resp.status_code, 200)
        csv_data = resp.data.decode('utf-8-sig')
        self.assertIn('Filter Beantwoord', csv_data)
        self.assertNotIn('Filter Doorverwezen', csv_data)

        # POST /exporteer with resultaat_id filter for XLSX
        resp = self.client.post('/exporteer', data={
            'formaat': 'xlsx',
            'resultaat_id': self.resultaat_doorverwezen.id
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.mimetype, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
