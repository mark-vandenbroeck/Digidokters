"""Tests voor de statusfilters (alle, enkel actief, enkel inactief) op stamgegevens overzichtspagina's."""
from tests.base import BaseTestCase
from extensions import db
from models.digidokter import Digidokter
from models.age_category import AgeCategory
from models.device import Device
from models.herkomst import Herkomst
from models.gender_identity import GenderIdentity
from models.functie import Functie
from models.activity_type import ActivityType
from models.location import Location
from models.question_category import QuestionCategory
from models.organisatie import Organisatie


class TestStamgegevensStatusFilters(BaseTestCase):

    def setUp(self):
        super().setUp()
        self.login("AdminMark", "password123")
        self.select_organisatie(self.org.id)

        # Maak actieve en inactieve items aan
        self.dd_actief = Digidokter(naam="DD Actief", actief=True, organisatie_id=self.org.id, volgorde=1)
        self.dd_inactief = Digidokter(naam="DD Inactief", actief=False, organisatie_id=self.org.id, volgorde=2)

        self.age_actief = AgeCategory(naam="Leeftijd Actief", actief=True, organisatie_id=self.org.id, volgorde=1)
        self.age_inactief = AgeCategory(naam="Leeftijd Inactief", actief=False, organisatie_id=self.org.id, volgorde=2)

        self.dev_actief = Device(naam="Toestel Actief", actief=True, organisatie_id=self.org.id, volgorde=1)
        self.dev_inactief = Device(naam="Toestel Inactief", actief=False, organisatie_id=self.org.id, volgorde=2)

        self.herk_actief = Herkomst(naam="Herkomst Actief", actief=True, organisatie_id=self.org.id, volgorde=1)
        self.herk_inactief = Herkomst(naam="Herkomst Inactief", actief=False, organisatie_id=self.org.id, volgorde=2)

        self.gen_actief = GenderIdentity(naam="Gender Actief", actief=True, organisatie_id=self.org.id, volgorde=1)
        self.gen_inactief = GenderIdentity(naam="Gender Inactief", actief=False, organisatie_id=self.org.id, volgorde=2)

        self.func_actief = Functie(naam="Functie Actief", actief=True, organisatie_id=self.org.id, volgorde=1)
        self.func_inactief = Functie(naam="Functie Inactief", actief=False, organisatie_id=self.org.id, volgorde=2)

        self.act_actief = ActivityType(naam="Type Actief", actief=True, organisatie_id=self.org.id, volgorde=1)
        self.act_inactief = ActivityType(naam="Type Inactief", actief=False, organisatie_id=self.org.id, volgorde=2)

        self.loc_actief = Location(naam="Locatie Actief", actief=True, organisatie_id=self.org.id, volgorde=1)
        self.loc_inactief = Location(naam="Locatie Inactief", actief=False, organisatie_id=self.org.id, volgorde=2)

        db.session.add_all([
            self.dd_actief, self.dd_inactief,
            self.age_actief, self.age_inactief,
            self.dev_actief, self.dev_inactief,
            self.herk_actief, self.herk_inactief,
            self.gen_actief, self.gen_inactief,
            self.func_actief, self.func_inactief,
            self.act_actief, self.act_inactief,
            self.loc_actief, self.loc_inactief
        ])
        db.session.commit()

    def test_digidokters_filter(self):
        # Alle
        res = self.client.get('/beheer/digidokters?status=alle')
        self.assertEqual(res.status_code, 200)
        self.assertIn("DD Actief", res.data.decode('utf-8'))
        self.assertIn("DD Inactief", res.data.decode('utf-8'))

        # Enkel actief
        res = self.client.get('/beheer/digidokters?status=actief')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        self.assertIn("DD Actief", html)
        self.assertNotIn("DD Inactief", html)

        # Enkel inactief
        res = self.client.get('/beheer/digidokters?status=inactief')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        self.assertNotIn("DD Actief", html)
        self.assertIn("DD Inactief", html)

    def test_leeftijdscategorieen_filter(self):
        # Enkel actief
        res = self.client.get('/beheer/leeftijdscategorieën?status=actief')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        self.assertIn("Leeftijd Actief", html)
        self.assertNotIn("Leeftijd Inactief", html)

        # Enkel inactief
        res = self.client.get('/beheer/leeftijdscategorieën?status=inactief')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        self.assertNotIn("Leeftijd Actief", html)
        self.assertIn("Leeftijd Inactief", html)

    def test_toestellen_filter(self):
        # Enkel actief
        res = self.client.get('/beheer/toestellen?status=actief')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        self.assertIn("Toestel Actief", html)
        self.assertNotIn("Toestel Inactief", html)

        # Enkel inactief
        res = self.client.get('/beheer/toestellen?status=inactief')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        self.assertNotIn("Toestel Actief", html)
        self.assertIn("Toestel Inactief", html)

    def test_herkomsten_filter(self):
        # Enkel actief
        res = self.client.get('/beheer/herkomsten?status=actief')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        self.assertIn("Herkomst Actief", html)
        self.assertNotIn("Herkomst Inactief", html)

        # Enkel inactief
        res = self.client.get('/beheer/herkomsten?status=inactief')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        self.assertNotIn("Herkomst Actief", html)
        self.assertIn("Herkomst Inactief", html)

    def test_genderidentiteiten_filter(self):
        # Enkel actief
        res = self.client.get('/beheer/genderidentiteiten?status=actief')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        self.assertIn("Gender Actief", html)
        self.assertNotIn("Gender Inactief", html)

        # Enkel inactief
        res = self.client.get('/beheer/genderidentiteiten?status=inactief')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        self.assertNotIn("Gender Actief", html)
        self.assertIn("Gender Inactief", html)

    def test_functies_filter(self):
        # Enkel actief
        res = self.client.get('/beheer/functies?status=actief')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        self.assertIn("Functie Actief", html)
        self.assertNotIn("Functie Inactief", html)

        # Enkel inactief
        res = self.client.get('/beheer/functies?status=inactief')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        self.assertNotIn("Functie Actief", html)
        self.assertIn("Functie Inactief", html)

    def test_activiteitstypes_filter(self):
        # Enkel actief
        res = self.client.get('/beheer/activiteitstypes?status=actief')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        self.assertIn("Type Actief", html)
        self.assertNotIn("Type Inactief", html)

        # Enkel inactief
        res = self.client.get('/beheer/activiteitstypes?status=inactief')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        self.assertNotIn("Type Actief", html)
        self.assertIn("Type Inactief", html)

    def test_locaties_filter(self):
        # Enkel actief
        res = self.client.get('/beheer/locaties?status=actief')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        self.assertIn("Locatie Actief", html)
        self.assertNotIn("Locatie Inactief", html)

        # Enkel inactief
        res = self.client.get('/beheer/locaties?status=inactief')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        self.assertNotIn("Locatie Actief", html)
        self.assertIn("Locatie Inactief", html)

    def test_vraagcategorieen_filter(self):
        # Platform login
        self.admin_user.rol = 'platformbeheerder'
        db.session.commit()

        cat_actief = QuestionCategory(naam="Vraagcat Actief", omschrijving="Test", actief=True, volgorde=100)
        cat_inactief = QuestionCategory(naam="Vraagcat Inactief", omschrijving="Test", actief=False, volgorde=101)
        db.session.add_all([cat_actief, cat_inactief])
        db.session.commit()

        # Enkel actief
        res = self.client.get('/platform/vraagcategorieen?status=actief')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        self.assertIn("Vraagcat Actief", html)
        self.assertNotIn("Vraagcat Inactief", html)

        # Enkel inactief
        res = self.client.get('/platform/vraagcategorieen?status=inactief')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        self.assertNotIn("Vraagcat Actief", html)
        self.assertIn("Vraagcat Inactief", html)

    def test_toggle_preserves_status_filter(self):
        res = self.client.get(f'/beheer/digidokters/{self.dd_actief.id}/toggle?status=actief', follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertIn('status=actief', res.headers['Location'])
