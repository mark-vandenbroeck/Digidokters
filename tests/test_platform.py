from tests.base import BaseTestCase
from extensions import db
from models.user import User
from models.organisatie import Organisatie
from models.age_category import AgeCategory
from models.device import Device
from models.activity_type import ActivityType
from models.location import Location
from models.herkomst import Herkomst
from utils.tenant import seed_organisatie_defaults

class TestPlatformSeeding(BaseTestCase):
    def test_seed_organisatie_defaults_copies_active_from_org_1(self):
        # 1. Setup master data in organization 1 (self.org has id 1)
        self.assertEqual(self.org.id, 1)

        # Clear existing seeded objects in org 1 to have full control
        AgeCategory.query.filter_by(organisatie_id=1).delete()
        Device.query.filter_by(organisatie_id=1).delete()
        Herkomst.query.filter_by(organisatie_id=1).delete()
        ActivityType.query.filter_by(organisatie_id=1).delete()
        Location.query.filter_by(organisatie_id=1).delete()
        db.session.commit()

        # Add active and inactive AgeCategory
        cat_active = AgeCategory(naam="Actieve Lft", actief=True, volgorde=10, organisatie_id=1)
        cat_inactive = AgeCategory(naam="Inactieve Lft", actief=False, volgorde=11, organisatie_id=1)

        # Add active and inactive Device
        dev_active = Device(naam="Actief Toestel", actief=True, volgorde=20, organisatie_id=1)
        dev_inactive = Device(naam="Inactief Toestel", actief=False, volgorde=21, organisatie_id=1)

        # Add active and inactive ActivityType
        type_active = ActivityType(naam="Actief Type", actief=True, kleur="teal", volgorde=30, organisatie_id=1)
        type_inactive = ActivityType(naam="Inactief Type", actief=False, kleur="blue", volgorde=31, organisatie_id=1)

        # Add active and inactive Location
        loc_active = Location(naam="Actieve Locatie", actief=True, volgorde=40, organisatie_id=1)
        loc_inactive = Location(naam="Inactieve Locatie", actief=False, volgorde=41, organisatie_id=1)

        # Add active and inactive Herkomst
        hk_active = Herkomst(naam="Actieve Herkomst", actief=True, volgorde=50, organisatie_id=1)
        hk_inactive = Herkomst(naam="Inactieve Herkomst", actief=False, volgorde=51, organisatie_id=1)

        db.session.add_all([
            cat_active, cat_inactive,
            dev_active, dev_inactive,
            type_active, type_inactive,
            loc_active, loc_inactive,
            hk_active, hk_inactive
        ])
        db.session.commit()

        # 2. Create organization 2
        org2 = Organisatie(id=2, naam="Nieuwe Org", slug="nieuwe-org", actief=True)
        db.session.add(org2)
        db.session.commit()

        # 3. Call seed defaults for organization 2
        seed_organisatie_defaults(org2.id)

        # 4. Verify only active items from org 1 were copied
        # AgeCategory checks
        cats = AgeCategory.query.filter_by(organisatie_id=2).all()
        self.assertEqual(len(cats), 1)
        self.assertEqual(cats[0].naam, "Actieve Lft")
        self.assertTrue(cats[0].actief)

        # Device checks
        devs = Device.query.filter_by(organisatie_id=2).all()
        self.assertEqual(len(devs), 1)
        self.assertEqual(devs[0].naam, "Actief Toestel")
        self.assertTrue(devs[0].actief)

        # ActivityType checks
        types = ActivityType.query.filter_by(organisatie_id=2).all()
        self.assertEqual(len(types), 1)
        self.assertEqual(types[0].naam, "Actief Type")
        self.assertEqual(types[0].kleur, "teal")
        self.assertTrue(types[0].actief)

        # Location checks
        locs = Location.query.filter_by(organisatie_id=2).all()
        self.assertEqual(len(locs), 1)
        self.assertEqual(locs[0].naam, "Actieve Locatie")
        self.assertTrue(locs[0].actief)

        # Herkomst checks
        hks = Herkomst.query.filter_by(organisatie_id=2).all()
        self.assertEqual(len(hks), 1)
        self.assertEqual(hks[0].naam, "Actieve Herkomst")
        self.assertTrue(hks[0].actief)


