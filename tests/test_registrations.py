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
            'herkomst_id': str(self.herkomst.id),
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
        self.assertEqual(reg.herkomst_id, self.herkomst.id)

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
        self.assertIsNotNone(db.session.get(Registration, reg_id))

        # 2. Simulate audit log creation for this registration
        # Since audit log triggers automatically, db.session.commit() above should have created a CREATE log
        audit_logs = AuditLog.query.filter_by(tabel='registrations', record_id=reg_id).all()
        self.assertGreater(len(audit_logs), 0)

        # 3. Call the delete route via POST
        response = self.client.post(f'/registraties/{reg_id}/verwijder', follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        # 4. Verify registration is deleted
        self.assertIsNone(db.session.get(Registration, reg_id))

        # 5. Verify associated audit logs are deleted (GDPR Compliance check)
        remaining_audit_logs = AuditLog.query.filter_by(tabel='registrations', record_id=reg_id).all()
        self.assertEqual(len(remaining_audit_logs), 0)

    def test_default_digidokter_preselected_on_new_form(self):
        # Koppel de digidokter aan de ingelogde gebruiker AdminMark
        self.digidokter.user_id = self.admin_user.id
        db.session.commit()

        response = self.client.get('/registraties/nieuw')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')

        # Controleer of de optie van self.digidokter het 'selected' attribuut heeft
        expected_option = f'<option value="{self.digidokter.id}"\n                                selected>\n                                {self.digidokter.naam}\n                            </option>'
        self.assertIn(f'value="{self.digidokter.id}"', html)
        self.assertIn('selected', html)
        self.assertIn(self.digidokter.naam, html)

    def test_registraties_filters(self):
        """Test filters op toesteltype, digidokter, leeftijdscategorie en geslacht."""
        from models.device import Device
        from models.age_category import AgeCategory
        from models.digidokter import Digidokter

        # Tweede toestel, leeftijdscategorie en digidokter aanmaken (actief)
        toestel_smartphone = Device(naam="Smartphone", actief=True, organisatie_id=self.org.id)
        leeftijd_jong = AgeCategory(naam="18-64 jaar", actief=True, organisatie_id=self.org.id)
        digidokter2 = Digidokter(naam="Tweede Dokter", actief=True, organisatie_id=self.org.id)

        # Inactieve items (mogen NIET in de filter-dropdowns verschijnen)
        toestel_inactief = Device(naam="Oude Faxmachine", actief=False, organisatie_id=self.org.id)
        leeftijd_inactief = AgeCategory(naam="Antieke Leeftijd", actief=False, organisatie_id=self.org.id)
        digidokter_inactief = Digidokter(naam="Inactieve Dokter", actief=False, organisatie_id=self.org.id)

        db.session.add_all([
            toestel_smartphone, leeftijd_jong, digidokter2,
            toestel_inactief, leeftijd_inactief, digidokter_inactief
        ])
        db.session.commit()

        # Drie registraties aanmaken
        r1 = Registration(
            registratienummer="2026-0101",
            datum=date.today(),
            client="Jan Man",
            digidokter_id=self.digidokter.id,
            toestel_id=self.device.id,
            leeftijdscategorie_id=self.age_category.id,
            geslacht="man",
            onderwerp="Probleem met laptop",
            organisatie_id=self.org.id,
            aangemaakt_door_id=self.admin_user.id
        )
        r2 = Registration(
            registratienummer="2026-0102",
            datum=date.today(),
            client="Els Vrouw",
            digidokter_id=digidokter2.id,
            toestel_id=toestel_smartphone.id,
            leeftijdscategorie_id=leeftijd_jong.id,
            geslacht="vrouw",
            onderwerp="Probleem met smartphone",
            organisatie_id=self.org.id,
            aangemaakt_door_id=self.admin_user.id
        )
        r3 = Registration(
            registratienummer="2026-0103",
            datum=date.today(),
            client="Sam Onbekend",
            digidokter_id=self.digidokter.id,
            toestel_id=toestel_smartphone.id,
            leeftijdscategorie_id=self.age_category.id,
            geslacht=None,
            onderwerp="Algemene vraag",
            organisatie_id=self.org.id,
            aangemaakt_door_id=self.admin_user.id
        )
        db.session.add_all([r1, r2, r3])
        db.session.commit()

        # 1. Test filter op toesteltype
        res = self.client.get(f"/registraties?toestel={self.device.id}")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")
        self.assertIn("Jan Man", html)
        self.assertNotIn("Els Vrouw", html)
        self.assertNotIn("Sam Onbekend", html)

        # 2. Test filter op digidokter
        res = self.client.get(f"/registraties?digidokter={digidokter2.id}")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")
        self.assertIn("Els Vrouw", html)
        self.assertNotIn("Jan Man", html)

        # 3. Test filter op leeftijdscategorie
        res = self.client.get(f"/registraties?leeftijd={leeftijd_jong.id}")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")
        self.assertIn("Els Vrouw", html)
        self.assertNotIn("Jan Man", html)
        self.assertNotIn("Sam Onbekend", html)

        # 4. Test filter op geslacht (man)
        res = self.client.get("/registraties?geslacht=man")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")
        self.assertIn("Jan Man", html)
        self.assertNotIn("Els Vrouw", html)
        self.assertNotIn("Sam Onbekend", html)

        # 5. Test filter op geslacht (vrouw)
        res = self.client.get("/registraties?geslacht=vrouw")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")
        self.assertIn("Els Vrouw", html)
        self.assertNotIn("Jan Man", html)

        # 6. Test filter op geslacht (onbekend)
        res = self.client.get("/registraties?geslacht=onbekend")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")
        self.assertIn("Sam Onbekend", html)
        self.assertNotIn("Jan Man", html)
        self.assertNotIn("Els Vrouw", html)

        # 7. Test gecombineerde filters: digidokter 1 + smartphone
        res = self.client.get(f"/registraties?digidokter={self.digidokter.id}&toestel={toestel_smartphone.id}")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")
        self.assertIn("Sam Onbekend", html)
        self.assertNotIn("Jan Man", html)
        self.assertNotIn("Els Vrouw", html)

        # 8. Test dat inactieve opties NIET in de filter dropdowns verschijnen
        res = self.client.get("/registraties")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")
        self.assertIn(self.device.naam, html)
        self.assertIn("Smartphone", html)
        self.assertNotIn("Oude Faxmachine", html)
        self.assertIn("18-64 jaar", html)
        self.assertNotIn("Antieke Leeftijd", html)
        self.assertIn(self.digidokter.naam, html)
        self.assertNotIn("Inactieve Dokter", html)

    def test_view_registration_shows_classification(self):
        """Test dat op de detailpagina van een registratie de vraagclassificatie, categorie, zekerheid en motivatie getoond worden."""
        from models.question_category import QuestionCategory
        from models.question_classification import QuestionClassification

        # 1. Registratie zonder classificatie
        reg_unclassified = Registration(
            registratienummer="2026-0201",
            datum=date.today(),
            client="Klant Ongeclassificeerd",
            digidokter_id=self.digidokter.id,
            toestel_id=self.device.id,
            leeftijdscategorie_id=self.age_category.id,
            onderwerp="Vraag over router configuratie",
            organisatie_id=self.org.id,
            aangemaakt_door_id=self.admin_user.id
        )
        db.session.add(reg_unclassified)
        db.session.commit()

        res = self.client.get(f"/registraties/{reg_unclassified.id}")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode("utf-8")
        self.assertIn("Vraagclassificatie", html)
        self.assertIn("Nog niet geclassificeerd", html)

        # 2. Registratie met classificatie
        cat = QuestionCategory(naam="Netwerk & Internet", omschrijving="Vragen over wifi, routers, netwerk", actief=True)
        db.session.add(cat)
        db.session.commit()

        reg_classified = Registration(
            registratienummer="2026-0202",
            datum=date.today(),
            client="Klant Geclassificeerd",
            digidokter_id=self.digidokter.id,
            toestel_id=self.device.id,
            leeftijdscategorie_id=self.age_category.id,
            onderwerp="Wifi valt steeds weg op laptop",
            organisatie_id=self.org.id,
            aangemaakt_door_id=self.admin_user.id
        )
        db.session.add(reg_classified)
        db.session.commit()

        classification = QuestionClassification(
            registration_id=reg_classified.id,
            category_id=cat.id,
            zekerheid=0.93,
            toelichting="De vraag betreft wifi-connectiviteit en netwerkproblemen.",
            model_naam="gemini-2.5-flash",
            is_handmatig_aangepast=False
        )
        db.session.add(classification)
        db.session.commit()

        res2 = self.client.get(f"/registraties/{reg_classified.id}")
        self.assertEqual(res2.status_code, 200)
        html2 = res2.data.decode("utf-8")
        self.assertIn("Vraagclassificatie", html2)
        self.assertIn("Netwerk &amp; Internet", html2)
        self.assertIn("93% zekerheid", html2)
        self.assertIn("De vraag betreft wifi-connectiviteit en netwerkproblemen.", html2)
        self.assertIn("Motivatie:", html2)


