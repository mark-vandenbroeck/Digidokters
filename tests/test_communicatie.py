"""
Unit tests voor Berichten & Communicatie functionaliteit:
- Platformbeheerders: emails sturen naar alle beheerders over alle organisaties.
- Organisatiebeheerders: emails sturen naar gebruikers van de eigen actieve organisatie.
- Bewaren van communicatieberichten & metadata (CommunicatieLog).
- Historiek: platformbeheerder ziet alles, organisatiebeheerder ziet enkel eigen organisatie.
- Autorisatie & permissies (FEATURE_COMMUNICATIE).
"""
import pytest
from unittest.mock import patch
from werkzeug.security import generate_password_hash
from tests.base import BaseTestCase
from extensions import db
from models.user import User
from models.organisatie import Organisatie, UserOrganisatie
from models.group import Group, GroupPermission, UserGroup
from models.communicatie import CommunicatieLog
from models.constants import (
    ROLE_PLATFORMBEHEERDER, ROLE_BEHEERDER, ROLE_MEDEWERKER, ROLE_LEZER,
    ACCESS_NONE, ACCESS_READ, ACCESS_WRITE,
    FEATURE_COMMUNICATIE, DEFAULT_GROUP_BEHEERDERS, DEFAULT_GROUP_MEDEWERKERS, DEFAULT_GROUP_LEZERS
)
from utils.permissions import seed_standaard_groepen_voor_organisatie, get_default_matrix_voor_groep


