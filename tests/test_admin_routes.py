import io
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from werkzeug.security import check_password_hash, generate_password_hash

from tests.base import BaseTestCase
from extensions import db
from models.user import User
from models.organisatie import Organisatie, UserOrganisatie
from models.digidokter import Digidokter
from models.functie import Functie
from models.location import Location
from models.activity_type import ActivityType
from models.audit import AuditLog


class TestAdminRoutes(BaseTestCase):
    def login_admin(self):
        with self.client.session_transaction() as sess:
            sess['organisatie_id'] = self.org.id
        return self.client.post('/login', data={
            'email': 'admin@test.com',
            'wachtwoord': 'password123'
        }, follow_redirects=True)

    def login_medewerker(self):
        with self.client.session_transaction() as sess:
            sess['organisatie_id'] = self.org.id
        return self.client.post('/login', data={
            'email': 'tim@test.com',
            'wachtwoord': 'password123'
        }, follow_redirects=True)

    def test_gebruikers_list_filters_and_sorting(self):
        """Test overzicht van gebruikers met statusfilters en kolomsorteringen."""
        self.login_admin()

        # Maak extra inactieve gebruiker
        u_inactive = User(
            naam="Inactieve Gebruiker",
            email="inactive@test.com",
            wachtwoord_hash=generate_password_hash("password123"),
            rol="medewerker",
            actief=False
        )
        db.session.add(u_inactive)
        db.session.commit()
        db.session.add(UserOrganisatie(user_id=u_inactive.id, organisatie_id=self.org.id, rol="medewerker", actief=False))
        db.session.commit()

        # 1. Filter alle
        res_alle = self.client.get('/beheer/gebruikers?status=alle')
        self.assertEqual(res_alle.status_code, 200)
        self.assertIn("AdminMark", res_alle.get_data(as_text=True))
        self.assertIn("UserTim", res_alle.get_data(as_text=True))
        self.assertIn("Inactieve Gebruiker", res_alle.get_data(as_text=True))

        # 2. Filter actief
        res_actief = self.client.get('/beheer/gebruikers?status=actief')
        self.assertEqual(res_actief.status_code, 200)
        self.assertIn("AdminMark", res_actief.get_data(as_text=True))
        self.assertNotIn("Inactieve Gebruiker", res_actief.get_data(as_text=True))

        # 3. Filter inactief
        res_inactief = self.client.get('/beheer/gebruikers?status=inactief')
        self.assertEqual(res_inactief.status_code, 200)
        self.assertNotIn("UserTim", res_inactief.get_data(as_text=True))
        self.assertIn("Inactieve Gebruiker", res_inactief.get_data(as_text=True))

        # 4. Sortering op verschillende kolommen
        for sort_col in ['naam', 'email', 'rol', 'status', 'laatste_login']:
            for direction in ['asc', 'desc']:
                res_sort = self.client.get(f'/beheer/gebruikers?sort_by={sort_col}&direction={direction}')
                self.assertEqual(res_sort.status_code, 200)

    def test_gebruiker_nieuw_validation_failures(self):
        """Test validatiefouten bij het aanmaken van een gebruiker."""
        self.login_admin()

        # 1. Niet-platformbeheerder probeert platformbeheerder rol toe te kennen
        res_pb = self.client.post('/beheer/gebruikers/nieuw', data={
            'naam': 'Illegale PB',
            'email': 'pb@test.com',
            'wachtwoord': 'password123',
            'rol': 'platformbeheerder'
        }, follow_redirects=True)
        self.assertEqual(res_pb.status_code, 200)
        self.assertIn("niet gemachtigd om de platformbeheerder rol toe te kennen", res_pb.get_data(as_text=True).lower())

        # 2. Lege verplichte velden (naam, email, wachtwoord)
        res_empty = self.client.post('/beheer/gebruikers/nieuw', data={
            'naam': '',
            'email': '',
            'wachtwoord': '',
            'rol': 'medewerker'
        }, follow_redirects=True)
        self.assertEqual(res_empty.status_code, 200)
        self.assertIn("naam, e-mailadres en wachtwoord zijn verplicht", res_empty.get_data(as_text=True).lower())

    @patch('utils.mail.stuur_welkomst_email')
    def test_gebruiker_nieuw_success_with_functions_and_digidokter(self, mock_mail):
        """Test succesvol aanmaken van een nieuwe gebruiker inclusief functies en digidokter record."""
        mock_mail.return_value = (True, "OK")
        self.login_admin()

        res = self.client.post('/beheer/gebruikers/nieuw', data={
            'naam': 'Nieuwe Vrijwilliger',
            'email': 'vrijwilliger@test.com',
            'telefoonnummer': '0471234567',
            'wachtwoord': 'tempPass123!',
            'rol': 'medewerker',
            'actief': 'on',
            'functie_ids': [str(self.functie_digidokter.id), str(self.functie_digihelper.id)]
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn("aangemaakt", res.get_data(as_text=True).lower())

        created = User.query.filter_by(email='vrijwilliger@test.com').first()
        self.assertIsNotNone(created)
        self.assertEqual(created.naam, 'Nieuwe Vrijwilliger')
        self.assertEqual(created.telefoonnummer, '0471234567')
        self.assertTrue(created.moet_wachtwoord_wijzigen)
        self.assertEqual(len(created.functies), 2)

        # Digidokter record moet automatisch aangemaakt zijn
        dd = Digidokter.query.filter_by(naam='Nieuwe Vrijwilliger', organisatie_id=self.org.id).first()
        self.assertIsNotNone(dd)
        self.assertTrue(dd.actief)

        # Welkomstmail moet verzonden zijn
        mock_mail.assert_called_once_with('vrijwilliger@test.com', 'Nieuwe Vrijwilliger', 'tempPass123!', organisatie_id=self.org.id)

    def test_gebruiker_nieuw_link_existing_global_user(self):
        """Test dat een bestaande globale gebruiker (uit andere org) gekoppeld wordt aan de huidige organisatie."""
        # Maak 2e organisatie aan
        org2 = Organisatie(naam="Tweede Org", slug="org2", actief=True)
        db.session.add(org2)
        db.session.commit()

        # Maak gebruiker in org2
        global_user = User(
            naam="Bestaande Global",
            email="global@test.com",
            wachtwoord_hash=generate_password_hash("pass123"),
            rol="medewerker",
            actief=True
        )
        db.session.add(global_user)
        db.session.commit()
        db.session.add(UserOrganisatie(user_id=global_user.id, organisatie_id=org2.id, rol="medewerker", actief=True))
        db.session.commit()

        # Admin van org1 logt in en voegt 'global@test.com' toe
        self.login_admin()
        res = self.client.post('/beheer/gebruikers/nieuw', data={
            'naam': 'Bestaande Global',
            'email': 'global@test.com',
            'wachtwoord': 'ignoredPassword',
            'rol': 'medewerker',
            'actief': 'on',
            'functie_ids': [str(self.functie_digidokter.id)]
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn("gekoppeld aan de organisatie", res.get_data(as_text=True).lower())

        # Controleer UserOrganisatie in org1
        uo = UserOrganisatie.query.filter_by(user_id=global_user.id, organisatie_id=self.org.id).first()
        self.assertIsNotNone(uo)
        self.assertTrue(uo.actief)

        # Probeer opnieuw toevoegen in org1 -> foutmelding dat gebruiker al bestaat in deze org
        res_dup = self.client.post('/beheer/gebruikers/nieuw', data={
            'naam': 'Bestaande Global',
            'email': 'global@test.com',
            'wachtwoord': 'ignoredPassword',
            'rol': 'medewerker'
        }, follow_redirects=True)
        self.assertEqual(res_dup.status_code, 200)
        self.assertIn("bestaat al een gebruiker met dit e-mailadres in deze organisatie", res_dup.get_data(as_text=True).lower())

    def test_gebruiker_wijzigen_cross_tenant_forbidden(self):
        """Test dat een beheerder geen gebruiker uit een andere organisatie kan bewerken."""
        org2 = Organisatie(naam="Org 2", slug="org-2", actief=True)
        db.session.add(org2)
        db.session.commit()

        other_user = User(naam="Ander", email="ander@org2.com", wachtwoord_hash="hash", rol="medewerker", actief=True)
        db.session.add(other_user)
        db.session.commit()
        db.session.add(UserOrganisatie(user_id=other_user.id, organisatie_id=org2.id, rol="medewerker", actief=True))
        db.session.commit()

        self.login_admin()

        # GET wijzigen op other_user (niet in tenant) -> 404
        res_get = self.client.get(f'/beheer/gebruikers/{other_user.id}/wijzig')
        self.assertEqual(res_get.status_code, 404)

        # POST wijzigen op other_user -> 404
        res_post = self.client.post(f'/beheer/gebruikers/{other_user.id}/wijzig', data={'naam': 'Gehackt'})
        self.assertEqual(res_post.status_code, 404)

    def test_gebruiker_wijzigen_self_protection(self):
        """Test dat beheerder 1 beschermd is tegen deactiveren en niet-platformbeheerders geen platformadmin rol kunnen toekennen."""
        self.login_admin()

        # 1. Probeer platformbeheerder rol toe te kennen zonder rechten
        res_pb = self.client.post(f'/beheer/gebruikers/{self.medewerker_user.id}/wijzig', data={
            'naam': 'UserTim',
            'email': 'tim@test.com',
            'rol': 'platformbeheerder',
            'actief': 'on'
        }, follow_redirects=True)
        self.assertEqual(res_pb.status_code, 200)
        self.assertIn("niet gemachtigd om de platformbeheerder rol toe te kennen", res_pb.get_data(as_text=True).lower())

        # 2. Beheerder id 1 deactiveren poging wordt genegeerd en blijft actief
        res_deact = self.client.post(f'/beheer/gebruikers/{self.admin_user.id}/wijzig', data={
            'naam': 'AdminMark',
            'email': 'admin@test.com',
            'rol': 'beheerder'
            # actief ontbreekt -> zou False zijn voor andere users
        }, follow_redirects=True)
        self.assertEqual(res_deact.status_code, 200)
        uo = UserOrganisatie.query.filter_by(user_id=self.admin_user.id, organisatie_id=self.org.id).first()
        self.assertTrue(uo.actief)

    def test_gebruiker_wijzigen_password_and_functions(self):
        """Test succesvol wijzigen van gebruikersgegevens, wachtwoord en functies."""
        self.login_admin()

        res = self.client.post(f'/beheer/gebruikers/{self.medewerker_user.id}/wijzig', data={
            'naam': 'UserTim Aangepast',
            'email': 'tim.nieuw@test.com',
            'telefoonnummer': '0123456789',
            'rol': 'medewerker',
            'actief': 'on',
            'wachtwoord': 'nieuwSecret123',
            'functie_ids': [str(self.functie_lesgever.id)]
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn("bijgewerkt", res.get_data(as_text=True).lower())

        db.session.refresh(self.medewerker_user)
        self.assertEqual(self.medewerker_user.naam, 'UserTim Aangepast')
        self.assertEqual(self.medewerker_user.email, 'tim.nieuw@test.com')
        self.assertEqual(self.medewerker_user.telefoonnummer, '0123456789')
        self.assertTrue(check_password_hash(self.medewerker_user.wachtwoord_hash, 'nieuwSecret123'))
        self.assertEqual(len(self.medewerker_user.functies), 1)
        self.assertEqual(self.medewerker_user.functies[0].id, self.functie_lesgever.id)

    def test_gebruiker_toggle_rules(self):
        """Test het in-/uitschakelen van gebruikers via toggle route."""
        self.login_admin()

        # 1. Medewerker deactiveren
        res_toggle1 = self.client.get(f'/beheer/gebruikers/{self.medewerker_user.id}/toggle', follow_redirects=True)
        self.assertEqual(res_toggle1.status_code, 200)
        uo = UserOrganisatie.query.filter_by(user_id=self.medewerker_user.id, organisatie_id=self.org.id).first()
        self.assertFalse(uo.actief)

        # 2. Medewerker opnieuw activeren
        res_toggle2 = self.client.get(f'/beheer/gebruikers/{self.medewerker_user.id}/toggle', follow_redirects=True)
        self.assertEqual(res_toggle2.status_code, 200)
        db.session.refresh(uo)
        self.assertTrue(uo.actief)

        # 3. Eerste beheerder (id 1) deactiveren is geblokkeerd
        res_toggle_self = self.client.get(f'/beheer/gebruikers/{self.admin_user.id}/toggle', follow_redirects=True)
        self.assertEqual(res_toggle_self.status_code, 200)
        self.assertIn("eerste beheerder kan niet worden gedeactiveerd", res_toggle_self.get_data(as_text=True).lower())

    def test_backup_and_restore_workflow(self):
        """Test backup download en herstel via admin routes."""
        self.login_admin()

        # 1. Download backup JSON
        res_backup = self.client.get('/beheer/backup')
        self.assertEqual(res_backup.status_code, 200)
        self.assertIn('application/json', res_backup.content_type)
        backup_json = json.loads(res_backup.data.decode('utf-8'))
        self.assertIn('organisatie', backup_json)
        self.assertIn('users', backup_json)

        # 2. Medewerker heeft geen toegang tot backup
        self.logout()
        self.login_medewerker()
        res_unauth = self.client.get('/beheer/backup', follow_redirects=True)
        self.assertIn("geen toegang", res_unauth.get_data(as_text=True).lower())

        # 3. Restore met ongeldig bestand
        self.logout()
        self.login_admin()
        res_empty_restore = self.client.post('/beheer/restore', data={}, follow_redirects=True)
        self.assertEqual(res_empty_restore.status_code, 200)
        self.assertIn("selecteren", res_empty_restore.get_data(as_text=True).lower())

        # 4. Restore met geldige backup data
        backup_bytes = io.BytesIO(res_backup.data)
        res_restore_ok = self.client.post('/beheer/restore', data={
            'backup_file': (backup_bytes, 'backup_test.json')
        }, follow_redirects=True)
        self.assertEqual(res_restore_ok.status_code, 200)
        self.assertIn("hersteld", res_restore_ok.get_data(as_text=True).lower())

    def test_audit_log_filters_and_clean_permissions(self):
        """Test audit-log overzicht, filtering en platformadmin opschonen."""
        # Maak test audit records
        log1 = AuditLog(
            organisatie_id=self.org.id,
            gebruiker="AdminMark",
            operatie="CREATE",
            tabel="users",
            record_id=1,
            details='{"nieuwe_waarden": {"naam": "AdminMark"}}',
            timestamp=datetime.now(timezone.utc) - timedelta(days=400)
        )
        log2 = AuditLog(
            organisatie_id=self.org.id,
            gebruiker="UserTim",
            operatie="UPDATE",
            tabel="registrations",
            record_id=10,
            details='{"wijzigingen": {"hulpvragen": "vraag"}}',
            timestamp=datetime.now(timezone.utc)
        )
        db.session.add_all([log1, log2])
        db.session.commit()
        log1_id = log1.id
        log2_id = log2.id

        self.login_admin()

        # 1. Bekijk audit log pagina met filters
        res_audit = self.client.get('/beheer/audit-log?gebruiker=Tim&tabel=registrations&operatie=UPDATE')
        self.assertEqual(res_audit.status_code, 200)
        self.assertIn("UserTim", res_audit.get_data(as_text=True))
        self.assertIn("registrations", res_audit.get_data(as_text=True))

        # 2. Gewone beheerder probeert logs op te schonen (enkel platformbeheerder mag dit)
        res_clean_denied = self.client.post('/beheer/audit-log/opschonen', follow_redirects=True)
        self.assertIn("geen toegang", res_clean_denied.get_data(as_text=True).lower())
        self.assertIsNotNone(db.session.get(AuditLog, log1_id))

        # 3. Platformbeheerder logt in en schoont op (>365 dagen oud)
        self.admin_user.rol = 'platformbeheerder'
        db.session.commit()

        res_clean_ok = self.client.post('/beheer/audit-log/opschonen', follow_redirects=True)
        self.assertEqual(res_clean_ok.status_code, 200)
        self.assertIn("succesvol", res_clean_ok.get_data(as_text=True).lower())
        # Oude log1 (>400 dagen) moet verwijderd zijn, recente log2 moet bewaard blijven
        self.assertIsNone(db.session.get(AuditLog, log1_id))
        self.assertIsNotNone(db.session.get(AuditLog, log2_id))

    def test_digidokter_and_locatie_reordering_and_duplicates(self):
        """Test duplicatencontrole en volgorde wijzigen van digidokters en locaties."""
        self.login_admin()

        # 1. Duplicaat digidokter toevoegen op basis van al gekoppelde digidokter
        # self.digidokter is al gekoppeld met naam 'Test Digidokter'
        res_dup_dd = self.client.post('/beheer/digidokters/nieuw', data={
            'naam': 'Test Digidokter',
            'email': self.admin_user.email,
            'actief': 'on'
        }, follow_redirects=True)
        self.assertEqual(res_dup_dd.status_code, 200)

        # Maak nieuwe gebruiker voor tweede digidokter
        u_extra = User(naam="Extra DD", email="extra_dd@test.com", wachtwoord_hash="hash", rol="medewerker", actief=True)
        db.session.add(u_extra)
        db.session.commit()
        db.session.add(UserOrganisatie(user_id=u_extra.id, organisatie_id=self.org.id, rol="medewerker", actief=True))
        db.session.commit()

        # 2. Nieuwe digidokter toevoegen via geldig e-mailadres
        res_add_dd = self.client.post('/beheer/digidokters/nieuw', data={
            'naam': 'Tweede Digidokter',
            'email': 'extra_dd@test.com',
            'actief': 'on'
        }, follow_redirects=True)
        self.assertEqual(res_add_dd.status_code, 200)
        dd2 = Digidokter.query.filter_by(naam='Tweede Digidokter', organisatie_id=self.org.id).first()
        self.assertIsNotNone(dd2)

        # 3. Volgorde digidokter wisselen
        v_orig_dd1 = self.digidokter.volgorde
        v_orig_dd2 = dd2.volgorde
        res_order = self.client.get(f'/beheer/digidokters/{dd2.id}/volgorde/omhoog', follow_redirects=True)
        self.assertEqual(res_order.status_code, 200)
        db.session.refresh(self.digidokter)
        db.session.refresh(dd2)
        self.assertEqual(dd2.volgorde, v_orig_dd1)
        self.assertEqual(self.digidokter.volgorde, v_orig_dd2)

        # 4. Locatie nieuw met consultatie-vlag
        res_loc = self.client.post('/beheer/locaties/nieuw', data={
            'naam': 'De Nieuwe Bib',
            'gebruikt_voor_consultaties': 'on'
        }, follow_redirects=True)
        self.assertEqual(res_loc.status_code, 200)
        loc = Location.query.filter_by(naam='De Nieuwe Bib', organisatie_id=self.org.id).first()
        self.assertIsNotNone(loc)
        self.assertTrue(loc.gebruikt_voor_consultaties)

        # 5. Locatie wijzigen: consultatie-vlag uitzetten
        res_loc_edit = self.client.post(f'/beheer/locaties/{loc.id}/wijzig', data={
            'naam': 'De Nieuwe Bib (Gewijzigd)',
            'actief': 'on'
            # gebruikt_voor_consultaties niet verzonden -> False
        }, follow_redirects=True)
        self.assertEqual(res_loc_edit.status_code, 200)
        db.session.refresh(loc)
        self.assertFalse(loc.gebruikt_voor_consultaties)
        self.assertEqual(loc.naam, 'De Nieuwe Bib (Gewijzigd)')

    def test_gebruikers_list_lezer_badge_display(self):
        """Test dat gebruikers met de rol 'lezer' correct getoond worden met een Lezer-badge en in het bewerkformulier."""
        self.login_admin()

        # Maak een gebruiker met rol 'lezer' aan
        u_lezer = User(
            naam="Agnes De TestLezer",
            email="agnes.lezer@test.com",
            wachtwoord_hash=generate_password_hash("password123"),
            rol="lezer",
            actief=True
        )
        db.session.add(u_lezer)
        db.session.commit()
        db.session.add(UserOrganisatie(user_id=u_lezer.id, organisatie_id=self.org.id, rol="lezer", actief=True))
        db.session.commit()

        # 1. Controleer de gebruikerslijst
        res = self.client.get('/beheer/gebruikers')
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)

        self.assertIn("Agnes De TestLezer", html)
        self.assertIn("Lezers", html)
        self.assertIn("Beheerders", html)
        self.assertIn("Medewerkers", html)

        # 2. Controleer het wijzigingsformulier
        res_edit = self.client.get(f'/beheer/gebruikers/{u_lezer.id}/wijzig')
        self.assertEqual(res_edit.status_code, 200)
        edit_html = res_edit.get_data(as_text=True)
        self.assertIn('Agnes De TestLezer', edit_html)
        self.assertIn('Toegewezen Groep(en)', edit_html)

    def test_gebruiker_nieuw_and_wijzig_derive_role_strictly_from_groups(self):
        """Test dat het aanmaken en wijzigen van gebruikers zonder rol-parameter de rol correct afleidt uit de geselecteerde groepen."""
        from models.group import Group
        from utils.permissions import seed_standaard_groepen_voor_organisatie
        groepen = seed_standaard_groepen_voor_organisatie(self.org.id)

        self.login_admin()

        # 1. Nieuwe gebruiker aanmaken met uitsluitend groep_ids (zonder 'rol' veld)
        res_post = self.client.post('/beheer/gebruikers/nieuw', data={
            'naam': 'GroepOnlyUser',
            'email': 'groeponly@test.com',
            'wachtwoord': 'Password123!',
            'groep_ids': [str(groepen['lezers'].id)]
        }, follow_redirects=True)
        self.assertEqual(res_post.status_code, 200)

        created_user = User.query.filter_by(email='groeponly@test.com').first()
        self.assertIsNotNone(created_user)
        uo = UserOrganisatie.query.filter_by(user_id=created_user.id, organisatie_id=self.org.id).first()
        self.assertEqual(uo.rol, 'lezer')
        self.assertEqual(created_user.get_groepen_voor_organisatie(self.org.id)[0].naam, 'Lezers')

        # 2. Gebruiker bijwerken naar Beheerders groep zonder 'rol' veld
        res_edit_post = self.client.post(f'/beheer/gebruikers/{created_user.id}/wijzig', data={
            'naam': 'GroepOnlyUser',
            'email': 'groeponly@test.com',
            'groep_ids': [str(groepen['beheerders'].id)]
        }, follow_redirects=True)
        self.assertEqual(res_edit_post.status_code, 200)

        db.session.refresh(uo)
        self.assertEqual(uo.rol, 'beheerder')
        self.assertEqual(created_user.get_groepen_voor_organisatie(self.org.id)[0].naam, 'Beheerders')

    def test_platformbeheerder_toggle_on_and_off(self):
        """Test dat een platformbeheerder de globale superuser status van een gebruiker aan en uit kan zetten via het wijzig-formulier."""
        # Maak platform admin aan
        pb_user = User(
            naam="SuperAdmin",
            email="superadmin@test.com",
            wachtwoord_hash=generate_password_hash("password123"),
            rol="platformbeheerder",
            actief=True,
            moet_wachtwoord_wijzigen=False
        )
        db.session.add(pb_user)
        db.session.commit()
        db.session.add(UserOrganisatie(user_id=pb_user.id, organisatie_id=self.org.id, rol="beheerder", actief=True))
        db.session.commit()

        # Login als platformbeheerder
        self.login("superadmin@test.com", "password123")
        self.select_organisatie(self.org.id)

        # Doelgebruiker is initieel platformbeheerder
        target_user = User(
            naam="TargetUser",
            email="target@test.com",
            wachtwoord_hash=generate_password_hash("password123"),
            rol="platformbeheerder",
            actief=True,
            moet_wachtwoord_wijzigen=False
        )
        db.session.add(target_user)
        db.session.commit()
        db.session.add(UserOrganisatie(user_id=target_user.id, organisatie_id=self.org.id, rol="beheerder", actief=True))
        db.session.commit()

        # 1. Schakel platformbeheerder UIT (checkbox niet meegeleverd in POST body)
        res = self.client.post(f'/beheer/gebruikers/{target_user.id}/wijzig', data={
            'naam': 'TargetUser',
            'email': 'target@test.com',
            # 'is_platformbeheerder' wordt weggelaten (ongecheckte checkbox)
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        db.session.refresh(target_user)
        self.assertNotEqual(target_user.rol, 'platformbeheerder')

        # 2. Schakel platformbeheerder opnieuw IN ('is_platformbeheerder': 'on')
        res2 = self.client.post(f'/beheer/gebruikers/{target_user.id}/wijzig', data={
            'naam': 'TargetUser',
            'email': 'target@test.com',
            'is_platformbeheerder': 'on'
        }, follow_redirects=True)
        self.assertEqual(res2.status_code, 200)

        db.session.refresh(target_user)
        self.assertEqual(target_user.rol, 'platformbeheerder')

    def test_laatste_platformbeheerder_kan_niet_worden_uitgeschakeld_of_verwijderd(self):
        """Test dat de allerlaatste actieve platformbeheerder beschermd is tegen uitschakelen of verwijderen."""
        # Enige platformbeheerder in het systeem
        solo_pb = User(
            naam="SoloSuperAdmin",
            email="solosuper@test.com",
            wachtwoord_hash=generate_password_hash("password123"),
            rol="platformbeheerder",
            actief=True,
            moet_wachtwoord_wijzigen=False
        )
        db.session.add(solo_pb)
        db.session.commit()
        db.session.add(UserOrganisatie(user_id=solo_pb.id, organisatie_id=self.org.id, rol="beheerder", actief=True))
        db.session.commit()

        self.login("solosuper@test.com", "password123")
        self.select_organisatie(self.org.id)

        # GET op wijzig-pagina toont waarschuwing en disabled switch
        res_get = self.client.get(f'/beheer/gebruikers/{solo_pb.id}/wijzig')
        self.assertEqual(res_get.status_code, 200)
        self.assertIn('Dit is de enige actieve platformbeheerder', res_get.get_data(as_text=True))

        # POST poging om platformbeheerder uit te schakelen
        res_post = self.client.post(f'/beheer/gebruikers/{solo_pb.id}/wijzig', data={
            'naam': 'SoloSuperAdmin',
            'email': 'solosuper@test.com',
            # 'is_platformbeheerder' weggelaten
        }, follow_redirects=True)
        self.assertEqual(res_post.status_code, 200)
        self.assertIn('De laatste actieve platformbeheerder kan niet worden ontdaan van de platformbeheerdersrol', res_post.get_data(as_text=True))

        # Verifieer dat solo_pb nog steeds platformbeheerder is
        db.session.refresh(solo_pb)
        self.assertEqual(solo_pb.rol, 'platformbeheerder')

        # Poging om solo_pb te verwijderen wordt eveneens geweigerd
        res_del = self.client.post(f'/beheer/gebruikers/{solo_pb.id}/verwijderen', follow_redirects=True)
        self.assertEqual(res_del.status_code, 200)
        self.assertIn('eigen account niet verwijderen', res_del.get_data(as_text=True))



