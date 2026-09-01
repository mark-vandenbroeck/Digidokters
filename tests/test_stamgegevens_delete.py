from tests.base import BaseTestCase
from extensions import db
from models.organisatie import Organisatie, UserOrganisatie
from models.user import User
from models.location import Location
from models.activity_type import ActivityType
from models.age_category import AgeCategory
from models.device import Device
from models.herkomst import Herkomst
from models.agenda import AgendaItem
from models.registration import Registration
from models.evaluation import EvaluationForm, EvaluationQuestion, EvaluationResponse
from werkzeug.security import generate_password_hash
import datetime


class TestStamgegevensDelete(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.platform_admin = User(
            naam="SuperPlatformAdmin",
            email="superplatform@test.be",
            wachtwoord_hash=generate_password_hash("password123"),
            rol="platformbeheerder",
            actief=True
        )
        db.session.add(self.platform_admin)
        db.session.commit()

    def test_delete_location(self):
        # Create unreferenced location
        loc = Location(naam="Ongebruikte Locatie", actief=True, volgorde=10, organisatie_id=self.org.id)
        db.session.add(loc)
        db.session.commit()
        loc_id = loc.id

        # 1. Beheerder can delete unreferenced location
        self.login("admin@test.com", "password123")
        resp = self.client.post(f'/beheer/locaties/{loc_id}/verwijderen', follow_redirects=True)
        self.assertIn('succesvol verwijderd', resp.get_data(as_text=True))
        self.assertIsNone(db.session.get(Location, loc_id))

        # 2. Location with agenda items cannot be deleted
        loc2 = Location(naam="Locatie Met Agenda", actief=True, volgorde=11, organisatie_id=self.org.id)
        act = ActivityType(naam="Type Voor Agenda", actief=True, volgorde=10, organisatie_id=self.org.id)
        db.session.add_all([loc2, act])
        db.session.commit()

        agenda = AgendaItem(
            datum=datetime.date(2026, 9, 10),
            uur_van="14:00",
            uur_tot="16:00",
            type_id=act.id,
            locatie_id=loc2.id,
            organisatie_id=self.org.id
        )
        db.session.add(agenda)
        db.session.commit()

        resp = self.client.post(f'/beheer/locaties/{loc2.id}/verwijderen', follow_redirects=True)
        self.assertIn('kan niet worden verwijderd omdat er nog 1 agenda-activiteit(en) aan gekoppeld zijn', resp.get_data(as_text=True))
        self.assertIsNotNone(db.session.get(Location, loc2.id))

    def test_delete_activity_type(self):
        # Create unreferenced activity type with empty evaluation form
        act = ActivityType(naam="Unused Workshop", actief=True, heeft_evaluatie=True, volgorde=10, organisatie_id=self.org.id)
        db.session.add(act)
        db.session.commit()
        act_id = act.id

        form = EvaluationForm(organisatie_id=self.org.id, activity_type_id=act_id, titel="Evaluatie Unused Workshop", actief=True)
        db.session.add(form)
        db.session.commit()

        # 1. Beheerder can delete unreferenced activity type (and its empty form)
        self.login("admin@test.com", "password123")
        resp = self.client.post(f'/beheer/activiteitstypes/{act_id}/verwijderen', follow_redirects=True)
        self.assertIn('succesvol verwijderd', resp.get_data(as_text=True))
        self.assertIsNone(db.session.get(ActivityType, act_id))
        self.assertIsNone(db.session.get(EvaluationForm, form.id))

        # 2. ActivityType with agenda items cannot be deleted
        loc = Location(naam="Test Locatie Act", actief=True, volgorde=1, organisatie_id=self.org.id)
        act2 = ActivityType(naam="Type Met Agenda", actief=True, volgorde=11, organisatie_id=self.org.id)
        db.session.add_all([loc, act2])
        db.session.commit()

        agenda = AgendaItem(
            datum=datetime.date(2026, 9, 10),
            uur_van="14:00",
            uur_tot="16:00",
            type_id=act2.id,
            locatie_id=loc.id,
            organisatie_id=self.org.id
        )
        db.session.add(agenda)
        db.session.commit()

        resp = self.client.post(f'/beheer/activiteitstypes/{act2.id}/verwijderen', follow_redirects=True)
        self.assertIn('kan niet worden verwijderd omdat er nog 1 agenda-activiteit(en) aan gekoppeld zijn', resp.get_data(as_text=True))
        self.assertIsNotNone(db.session.get(ActivityType, act2.id))

    def test_delete_age_category(self):
        # 1. Unreferenced age category can be deleted
        cat = AgeCategory(naam="Unused 100+", actief=True, volgorde=10, organisatie_id=self.org.id)
        db.session.add(cat)
        db.session.commit()
        cat_id = cat.id

        self.login("admin@test.com", "password123")
        resp = self.client.post(f'/beheer/leeftijdscategorieën/{cat_id}/verwijderen', follow_redirects=True)
        self.assertIn('succesvol verwijderd', resp.get_data(as_text=True))
        self.assertIsNone(db.session.get(AgeCategory, cat_id))

        # 2. Age category with registrations cannot be deleted
        cat2 = AgeCategory(naam="Cat Met Reg", actief=True, volgorde=11, organisatie_id=self.org.id)
        db.session.add(cat2)
        db.session.commit()

        reg = Registration(
            registratienummer="2026-CAT-001",
            client="Karel",
            datum=datetime.date(2026, 9, 1),
            digidokter_id=self.digidokter.id,
            toestel_id=self.device.id,
            leeftijdscategorie_id=cat2.id,
            onderwerp="Vraagje",
            organisatie_id=self.org.id,
            aangemaakt_door_id=self.admin_user.id
        )
        db.session.add(reg)
        db.session.commit()

        resp = self.client.post(f'/beheer/leeftijdscategorieën/{cat2.id}/verwijderen', follow_redirects=True)
        self.assertIn('kan niet worden verwijderd omdat er nog 1 registratie(s) aan gekoppeld zijn', resp.get_data(as_text=True))
        self.assertIsNotNone(db.session.get(AgeCategory, cat2.id))

    def test_delete_device(self):
        # 1. Unreferenced device can be deleted
        dev = Device(naam="Unused Smartwatch", actief=True, volgorde=10, organisatie_id=self.org.id)
        db.session.add(dev)
        db.session.commit()
        dev_id = dev.id

        self.login("admin@test.com", "password123")
        resp = self.client.post(f'/beheer/toestellen/{dev_id}/verwijderen', follow_redirects=True)
        self.assertIn('succesvol verwijderd', resp.get_data(as_text=True))
        self.assertIsNone(db.session.get(Device, dev_id))

        # 2. Device with registrations cannot be deleted
        dev2 = Device(naam="Dev Met Reg", actief=True, volgorde=11, organisatie_id=self.org.id)
        db.session.add(dev2)
        db.session.commit()

        reg = Registration(
            registratienummer="2026-DEV-001",
            client="Lies",
            datum=datetime.date(2026, 9, 1),
            digidokter_id=self.digidokter.id,
            toestel_id=dev2.id,
            leeftijdscategorie_id=self.age_category.id,
            onderwerp="Vraagje",
            organisatie_id=self.org.id,
            aangemaakt_door_id=self.admin_user.id
        )
        db.session.add(reg)
        db.session.commit()

        resp = self.client.post(f'/beheer/toestellen/{dev2.id}/verwijderen', follow_redirects=True)
        self.assertIn('kan niet worden verwijderd omdat er nog 1 registratie(s) aan gekoppeld zijn', resp.get_data(as_text=True))
        self.assertIsNotNone(db.session.get(Device, dev2.id))

    def test_delete_herkomst(self):
        # 1. Unreferenced herkomst can be deleted
        hk = Herkomst(naam="Unused Reclamebord", actief=True, volgorde=10, organisatie_id=self.org.id)
        db.session.add(hk)
        db.session.commit()
        hk_id = hk.id

        self.login("admin@test.com", "password123")
        resp = self.client.post(f'/beheer/herkomsten/{hk_id}/verwijderen', follow_redirects=True)
        self.assertIn('succesvol verwijderd', resp.get_data(as_text=True))
        self.assertIsNone(db.session.get(Herkomst, hk_id))

        # 2. Herkomst with registrations cannot be deleted
        hk2 = Herkomst(naam="Hk Met Reg", actief=True, volgorde=11, organisatie_id=self.org.id)
        db.session.add(hk2)
        db.session.commit()

        reg = Registration(
            registratienummer="2026-HK-001",
            client="Sophie",
            datum=datetime.date(2026, 9, 1),
            digidokter_id=self.digidokter.id,
            toestel_id=self.device.id,
            leeftijdscategorie_id=self.age_category.id,
            herkomst_id=hk2.id,
            onderwerp="Vraagje",
            organisatie_id=self.org.id,
            aangemaakt_door_id=self.admin_user.id
        )
        db.session.add(reg)
        db.session.commit()

        resp = self.client.post(f'/beheer/herkomsten/{hk2.id}/verwijderen', follow_redirects=True)
        self.assertIn('kan niet worden verwijderd omdat er nog 1 registratie(s) aan gekoppeld zijn', resp.get_data(as_text=True))
        self.assertIsNotNone(db.session.get(Herkomst, hk2.id))

    def test_delete_stamgegevens_authorization_and_isolation(self):
        # Create unreferenced item in Org 1
        loc = Location(naam="Org1 Locatie", actief=True, volgorde=1, organisatie_id=self.org.id)
        db.session.add(loc)

        # Create Org 2 and an item in Org 2
        org2 = Organisatie(naam="Org 2", slug="org-2", actief=True)
        db.session.add(org2)
        db.session.commit()
        loc_org2 = Location(naam="Org2 Locatie", actief=True, volgorde=1, organisatie_id=org2.id)
        db.session.add(loc_org2)
        db.session.commit()

        # 1. Medewerker (regular user) gets redirected with access denied flash message
        self.login("tim@test.com", "password123")
        resp = self.client.post(f'/beheer/locaties/{loc.id}/verwijderen', follow_redirects=True)
        self.assertIn('U heeft geen toegang tot deze pagina.', resp.get_data(as_text=True))
        self.assertIsNotNone(db.session.get(Location, loc.id))

        # 2. Beheerder in Org 1 cannot delete item in Org 2 (403)
        self.logout()
        self.login("admin@test.com", "password123")
        resp = self.client.post(f'/beheer/locaties/{loc_org2.id}/verwijderen', follow_redirects=True)
        self.assertEqual(resp.status_code, 403)
        self.assertIsNotNone(db.session.get(Location, loc_org2.id))

        # 3. Platform admin can delete item
        self.logout()
        self.login("superplatform@test.be", "password123")
        self.client.post('/switch-organisatie', data={'organisatie_id': org2.id}, follow_redirects=True)
        resp = self.client.post(f'/beheer/locaties/{loc_org2.id}/verwijderen', follow_redirects=True)
        self.assertIn('succesvol verwijderd', resp.get_data(as_text=True))
        self.assertIsNone(db.session.get(Location, loc_org2.id))
