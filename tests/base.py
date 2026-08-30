import unittest
from app import create_app
from extensions import db
from models.user import User
from models.organisatie import Organisatie, UserOrganisatie
from werkzeug.security import generate_password_hash

from config import Config

class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SQLALCHEMY_ENGINE_OPTIONS = {}  # Override to prevent SQLite in-memory engine pool errors
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False
    SECRET_KEY = 'test-secret-key'

class BaseTestCase(unittest.TestCase):
    def setUp(self):
        # Create the app with testing configuration
        self.app = create_app(TestConfig)
        
        # Establish app context
        self.app_context = self.app.app_context()
        self.app_context.push()
        
        # Create all schemas
        db.create_all()
        
        # Set up test client
        self.client = self.app.test_client()
        
        # Seed test data
        self.seed_test_data()

    def tearDown(self):
        # Cleanup session and drop all tables
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def seed_test_data(self):
        # 1. Create Default Organisatie
        self.org = Organisatie(
            naam="Digidokters Test",
            slug="digidokters-test",
            actief=True
        )
        db.session.add(self.org)
        db.session.commit()  # commit to get org.id

        # 2. Create Admin/Beheerder User
        self.admin_user = User(
            naam="AdminMark",
            email="admin@test.com",
            wachtwoord_hash=generate_password_hash("password123"),
            rol="beheerder",
            actief=True,
            moet_wachtwoord_wijzigen=False
        )
        db.session.add(self.admin_user)
        
        # 3. Create Regular Medewerker User
        self.medewerker_user = User(
            naam="UserTim",
            email="tim@test.com",
            wachtwoord_hash=generate_password_hash("password123"),
            rol="medewerker",
            actief=True,
            moet_wachtwoord_wijzigen=False
        )
        db.session.add(self.medewerker_user)
        db.session.commit()

        # 4. Link Users to Organisatie
        admin_membership = UserOrganisatie(
            user_id=self.admin_user.id,
            organisatie_id=self.org.id,
            rol="beheerder",
            actief=True
        )
        medewerker_membership = UserOrganisatie(
            user_id=self.medewerker_user.id,
            organisatie_id=self.org.id,
            rol="medewerker",
            actief=True
        )
        db.session.add_all([admin_membership, medewerker_membership])
        db.session.commit()

        # 5. Create test Digidokter, AgeCategory, Device
        from models.digidokter import Digidokter
        from models.age_category import AgeCategory
        from models.device import Device
        
        self.digidokter = Digidokter(
            naam="Test Digidokter",
            actief=True,
            organisatie_id=self.org.id
        )
        self.age_category = AgeCategory(
            naam="Test Leeftijdscategorie",
            actief=True,
            organisatie_id=self.org.id
        )
        from models.device import Device
        self.device = Device(
            naam="Test Toestel",
            actief=True,
            organisatie_id=self.org.id
        )
        from models.herkomst import Herkomst
        self.herkomst = Herkomst(
            naam="Test Herkomst",
            actief=True,
            organisatie_id=self.org.id
        )
        db.session.add_all([self.digidokter, self.age_category, self.device, self.herkomst])
        db.session.commit()

    def login(self, identifier, password):
        if '@' in identifier:
            email = identifier
        else:
            u = User.query.filter(db.func.lower(User.naam) == identifier.lower()).first()
            email = u.email if u and u.email else 'admin@test.com'
        return self.client.post('/login', data={
            'email': email,
            'wachtwoord': password
        }, follow_redirects=True)

    def logout(self):
        return self.client.get('/logout', follow_redirects=True)

    def select_organisatie(self, org_id):
        # Helper to set the organisation session context
        return self.client.post(f'/select-organisatie?next=/beheer/audit-log', data={
            'organisatie_id': org_id
        }, follow_redirects=True)