class TestCommunicatieRoutes(BaseTestCase):

    def setUp(self):
        super().setUp()

        # Maak 2e organisatie aan voor multi-tenant tests
        self.org2 = Organisatie(
            naam="Digidokters Tweede Gemeente",
            slug="tweede-gemeente",
            actief=True
        )
        self.org_sjabloon = Organisatie(
            naam="Sjabloon Organisatie",
            slug="sjabloon",
            actief=True
        )
        db.session.add_all([self.org2, self.org_sjabloon])
        db.session.commit()

        # Maak platformbeheerder aan
        self.platform_user = User(
            naam="PlatformAdmin",
            email="platformadmin@test.com",
            wachtwoord_hash=generate_password_hash("password123"),
            rol=ROLE_PLATFORMBEHEERDER,
            actief=True
        )

        # Maak beheerder voor org2 aan
        self.admin_org2 = User(
            naam="AdminOrg2",
            email="admin.org2@test.com",
            wachtwoord_hash=generate_password_hash("password123"),
            rol=ROLE_BEHEERDER,
            actief=True
        )

        # Maak medewerker voor org2 aan
        self.medewerker_org2 = User(
            naam="MedewerkerOrg2",
            email="medewerker.org2@test.com",
            wachtwoord_hash=generate_password_hash("password123"),
            rol=ROLE_MEDEWERKER,
            actief=True
        )

        # Inactieve beheerder (mag geen mails ontvangen)
        self.inactive_admin = User(
            naam="InactieveAdmin",
            email="inactief@test.com",
            wachtwoord_hash=generate_password_hash("password123"),
            rol=ROLE_BEHEERDER,
            actief=False
        )

        db.session.add_all([
            self.platform_user,
            self.admin_org2,
            self.medewerker_org2,
            self.inactive_admin
        ])
        db.session.commit()

        # Koppel gebruikers aan organisaties
        uo_admin2 = UserOrganisatie(user_id=self.admin_org2.id, organisatie_id=self.org2.id, rol=ROLE_BEHEERDER, actief=True)
        uo_med2 = UserOrganisatie(user_id=self.medewerker_org2.id, organisatie_id=self.org2.id, rol=ROLE_MEDEWERKER, actief=True)
        uo_inactive = UserOrganisatie(user_id=self.inactive_admin.id, organisatie_id=self.org.id, rol=ROLE_BEHEERDER, actief=False)

        db.session.add_all([uo_admin2, uo_med2, uo_inactive])
        db.session.commit()

        # Seed standaardgroepen voor beide organisaties
        seed_standaard_groepen_voor_organisatie(self.org.id)
        seed_standaard_groepen_voor_organisatie(self.org2.id)

    # ─── Permissie & Default Matrix Tests ────────────────────────────────────

    def test_default_permissions_for_communicatie(self):
        """Test dat FEATURE_COMMUNICATIE standaard alleen schrijfbaar is voor beheerders."""
        matrix_admin = get_default_matrix_voor_groep(DEFAULT_GROUP_BEHEERDERS)
        matrix_medewerker = get_default_matrix_voor_groep(DEFAULT_GROUP_MEDEWERKERS)
        matrix_lezer = get_default_matrix_voor_groep(DEFAULT_GROUP_LEZERS)

        assert matrix_admin.get(FEATURE_COMMUNICATIE) == ACCESS_WRITE
        assert matrix_medewerker.get(FEATURE_COMMUNICATIE) == ACCESS_NONE
        assert matrix_lezer.get(FEATURE_COMMUNICATIE) == ACCESS_NONE

    # ─── Platform Communicatie Tests ─────────────────────────────────────────

    def test_platform_communicatie_get_view(self):
        """Platformbeheerder kan het communicatieformulier inzien en ziet alle actieve beheerders."""
        self.login("platformadmin@test.com", "password123")
        response = self.client.get('/platform/communicatie')
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert 'Platform Communicatie' in html
        assert 'admin@test.com' in html
        assert 'admin.org2@test.com' in html
        # Inactieve beheerder of gewone medewerkers horen er niet tussen te staan
        assert 'inactief@test.com' not in html
        assert 'tim@test.com' not in html

    @patch('utils.mail.verstuur_email')
    def test_platform_communicatie_send_and_persist_log(self, mock_mail):
        """Platformbeheerder verstuurt een aankondiging en de log wordt correct opgeslagen."""
        mock_mail.return_value = (True, "OK")
        self.login("platformadmin@test.com", "password123")

        response = self.client.post('/platform/communicatie', data={
            'onderwerp': 'Belangrijke platform-upgrade',
            'bericht': 'Beste beheerders, vanavond om 22u voeren we onderhoud uit.'
        }, follow_redirects=True)

        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert 'Aankondiging succesvol verzonden' in html

        # Controleer mock_mail aanroep
        assert mock_mail.called
        args, kwargs = mock_mail.call_args
        ontvangers, onderwerp, bericht = args[0], args[1], args[2]

        assert onderwerp == 'Belangrijke platform-upgrade'
        assert 'vanavond om 22u' in bericht
        assert 'admin@test.com' in ontvangers
        assert 'admin.org2@test.com' in ontvangers

        # Controleer dat de log in de database is opgeslagen
        log = CommunicatieLog.query.filter_by(onderwerp='Belangrijke platform-upgrade').first()
        assert log is not None
        assert log.type == 'platform'
        assert log.afzender_email == 'platformadmin@test.com'
        assert log.afzender_naam == 'PlatformAdmin'
        assert log.organisatie_id is None
        assert log.aantal_ontvangers == 2
        assert len(log.ontvangers_lijst) == 2

    def test_platform_communicatie_validation_empty_fields(self):
        """Test validatie bij lege velden in platform communicatie."""
        self.login("platformadmin@test.com", "password123")

        # Leeg onderwerp
        res1 = self.client.post('/platform/communicatie', data={
            'onderwerp': '',
            'bericht': 'Een bericht zonder onderwerp.'
        }, follow_redirects=True)
        assert 'Onderwerp is verplicht' in res1.get_data(as_text=True)

        # Leeg bericht
        res2 = self.client.post('/platform/communicatie', data={
            'onderwerp': 'Onderwerp zonder tekst',
            'bericht': ''
        }, follow_redirects=True)
        assert 'Berichttekst is verplicht' in res2.get_data(as_text=True)

    def test_platform_communicatie_access_denied_for_regular_users(self):
        """Gewone beheerders of medewerkers mogen niet bij /platform/communicatie."""
        self.login("admin@test.com", "password123")
        res1 = self.client.get('/platform/communicatie')
        assert res1.status_code in (302, 403)

        self.login("tim@test.com", "password123")
        res2 = self.client.get('/platform/communicatie')
        assert res2.status_code in (302, 403)

    # ─── Organisatie Communicatie Tests ──────────────────────────────────────

    def test_organisatie_communicatie_get_view(self):
        """Organisatiebeheerder ziet het communicatiescherm met ontvangers en melding over gebruikers zonder e-mail."""
        # Voeg een actieve gebruiker zonder e-mailadres toe aan self.org
        user_no_email = User(
            naam="ZonderEmailUser",
            email="",
            wachtwoord_hash=generate_password_hash("password123"),
            rol=ROLE_MEDEWERKER,
            actief=True
        )
        db.session.add(user_no_email)
        db.session.commit()
        uo_no_email = UserOrganisatie(user_id=user_no_email.id, organisatie_id=self.org.id, rol=ROLE_MEDEWERKER, actief=True)
        db.session.add(uo_no_email)
        db.session.commit()

        self.login("admin@test.com", "password123")
        self.select_organisatie(self.org.id)

        response = self.client.get('/beheer/communicatie')
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert 'Berichten & Communicatie' in html
        assert 'admin@test.com' in html
        assert 'tim@test.com' in html
        assert 'ZonderEmailUser' in html
        assert 'zonder e-mailadres' in html
        assert 'admin.org2@test.com' not in html
        assert 'medewerker.org2@test.com' not in html

    @patch('utils.mail.verstuur_email')
    def test_organisatie_communicatie_send_and_persist_log(self, mock_mail):
        """Organisatiebeheerder stuurt een bericht en de log wordt gekoppeld aan de eigen organisatie."""
        mock_mail.return_value = (True, "OK")
        self.login("admin@test.com", "password123")
        self.select_organisatie(self.org.id)

        response = self.client.post('/beheer/communicatie', data={
            'doelgroep': 'alle',
            'onderwerp': 'Herinnering digidokters overleg',
            'bericht': 'Beste team, volgende week dinsdag is er een kort overleg.'
        }, follow_redirects=True)

        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert 'E-mail succesvol verzonden' in html

        assert mock_mail.called
        args, kwargs = mock_mail.call_args
        ontvangers, onderwerp, bericht = args[0], args[1], args[2]

        assert onderwerp == 'Herinnering digidokters overleg'
        assert 'admin@test.com' in ontvangers
        assert 'tim@test.com' in ontvangers
        assert 'admin.org2@test.com' not in ontvangers

        # Check log entry in DB
        log = CommunicatieLog.query.filter_by(onderwerp='Herinnering digidokters overleg').first()
        assert log is not None
        assert log.type == 'organisatie'
        assert log.organisatie_id == self.org.id
        assert log.afzender_email == 'admin@test.com'
        assert log.afzender_id == self.admin_user.id
        assert log.doelgroep == 'alle'
        assert log.aantal_ontvangers == 2

    @patch('utils.mail.verstuur_email')
    def test_organisatie_communicatie_filter_doelgroep(self, mock_mail):
        """Test filtering op doelgroep (enkel medewerkers of enkel beheerders)."""
        mock_mail.return_value = (True, "OK")
        self.login("admin@test.com", "password123")
        self.select_organisatie(self.org.id)

        # 1. Enkel medewerkers
        self.client.post('/beheer/communicatie', data={
            'doelgroep': 'medewerkers',
            'onderwerp': 'Info voor vrijwilligers',
            'bericht': 'Bericht speciaal voor vrijwilligers.'
        }, follow_redirects=True)

        args1, _ = mock_mail.call_args
        ontvangers1 = args1[0]
        assert 'tim@test.com' in ontvangers1
        assert 'admin@test.com' not in ontvangers1

        mock_mail.reset_mock()

        # 2. Enkel beheerders
        self.client.post('/beheer/communicatie', data={
            'doelgroep': 'beheerders',
            'onderwerp': 'Info voor beheerders',
            'bericht': 'Bericht speciaal voor lokale beheerders.'
        }, follow_redirects=True)

        args2, _ = mock_mail.call_args
        ontvangers2 = args2[0]
        assert 'admin@test.com' in ontvangers2
        assert 'tim@test.com' not in ontvangers2

    def test_organisatie_communicatie_access_denied_for_medewerker_without_permission(self):
        """Medewerkers zonder FEATURE_COMMUNICATIE permissie worden geweigerd."""
        self.login("tim@test.com", "password123")
        self.select_organisatie(self.org.id)

        response = self.client.get('/beheer/communicatie')
        assert response.status_code in (302, 403)

    def test_organisatie_communicatie_allowed_with_explicit_permission(self):
        """Medewerker in een custom groep met schrijfpermissie op communicatie heeft wél toegang."""
        custom_grp = Group(
            organisatie_id=self.org.id,
            naam="Communicatie Verantwoordelijken",
            actief=True
        )
        custom_grp.set_permission(FEATURE_COMMUNICATIE, ACCESS_WRITE)
        db.session.add(custom_grp)
        db.session.commit()

        db.session.add(UserGroup(user_id=self.medewerker_user.id, groep_id=custom_grp.id))
        db.session.commit()

        self.login("tim@test.com", "password123")
        self.select_organisatie(self.org.id)

        response = self.client.get('/beheer/communicatie')
        assert response.status_code == 200
        assert 'Berichten & Communicatie' in response.get_data(as_text=True)

    # ─── Historiek & Multi-tenant Afscherming Tests ─────────────────────────

    def test_communicatie_historiek_isolation(self):
        """
        Test dat een beheerder enkel de historiek van de eigen organisatie ziet,
        terwijl een platformbeheerder de volledige historiek ziet.
        """
        import json
        # Maak 3 communicatielogs aan:
        # 1. Platformbreed
        log_platform = CommunicatieLog(
            organisatie_id=None,
            afzender_id=self.platform_user.id,
            afzender_naam="PlatformAdmin",
            afzender_email="platformadmin@test.com",
            type='platform',
            doelgroep='alle_beheerders',
            onderwerp='Platform Update 2.0',
            inhoud='Inhoud van platform update.',
            ontvangers_json=json.dumps([{'email': 'admin@test.com'}, {'email': 'admin.org2@test.com'}]),
            aantal_ontvangers=2
        )
        # 2. Organisatie 1
        log_org1 = CommunicatieLog(
            organisatie_id=self.org.id,
            afzender_id=self.admin_user.id,
            afzender_naam="AdminMark",
            afzender_email="admin@test.com",
            type='organisatie',
            doelgroep='alle',
            onderwerp='Org1 Jaarplanning',
            inhoud='Planning voor Org1.',
            ontvangers_json=json.dumps([{'email': 'tim@test.com'}]),
            aantal_ontvangers=1
        )
        # 3. Organisatie 2
        log_org2 = CommunicatieLog(
            organisatie_id=self.org2.id,
            afzender_id=self.admin_org2.id,
            afzender_naam="AdminOrg2",
            afzender_email="admin.org2@test.com",
            type='organisatie',
            doelgroep='alle',
            onderwerp='Org2 Vrijwilligersdag',
            inhoud='Info voor Org2.',
            ontvangers_json=json.dumps([{'email': 'medewerker.org2@test.com'}]),
            aantal_ontvangers=1
        )
        db.session.add_all([log_platform, log_org1, log_org2])
        db.session.commit()

        # 1. Beheerder van Org 1 bekijkt overzicht
        self.login("admin@test.com", "password123")
        self.select_organisatie(self.org.id)
        res_org1 = self.client.get('/beheer/communicatie')
        html_org1 = res_org1.get_data(as_text=True)

        assert 'Org1 Jaarplanning' in html_org1
        # Mag NOOIT logs van Org2 of globale platformlogs zien in lokaal beheer
        assert 'Org2 Vrijwilligersdag' not in html_org1
        assert 'Platform Update 2.0' not in html_org1

        # Beheerder van Org 1 probeert detail van Org2 log te openen -> geweigerd
        res_detail_forbidden = self.client.get(f'/beheer/communicatie/log/{log_org2.id}')
        assert res_detail_forbidden.status_code == 302  # redirect met waarschuwing

        # Beheerder van Org 1 opent eigen log detail -> 200 OK
        res_detail_ok = self.client.get(f'/beheer/communicatie/log/{log_org1.id}')
        assert res_detail_ok.status_code == 200
        assert 'Planning voor Org1' in res_detail_ok.get_data(as_text=True)

        # 2. Platformbeheerder bekijkt platform historiek -> ziet ALLE logs
        self.logout()
        self.login("platformadmin@test.com", "password123")
        res_pb = self.client.get('/platform/communicatie')
        html_pb = res_pb.get_data(as_text=True)

        assert 'Platform Update 2.0' in html_pb
        assert 'Org1 Jaarplanning' in html_pb
        assert 'Org2 Vrijwilligersdag' in html_pb

        # Platformbeheerder opent log detail
        res_pb_detail = self.client.get(f'/platform/communicatie/log/{log_org2.id}')
        assert res_pb_detail.status_code == 200
        assert 'Info voor Org2' in res_pb_detail.get_data(as_text=True)

    # ─── Proefmail & Veilige Testmodus Tests ─────────────────────────────────

    @patch('utils.mail.verstuur_email')
    def test_platform_communicatie_testmail_naar_mijzelf(self, mock_send):
        """
        Test dat de knop 'Testmail naar mijzelf' enkel een proefmail naar de ingelogde platformbeheerder stuurt
        en geen CommunicatieLog record aanmaakt in de bulk-historiek.
        """
        self.login("platformadmin@test.com", "password123")
        mock_send.return_value = (True, "OK")

        init_count = CommunicatieLog.query.count()
        response = self.client.post('/platform/communicatie', data={
            'actie': 'test',
            'onderwerp': 'Test Aankondiging Onderwerp',
            'bericht': 'Test Aankondiging Inhoud'
        }, follow_redirects=True)

        assert response.status_code == 200
        assert 'Proefmail succesvol verzonden naar uw eigen e-mailadres' in response.get_data(as_text=True)

        # Controleer dat verstuur_email ALLEEN naar platformadmin@test.com is aangeroepen
        mock_send.assert_called_once()
        args, kwargs = mock_send.call_args
        assert args[0] == ['platformadmin@test.com']
        assert '[PROEFMAIL]' in args[1]
        assert 'Test Aankondiging Inhoud' in args[2]

        # Geen broadcast record in database opgeslagen
        assert CommunicatieLog.query.count() == init_count

    @patch('utils.mail.verstuur_email')
    def test_admin_communicatie_testmail_naar_mijzelf(self, mock_send):
        """
        Test dat de knop 'Testmail naar mijzelf' in lokaal beheer enkel naar de ingelogde admin stuurt
        en geen bulk CommunicatieLog aanmaakt.
        """
        self.login("admin@test.com", "password123")
        self.select_organisatie(self.org.id)
        mock_send.return_value = (True, "OK")

        init_count = CommunicatieLog.query.count()
        response = self.client.post('/beheer/communicatie', data={
            'actie': 'test',
            'doelgroep': 'alle',
            'onderwerp': 'Test Lokaal Bericht',
            'bericht': 'Test Lokaal Bericht Inhoud'
        }, follow_redirects=True)

        assert response.status_code == 200
        assert 'Proefmail succesvol verzonden naar uw eigen e-mailadres' in response.get_data(as_text=True)

        # Controleer dat verstuur_email ALLEEN naar admin@test.com is aangeroepen
        mock_send.assert_called_once()
        args, kwargs = mock_send.call_args
        assert args[0] == ['admin@test.com']
        assert '[PROEFMAIL]' in args[1]
        assert 'Test Lokaal Bericht Inhoud' in args[2]

        # Geen broadcast record in database opgeslagen
        assert CommunicatieLog.query.count() == init_count

    def test_mail_override_recipient_safety_net(self):
        """
        Test dat wanneer MAIL_OVERRIDE_RECIPIENT is ingesteld in de environment,
        verstuur_email ALTIJD alle ontvangers omleidt naar dat ene testadres.
        """
        import os
        from utils.mail import verstuur_email

        with patch.dict(os.environ, {
            'MAIL_OVERRIDE_RECIPIENT': 'mark.ontvanger@test.be',
            'BREVO_API_KEY': 'test-fake-key'
        }):
            with patch('urllib.request.urlopen') as mock_urlopen:
                # Mock Brevo API respons
                import io
                mock_resp = io.BytesIO(b'{"messageId": "test-123"}')
                mock_urlopen.return_value.__enter__.return_value = mock_resp

                # Verstuur mail naar 3 verschillende echte adressen
                echte_ontvangers = ['beheerder1@antwerpen.be', 'beheerder2@gent.be', 'beheerder3@leuven.be']
                succes, msg = verstuur_email(echte_ontvangers, "Belangrijk bericht", "Inhoud")

                assert succes is True

                # Controleer payload verzonden naar Brevo
                req = mock_urlopen.call_args[0][0]
                import json
                payload = json.loads(req.data.decode('utf-8'))

                # Ontvangers moeten ALLEEN het override adres zijn
                assert payload['to'] == [{'email': 'mark.ontvanger@test.be'}]
                # Onderwerp en body moeten de oorspronkelijke bestemmelingen tonen
                assert 'OVERRIDE: mark.ontvanger@test.be' in payload['subject']
                assert 'beheerder1@antwerpen.be' in payload['subject']
                assert 'beheerder1@antwerpen.be' in payload['textContent']

