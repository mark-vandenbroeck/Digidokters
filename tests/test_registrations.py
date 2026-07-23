from tests.base import BaseTestCase
from flask import session
from extensions import db
from models.registration import Registration
from models.audit import AuditLog
from datetime import date

class TestRegistrations(BaseTestCase):
    def setUp(self):
        super().setUp()
        # Log in and select organization context
        self.login("AdminMark", "password123")
        self.select_organisatie(self.org.id)

    def test_create_registration_success(self):
        # Post data to create a new registration
        data = {
            'datum': str(date.today()),
            'client': "John Doe",
            'digidokter_id': str(self.digidokter.id),
            'nieuwe_klant': 'ja',
            'herkomst': 'Mond tot mond',
            'geslacht': 'man',
            'onderwerp': 'Uitleg over whatsapp',
            'leeftijdscategorie_id': str(self.age_category.id),
            'toestel_id': str(self.device.id)
        }
        
        # Call the new registration route
        response = self.client.post('/registraties/nieuw', data=data, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        
        # Verify that registration was added to database
        reg = Registration.query.filter_by(client="John Doe").first()
        self.assertIsNotNone(reg)
        self.assertEqual(reg.organisatie_id, self.org.id)
        self.assertEqual(reg.onderwerp, "Uitleg over whatsapp")
        self.assertTrue(reg.nieuwe_klant)

    def test_delete_registration_and_clean_audit_logs(self):
        # 1. Create a registration manually
        reg = Registration(
            registratienummer="2026-0001",
            datum=date.today(),
            client="Jane Doe",
            digidokter_id=self.digidokter.id,
            nieuwe_klant=False,
            onderwerp="Vraag over e-mail",
            leeftijdscategorie_id=self.age_category.id,
            toestel_id=self.device.id,
            organisatie_id=self.org.id,
            aangemaakt_door_id=self.admin_user.id
        )
        db.session.add(reg)
        db.session.commit()

        # Check registration exists
        reg_id = reg.id
        self.assertIsNotNone(Registration.query.get(reg_id))

        # 2. Simulate audit log creation for this registration
        # Since audit log triggers automatically, db.session.commit() above should have created a CREATE log
        audit_logs = AuditLog.query.filter_by(tabel='registrations', record_id=reg_id).all()
        self.assertGreater(len(audit_logs), 0)

        # 3. Call the delete route via POST
        response = self.client.post(f'/registraties/{reg_id}/verwijder', follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        # 4. Verify registration is deleted
        self.assertIsNone(Registration.query.get(reg_id))

        # 5. Verify associated audit logs are deleted (GDPR Compliance check)
        remaining_audit_logs = AuditLog.query.filter_by(tabel='registrations', record_id=reg_id).all()
        self.assertEqual(len(remaining_audit_logs), 0)