class TestPlatformOrganizationDelete(BaseTestCase):
    def setUp(self):
        super().setUp()
        from werkzeug.security import generate_password_hash
        self.platform_admin = User(
            naam="SuperPlatformAdmin",
            email="superplatform@test.be",
            wachtwoord_hash=generate_password_hash("password123"),
            rol="platformbeheerder",
            actief=True
        )
        db.session.add(self.platform_admin)
        db.session.commit()

    def test_cannot_delete_default_organization_1(self):
        self.login("superplatform@test.be", "password123")
        resp = self.client.post('/platform/organisaties/1/verwijderen', follow_redirects=True)
        self.assertIn('is een beschermde systeemorganisatie en kan niet worden gewist.', resp.get_data(as_text=True))
        self.assertIsNotNone(db.session.get(Organisatie, 1))

    def test_delete_organization_requires_platform_admin(self):
        # Create org 2
        org2 = Organisatie(naam="Test Delete Org", slug="test-delete-org", actief=True)
        db.session.add(org2)
        db.session.commit()

        # Regular user should be forbidden
        self.login("tim@test.com", "password123")
        resp = self.client.post(f'/platform/organisaties/{org2.id}/verwijderen', follow_redirects=True)
        self.assertIn('U heeft geen toegang tot deze pagina.', resp.get_data(as_text=True))
        self.assertIsNotNone(db.session.get(Organisatie, org2.id))

    def test_delete_organization_cascades_all_data(self):
        from models.user import User
        from models.organisatie import UserOrganisatie
        from models.digidokter import Digidokter
        from models.agenda import AgendaItem
        from models.registration import Registration
        from models.document import Document, Folder
        from models.evaluation import EvaluationForm, EvaluationQuestion, EvaluationResponse
        from werkzeug.security import generate_password_hash
        import datetime

        # 1. Create org 2
        org2 = Organisatie(naam="Gemeente Test", slug="gemeente-test", actief=True)
        db.session.add(org2)
        db.session.commit()
        org2_id = org2.id

        # 2. Seed data in org 2
        seed_organisatie_defaults(org2_id)

        # 3. Add users: one exclusive to org 2, one shared with org 1
        user_exclusive = User(naam="Exclusieve Medewerker", email="exclusive@test.be", wachtwoord_hash=generate_password_hash("password123"), rol="medewerker")
        db.session.add(user_exclusive)
        db.session.commit()
        db.session.add(UserOrganisatie(user_id=user_exclusive.id, organisatie_id=org2_id, rol="medewerker", actief=True))

        # Shared user (self.admin_user is in org 1, link to org 2 as well)
        db.session.add(UserOrganisatie(user_id=self.admin_user.id, organisatie_id=org2_id, rol="beheerder", actief=True))

        # Add Digidokter, ActivityType, Location in org 2
        dd = Digidokter(naam="Jan Test", actief=True, volgorde=1, organisatie_id=org2_id)
        act = ActivityType.query.filter_by(organisatie_id=org2_id).first()
        loc = Location.query.filter_by(organisatie_id=org2_id).first()
        dev = Device.query.filter_by(organisatie_id=org2_id).first()
        age = AgeCategory.query.filter_by(organisatie_id=org2_id).first()
        db.session.add(dd)
        db.session.commit()

        # Add AgendaItem
        agenda = AgendaItem(
            datum=datetime.date(2026, 9, 1),
            uur_van="14:00",
            uur_tot="16:00",
            type_id=act.id,
            locatie_id=loc.id,
            organisatie_id=org2_id
        )
        agenda.digidokters.append(dd)
        db.session.add(agenda)
        db.session.commit()

        # Add Registration
        reg = Registration(
            registratienummer="2026-TEST-001",
            client="Piet",
            datum=datetime.date(2026, 9, 1),
            digidokter_id=dd.id,
            toestel_id=dev.id,
            leeftijdscategorie_id=age.id,
            onderwerp="Test registratie",
            organisatie_id=org2_id,
            aangemaakt_door_id=user_exclusive.id
        )
        db.session.add(reg)

        # Add Folder & Document
        folder = Folder(naam="Testmap", organisatie_id=org2_id, aangemaakt_door_id=self.admin_user.id)
        db.session.add(folder)
        db.session.commit()

        doc = Document(
            bestandsnaam="test.pdf",
            type="pdf",
            mime_type="application/pdf",
            bestandsgrootte=123,
            inhoud=b"PDF CONTENT",
            organisatie_id=org2_id,
            map_id=folder.id,
            aangemaakt_door_id=self.admin_user.id
        )
        db.session.add(doc)
        db.session.commit()

        # Verify everything is present before delete
        self.assertGreater(Registration.query.filter_by(organisatie_id=org2_id).count(), 0)
        self.assertGreater(AgendaItem.query.filter_by(organisatie_id=org2_id).count(), 0)
        self.assertGreater(Folder.query.filter_by(organisatie_id=org2_id).count(), 0)
        self.assertGreater(Document.query.filter_by(organisatie_id=org2_id).count(), 0)

        # 4. Perform Delete as platform admin
        self.login("superplatform@test.be", "password123")
        resp = self.client.post(f'/platform/organisaties/{org2_id}/verwijderen', follow_redirects=True)
        self.assertIn('zijn definitief gewist', resp.get_data(as_text=True))

        # 5. Verify org2 and all its data are wiped
        self.assertIsNone(db.session.get(Organisatie, org2_id))
        self.assertEqual(Registration.query.filter_by(organisatie_id=org2_id).count(), 0)
        self.assertEqual(AgendaItem.query.filter_by(organisatie_id=org2_id).count(), 0)
        self.assertEqual(Folder.query.filter_by(organisatie_id=org2_id).count(), 0)
        self.assertEqual(Document.query.filter_by(organisatie_id=org2_id).count(), 0)
        self.assertEqual(Digidokter.query.filter_by(organisatie_id=org2_id).count(), 0)
        self.assertEqual(ActivityType.query.filter_by(organisatie_id=org2_id).count(), 0)
        self.assertEqual(EvaluationForm.query.filter_by(organisatie_id=org2_id).count(), 0)
        self.assertEqual(UserOrganisatie.query.filter_by(organisatie_id=org2_id).count(), 0)

        # Exclusive user should be cleaned up
        self.assertIsNone(db.session.get(User, user_exclusive.id))

        # Shared user (self.admin_user) still exists in org 1
        self.assertIsNotNone(db.session.get(User, self.admin_user.id))

        # Org 1 data should still exist untouched
        self.assertIsNotNone(db.session.get(Organisatie, 1))

    def test_cannot_delete_sjabloon_organization(self):
        sjabloon = Organisatie(naam="Sjabloon", slug="sjabloon", actief=True)
        db.session.add(sjabloon)
        db.session.commit()

        self.login("superplatform@test.be", "password123")
        resp = self.client.post(f'/platform/organisaties/{sjabloon.id}/verwijderen', follow_redirects=True)
        self.assertIn('is een beschermde systeemorganisatie en kan niet worden gewist.', resp.get_data(as_text=True))
        self.assertIsNotNone(db.session.get(Organisatie, sjabloon.id))

    def test_sjabloon_accessible_only_by_platform_admin(self):
        sjabloon = Organisatie(naam="Sjabloon", slug="sjabloon", actief=True)
        db.session.add(sjabloon)
        db.session.commit()

        # 1. Platform admin can switch to Sjabloon
        self.login("superplatform@test.be", "password123")
        resp = self.client.post('/switch-organisatie', data={'organisatie_id': sjabloon.id}, follow_redirects=True)
        self.assertIn('Gewisseld naar organisatie: Sjabloon', resp.get_data(as_text=True))

        # 2. Platform admin cannot link regular user to Sjabloon
        resp = self.client.post('/platform/koppelingen', data={
            'user_id': self.medewerker_user.id,
            'organisatie_id': sjabloon.id,
            'rol': 'medewerker',
            'actief': 'on'
        }, follow_redirects=True)
        self.assertIn('Enkel platformbeheerders hebben toegang tot de Sjabloon-organisatie.', resp.get_data(as_text=True))

        # 3. Regular user attempting to switch to Sjabloon is rejected
        self.logout()
        self.login("tim@test.com", "password123")
        resp = self.client.post('/switch-organisatie', data={'organisatie_id': sjabloon.id}, follow_redirects=True)
        self.assertIn('U heeft geen toegang tot deze organisatie.', resp.get_data(as_text=True))

