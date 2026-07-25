from tests.base import BaseTestCase
from flask import session
from extensions import db
from models.herkomst import Herkomst

class TestHerkomst(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.login("AdminMark", "password123")
        self.select_organisatie(self.org.id)

    def test_herkomst_list_admin_access(self):
        # Admin can access the list
        response = self.client.get('/beheer/herkomsten')
        self.assertEqual(response.status_code, 200)
        self.assertIn("Test Herkomst", response.data.decode('utf-8'))

    def test_herkomst_list_medewerker_denied(self):
        # Log out admin and login as regular medewerker
        self.logout()
        self.login("UserTim", "password123")
        self.select_organisatie(self.org.id)

        # Medewerker should be redirected to registrations list (302)
        response = self.client.get('/beheer/herkomsten')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/registraties', response.headers['Location'])

    def test_herkomst_crud_lifecycle(self):
        # 1. Create new Herkomst
        data = {
            'naam': 'Social Media',
            'actief': 'on'
        }
        response = self.client.post('/beheer/herkomsten/nieuw', data=data, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Social Media", response.data.decode('utf-8'))

        # Verify in DB
        h = Herkomst.query.filter_by(naam='Social Media', organisatie_id=self.org.id).first()
        self.assertIsNotNone(h)
        self.assertTrue(h.actief)

        # 2. Edit Herkomst
        edit_data = {
            'naam': 'Social Media & Website',
            'actief': 'on'
        }
        response = self.client.post(f'/beheer/herkomsten/{h.id}/wijzig', data=edit_data, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Social Media &amp; Website", response.data.decode('utf-8'))

        # Verify updated in DB
        h_updated = db.session.get(Herkomst, h.id)
        self.assertEqual(h_updated.naam, 'Social Media & Website')

        # 3. Toggle Active
        response = self.client.get(f'/beheer/herkomsten/{h.id}/toggle', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(h_updated.actief)

        # 4. Volgorde Reordering
        # Create another herkomst so we have multiple to sort
        h2 = Herkomst(naam="Mondeling", actief=True, volgorde=2, organisatie_id=self.org.id)
        db.session.add(h2)
        db.session.commit()

        # Move h2 (which has volgorde 2 and comes after h_updated) omhoog
        response = self.client.get(f'/beheer/herkomsten/{h2.id}/volgorde/omhoog', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        
        # Verify volgordes are swapped/recalculated
        db.session.refresh(h_updated)
        db.session.refresh(h2)
        # Since h2 went up, it should have a lower volgorde than h_updated now
        self.assertLess(h2.volgorde, h_updated.volgorde)
