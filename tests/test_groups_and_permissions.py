"""Unit tests voor Groepen, Permissies en RBAC authorisatieschema."""
import pytest
from werkzeug.security import generate_password_hash
from tests.base import BaseTestCase
from extensions import db
from models.user import User
from models.organisatie import Organisatie, UserOrganisatie
from models.group import Group, GroupPermission, UserGroup
from models.constants import (
    ROLE_PLATFORMBEHEERDER, ROLE_BEHEERDER, ROLE_MEDEWERKER, ROLE_LEZER,
    ACCESS_NONE, ACCESS_READ, ACCESS_WRITE,
    DEFAULT_GROUP_LEZERS, DEFAULT_GROUP_MEDEWERKERS,
    DEFAULT_GROUP_BEHEERDERS, DEFAULT_GROUP_PLATFORMBEHEERDERS,
    FEATURE_REGISTRATIES, FEATURE_AGENDA, FEATURE_STATISTIEKEN,
    FEATURE_DOCUMENTEN, FEATURE_EVALUATIES, FEATURE_GEBRUIKERS,
    FEATURE_STAMGEGEVENS, FEATURE_IMPORT_EXPORT, FEATURE_FEEDBACK
)
from utils.permissions import (
    has_permission, can_read, can_write,
    get_user_permissions_voor_organisatie,
    seed_standaard_groepen_voor_organisatie
)
from utils.tenant import seed_organisatie_defaults


