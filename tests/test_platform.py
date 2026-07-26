from tests.base import BaseTestCase
from extensions import db
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