class TestGroupsAndPermissions(BaseTestCase):

    def setUp(self):
        super().setUp()
        # Maak extra lezer en platformbeheerder aan voor tests
        self.lezer_user = User(
            naam="LezerLuc",
            email="luc@test.com",
            wachtwoord_hash=generate_password_hash("password123"),
            rol=ROLE_LEZER,
            actief=True
        )
        self.platformbeheerder_user = User(
            naam="PlatformBaas",
            email="platform@test.com",
            wachtwoord_hash=generate_password_hash("password123"),
            rol=ROLE_PLATFORMBEHEERDER,
            actief=True
        )
        db.session.add_all([self.lezer_user, self.platformbeheerder_user])
        db.session.commit()

        # Link lezer aan self.org
        uo_lezer = UserOrganisatie(
            user_id=self.lezer_user.id,
            organisatie_id=self.org.id,
            rol=ROLE_LEZER,
            actief=True
        )
        db.session.add(uo_lezer)
        db.session.commit()

    def test_seed_standaard_groepen(self):
        """Test dat seed_standaard_groepen_voor_organisatie de 4 standaardgroepen correct aanmaakt."""
        groepen_map = seed_standaard_groepen_voor_organisatie(self.org.id)
        assert len(groepen_map) == 4

        assert DEFAULT_GROUP_LEZERS in groepen_map
        assert DEFAULT_GROUP_MEDEWERKERS in groepen_map
        assert DEFAULT_GROUP_BEHEERDERS in groepen_map
        assert DEFAULT_GROUP_PLATFORMBEHEERDERS in groepen_map

        # Check lezers permissions: registraties=lezen, agenda=lezen, statistieken=lezen, stamgegevens=lezen, gebruikers=geen
        lezers = groepen_map[DEFAULT_GROUP_LEZERS]
        assert lezers.naam == 'Lezers'
        assert lezers.get_permission(FEATURE_REGISTRATIES) == ACCESS_READ
        assert lezers.get_permission(FEATURE_GEBRUIKERS) == ACCESS_NONE
        assert lezers.get_permission(FEATURE_STAMGEGEVENS) == ACCESS_READ

        # Check medewerkers: registraties=schrijven, agenda=schrijven, documenten=schrijven, gebruikers=geen
        medewerkers = groepen_map[DEFAULT_GROUP_MEDEWERKERS]
        assert medewerkers.naam == 'Medewerkers'
        assert medewerkers.get_permission(FEATURE_REGISTRATIES) == ACCESS_WRITE
        assert medewerkers.get_permission(FEATURE_GEBRUIKERS) == ACCESS_NONE

        # Check beheerders: alles schrijven
        beheerders = groepen_map[DEFAULT_GROUP_BEHEERDERS]
        assert beheerders.naam == 'Beheerders'
        assert beheerders.get_permission(FEATURE_REGISTRATIES) == ACCESS_WRITE
        assert beheerders.get_permission(FEATURE_GEBRUIKERS) == ACCESS_WRITE
        assert beheerders.get_permission(FEATURE_STAMGEGEVENS) == ACCESS_WRITE

    def test_permission_resolution_single_and_multi_group(self):
        """Test effectieve rechten bij 1 of meerdere groepen."""
        # Maak 2 custom groepen
        g1 = Group(organisatie_id=self.org.id, naam='Groep A')
        g1.set_permission(FEATURE_REGISTRATIES, ACCESS_READ)
        g1.set_permission(FEATURE_DOCUMENTEN, ACCESS_NONE)

        g2 = Group(organisatie_id=self.org.id, naam='Groep B')
        g2.set_permission(FEATURE_REGISTRATIES, ACCESS_WRITE)
        g2.set_permission(FEATURE_DOCUMENTEN, ACCESS_READ)

        db.session.add_all([g1, g2])
        db.session.commit()

        # Koppel medewerker aan alleen Groep A
        ug1 = UserGroup(user_id=self.medewerker_user.id, groep_id=g1.id)
        db.session.add(ug1)
        db.session.commit()

        perms = get_user_permissions_voor_organisatie(self.medewerker_user, self.org.id)
        assert perms[FEATURE_REGISTRATIES] == ACCESS_READ
        assert perms[FEATURE_DOCUMENTEN] == ACCESS_NONE
        assert has_permission(FEATURE_REGISTRATIES, 'read', user=self.medewerker_user, org_id=self.org.id) is True
        assert has_permission(FEATURE_REGISTRATIES, 'write', user=self.medewerker_user, org_id=self.org.id) is False

        # Koppel nu ook aan Groep B: hoogste niveau (write) moet winnen
        ug2 = UserGroup(user_id=self.medewerker_user.id, groep_id=g2.id)
        db.session.add(ug2)
        db.session.commit()

        perms_multi = get_user_permissions_voor_organisatie(self.medewerker_user, self.org.id)
        assert perms_multi[FEATURE_REGISTRATIES] == ACCESS_WRITE
        assert perms_multi[FEATURE_DOCUMENTEN] == ACCESS_READ
        assert has_permission(FEATURE_REGISTRATIES, 'write', user=self.medewerker_user, org_id=self.org.id) is True
        assert has_permission(FEATURE_DOCUMENTEN, 'read', user=self.medewerker_user, org_id=self.org.id) is True
        assert has_permission(FEATURE_DOCUMENTEN, 'write', user=self.medewerker_user, org_id=self.org.id) is False

    def test_platformbeheerder_always_has_full_write(self):
        """Platformbeheerder heeft altijd 'schrijven' op alle functionaliteiten."""
        perms = get_user_permissions_voor_organisatie(self.platformbeheerder_user, self.org.id)
        for feat in [FEATURE_REGISTRATIES, FEATURE_AGENDA, FEATURE_GEBRUIKERS, FEATURE_STAMGEGEVENS]:
            assert perms[feat] == ACCESS_WRITE
            assert has_permission(feat, 'write', user=self.platformbeheerder_user, org_id=self.org.id) is True

    def test_role_fallback_when_no_groups(self):
        """Als een gebruiker nog geen groepen heeft in de org, val terug op legacy rol."""
        # self.lezer_user heeft geen UserGroup records
        perms_lezer = get_user_permissions_voor_organisatie(self.lezer_user, self.org.id)
        assert perms_lezer[FEATURE_REGISTRATIES] == ACCESS_READ
        assert perms_lezer[FEATURE_GEBRUIKERS] == ACCESS_NONE

        # self.admin_user heeft geen UserGroup records
        perms_admin = get_user_permissions_voor_organisatie(self.admin_user, self.org.id)
        assert perms_admin[FEATURE_REGISTRATIES] == ACCESS_WRITE
        assert perms_admin[FEATURE_GEBRUIKERS] == ACCESS_WRITE

    def test_groepen_crud_routes(self):
        """Test de CRUD routes voor groepenbeheer door beheerders."""
        self.login(self.admin_user.email, "password123")

        # 1. Overzicht pagina
        resp = self.client.get('/beheer/groepen')
        assert resp.status_code == 200
        assert 'Groepen &amp; Rechten' in resp.get_data(as_text=True) or 'Groepen & Rechten' in resp.get_data(as_text=True)

        # 2. Nieuwe groep formulier ophalen
        resp = self.client.get('/beheer/groepen/nieuw')
        assert resp.status_code == 200
        assert 'Nieuwe Groep' in resp.get_data(as_text=True)

        # 3. Nieuwe groep opslaan
        data = {
            'naam': 'Vrijwilligers Coach',
            'beschrijving': 'Coaches met specifieke rechten',
            'perm_registraties': 'schrijven',
            'perm_agenda': 'schrijven',
            'perm_statistieken': 'lezen',
            'perm_documenten': 'lezen',
            'perm_evaluaties': 'lezen',
            'perm_feedback': 'schrijven',
            'perm_stamgegevens': 'geen',
            'perm_gebruikers': 'geen',
            'perm_import_export': 'geen'
        }
        resp = self.client.post('/beheer/groepen/nieuw', data=data, follow_redirects=True)
        assert resp.status_code == 200
        assert 'is succesvol aangemaakt' in resp.get_data(as_text=True)

        nieuwe_groep = Group.query.filter_by(organisatie_id=self.org.id, naam='Vrijwilligers Coach').first()
        assert nieuwe_groep is not None
        assert nieuwe_groep.get_permission(FEATURE_REGISTRATIES) == ACCESS_WRITE
        assert nieuwe_groep.get_permission(FEATURE_STATISTIEKEN) == ACCESS_READ
        assert nieuwe_groep.get_permission(FEATURE_GEBRUIKERS) == ACCESS_NONE

        # 4. Groep bewerken
        edit_data = {
            'naam': 'Vrijwilligers Coach Aangepast',
            'beschrijving': 'Nieuwe beschrijving',
            'perm_registraties': 'lezen',
            'perm_agenda': 'schrijven',
            'perm_statistieken': 'geen',
            'perm_documenten': 'geen',
            'perm_evaluaties': 'geen',
            'perm_feedback': 'geen',
            'perm_stamgegevens': 'geen',
            'perm_gebruikers': 'geen',
            'perm_import_export': 'geen'
        }
        resp = self.client.post(f'/beheer/groepen/{nieuwe_groep.id}/bewerken', data=edit_data, follow_redirects=True)
        assert resp.status_code == 200
        assert 'is succesvol bijgewerkt' in resp.get_data(as_text=True)

        db.session.refresh(nieuwe_groep)
        assert nieuwe_groep.naam == 'Vrijwilligers Coach Aangepast'
        assert nieuwe_groep.get_permission(FEATURE_REGISTRATIES) == ACCESS_READ

        # 5. Groep togglen (deactiveren)
        resp = self.client.post(f'/beheer/groepen/{nieuwe_groep.id}/toggle', follow_redirects=True)
        assert resp.status_code == 200
        db.session.refresh(nieuwe_groep)
        assert nieuwe_groep.actief is False

        # 6. Groep verwijderen
        resp = self.client.post(f'/beheer/groepen/{nieuwe_groep.id}/verwijderen', follow_redirects=True)
        assert resp.status_code == 200
        assert 'is verwijderd' in resp.get_data(as_text=True)
        assert Group.query.get(nieuwe_groep.id) is None

    def test_standaard_groep_kan_niet_verwijderd_worden(self):
        """Test dat standaardgroepen (is_standaard=True) beschermd zijn tegen verwijdering."""
        self.login(self.admin_user.email, "password123")
        groepen_map = seed_standaard_groepen_voor_organisatie(self.org.id)

        lezers = groepen_map[DEFAULT_GROUP_LEZERS]
        assert lezers.is_standaard is True

        resp = self.client.post(f'/beheer/groepen/{lezers.id}/verwijderen', follow_redirects=True)
        assert resp.status_code == 200
        assert 'kan niet verwijderd worden' in resp.get_data(as_text=True)
        assert Group.query.get(lezers.id) is not None

    def test_cross_tenant_groep_isolation(self):
        """Beheerder van org A mag geen groepen van org B bekijken of wijzigen."""
        # Maak org 2
        org2 = Organisatie(naam='Tweede Org', slug='tweede-org', actief=True)
        db.session.add(org2)
        db.session.commit()

        g_org2 = Group(organisatie_id=org2.id, naam='Org2 Groep')
        db.session.add(g_org2)
        db.session.commit()

        self.login(self.admin_user.email, "password123")  # ingelogd op self.org (org 1)

        # Probeer groep van org 2 te bewerken
        resp = self.client.get(f'/beheer/groepen/{g_org2.id}/bewerken')
        assert resp.status_code == 404

        resp = self.client.post(f'/beheer/groepen/{g_org2.id}/verwijderen')
        assert resp.status_code == 404

    def test_gebruiker_koppelen_aan_groepen_via_admin(self):
        """Test dat beheerder een gebruiker aan groepen kan koppelen via het gebruikersformulier."""
        self.login(self.admin_user.email, "password123")
        groepen_map = seed_standaard_groepen_voor_organisatie(self.org.id)
        medewerkers_grp = groepen_map[DEFAULT_GROUP_MEDEWERKERS]
        lezers_grp = groepen_map[DEFAULT_GROUP_LEZERS]

        # Wijzig medewerker en koppel aan medewerkers_grp en lezers_grp
        data = {
            'naam': self.medewerker_user.naam,
            'email': self.medewerker_user.email,
            'telefoonnummer': self.medewerker_user.telefoonnummer or '',
            'rol': ROLE_MEDEWERKER,
            'groep_ids': [str(medewerkers_grp.id), str(lezers_grp.id)]
        }
        resp = self.client.post(f'/beheer/gebruikers/{self.medewerker_user.id}/wijzig', data=data, follow_redirects=True)
        assert resp.status_code == 200

        user_groepen = self.medewerker_user.get_groepen_voor_organisatie(self.org.id)
        user_groep_ids = {g.id for g in user_groepen}
        assert medewerkers_grp.id in user_groep_ids
        assert lezers_grp.id in user_groep_ids

    def test_cloning_groups_from_sjabloon(self):
        """Test dat seed_organisatie_defaults groepen kopieert uit sjabloon organisatie."""
        # Maak sjabloon org
        sjabloon = Organisatie(naam='Sjabloon Organisatie', slug='sjabloon', actief=True)
        db.session.add(sjabloon)
        db.session.commit()

        # Maak custom groepen in sjabloon
        s_g1 = Group(organisatie_id=sjabloon.id, naam='Docenten', beschrijving='Voor lesgevers', alleen_eigen_registraties=True)
        s_g1.set_permission(FEATURE_DOCUMENTEN, ACCESS_WRITE)
        db.session.add(s_g1)
        db.session.commit()

        # Maak nieuwe org aan via seed_organisatie_defaults
        new_org = Organisatie(naam='Nieuwe Gemeente', slug='nieuwe-gemeente', actief=True)
        db.session.add(new_org)
        db.session.commit()

        seed_organisatie_defaults(new_org.id)

        new_groepen = Group.query.filter_by(organisatie_id=new_org.id).all()
        assert len(new_groepen) >= 1
        docenten_new = next((g for g in new_groepen if g.naam == 'Docenten'), None)
        assert docenten_new is not None
        assert docenten_new.beschrijving == 'Voor lesgevers'
        assert docenten_new.alleen_eigen_registraties is True
        assert docenten_new.get_permission(FEATURE_DOCUMENTEN) == ACCESS_WRITE

    def test_alleen_eigen_registraties_matrix_resolution(self):
        """Test logica van is_alleen_eigen_registraties bij enkelvoudig en meervoudig groepslidmaatschap."""
        from utils.permissions import is_alleen_eigen_registraties

        # 1. Beheerder en platformbeheerder zijn nooit beperkt
        assert is_alleen_eigen_registraties(self.admin_user, self.org.id) is False
        assert is_alleen_eigen_registraties(self.platformbeheerder_user, self.org.id) is False

        # 2. Maak groep met alleen_eigen_registraties=True
        g_eigen = Group(organisatie_id=self.org.id, naam='Eigen Registraties Alleen', alleen_eigen_registraties=True)
        g_eigen.set_permission(FEATURE_REGISTRATIES, ACCESS_WRITE)
        db.session.add(g_eigen)
        db.session.commit()

        ug = UserGroup(user_id=self.medewerker_user.id, groep_id=g_eigen.id)
        db.session.add(ug)
        db.session.commit()

        # Nu heeft medewerker uitsluitend een groep met alleen_eigen_registraties=True
        assert is_alleen_eigen_registraties(self.medewerker_user, self.org.id) is True

        # 3. Voeg een 2e groep toe die ALLE registraties toestaat (alleen_eigen_registraties=False)
        g_alles = Group(organisatie_id=self.org.id, naam='Alles Zien', alleen_eigen_registraties=False)
        g_alles.set_permission(FEATURE_REGISTRATIES, ACCESS_READ)
        db.session.add(g_alles)
        db.session.commit()

        ug2 = UserGroup(user_id=self.medewerker_user.id, groep_id=g_alles.id)
        db.session.add(ug2)
        db.session.commit()

        # Toegang tot alles wint
        assert is_alleen_eigen_registraties(self.medewerker_user, self.org.id) is False

    def test_alleen_eigen_registraties_route_filtering_and_ui(self):
        """Test dat in de registratielijst de filter verborgen is en enkel eigen registraties getoond worden."""
        from models.digidokter import Digidokter
        from models.registration import Registration
        from datetime import date

        # Maak digidokter profielen
        dd_tim = Digidokter(naam='UserTim', user_id=self.medewerker_user.id, organisatie_id=self.org.id, actief=True)
        dd_other = Digidokter(naam='Andere Dokter', organisatie_id=self.org.id, actief=True)
        db.session.add_all([dd_tim, dd_other])
        db.session.commit()

        # Maak 2 registraties
        reg1 = Registration(
            registratienummer='REG-TIM-001',
            datum=date.today(),
            client='Klant Tim',
            digidokter_id=dd_tim.id,
            aangemaakt_door_id=self.medewerker_user.id,
            organisatie_id=self.org.id,
            onderwerp='Vraag voor Tim',
            leeftijdscategorie_id=self.age_category.id,
            toestel_id=self.device.id,
            locatie_id=None
        )
        reg2 = Registration(
            registratienummer='REG-OTHER-002',
            datum=date.today(),
            client='Klant Ander',
            digidokter_id=dd_other.id,
            aangemaakt_door_id=self.admin_user.id,
            organisatie_id=self.org.id,
            onderwerp='Vraag voor Ander',
            leeftijdscategorie_id=self.age_category.id,
            toestel_id=self.device.id,
            locatie_id=None
        )
        db.session.add_all([reg1, reg2])
        db.session.commit()

        # Koppel medewerker Tim aan een groep met alleen_eigen_registraties=True
        g_restricteerd = Group(organisatie_id=self.org.id, naam='Digidokter Privé', alleen_eigen_registraties=True)
        g_restricteerd.set_permission(FEATURE_REGISTRATIES, ACCESS_READ)
        db.session.add(g_restricteerd)
        db.session.commit()

        ug = UserGroup(user_id=self.medewerker_user.id, groep_id=g_restricteerd.id)
        db.session.add(ug)
        db.session.commit()

        # Log in als UserTim
        self.login(self.medewerker_user.email, 'password123')

        resp = self.client.get('/registraties')
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)

        # Reg 1 van Tim moet zichtbaar zijn
        assert 'REG-TIM-001' in html
        assert 'Klant Tim' in html

        # Reg 2 van Andere Dokter mag NIET zichtbaar zijn
        assert 'REG-OTHER-002' not in html
        assert 'Klant Ander' not in html

        # Digidokter filter dropdown mag NIET in het formulier voorkomen
        assert 'name="digidokter"' not in html

        # Poging tot manueel filteren via querystring ?digidokter=<dd_other.id> mag geen vreemde data lekken
        resp_tamper = self.client.get(f'/registraties?digidokter={dd_other.id}')
        assert resp_tamper.status_code == 200
        html_tamper = resp_tamper.get_data(as_text=True)
        assert 'REG-OTHER-002' not in html_tamper
        assert 'REG-TIM-001' in html_tamper

        # Log in als beheerder: beheerder ziet wél alles en heeft wél het filter
        self.logout()
        self.login(self.admin_user.email, 'password123')
        resp_admin = self.client.get('/registraties')
        assert resp_admin.status_code == 200
        html_admin = resp_admin.get_data(as_text=True)
        assert 'REG-TIM-001' in html_admin
        assert 'REG-OTHER-002' in html_admin
        assert 'name="digidokter"' in html_admin
