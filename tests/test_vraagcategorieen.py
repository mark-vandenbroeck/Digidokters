from tests.base import BaseTestCase
from werkzeug.security import generate_password_hash
from extensions import db
from models.user import User
from models.registration import Registration
from models.question_category import QuestionCategory
from models.question_classification import QuestionClassification
from datetime import date


class TestVraagcategorieen(BaseTestCase):
    def setUp(self):
        super().setUp()
        # Maak platformbeheerder gebruiker
        self.platform_admin = User(
            naam="SuperAdmin",
            email="platform@test.com",
            wachtwoord_hash=generate_password_hash("password123"),
            rol="platformbeheerder",
            actief=True,
            moet_wachtwoord_wijzigen=False
        )
        db.session.add(self.platform_admin)
        db.session.commit()

    def test_vraagcategorieen_access_control(self):
        # 1. Niet ingelogd -> redirect login
        res = self.client.get('/platform/vraagcategorieen')
        self.assertEqual(res.status_code, 302)
        self.assertIn('/login', res.headers['Location'])

        # 2. Ingelogd als gewone medewerker -> denied
        self.login("UserTim", "password123")
        self.select_organisatie(self.org.id)
        res = self.client.get('/platform/vraagcategorieen')
        self.assertEqual(res.status_code, 302)
        self.assertIn('/registraties', res.headers['Location'])
        self.logout()

        # 3. Ingelogd als gewone lokale beheerder -> denied
        self.login("AdminMark", "password123")
        self.select_organisatie(self.org.id)
        res = self.client.get('/platform/vraagcategorieen')
        self.assertEqual(res.status_code, 302)
        self.assertIn('/registraties', res.headers['Location'])
        self.logout()

        # 4. Ingelogd als platformbeheerder -> 200 OK
        self.login("SuperAdmin", "password123")
        res = self.client.get('/platform/vraagcategorieen')
        self.assertEqual(res.status_code, 200)
        self.assertIn("Vraagcategorieën", res.data.decode('utf-8'))

    def test_vraagcategorie_crud_lifecycle(self):
        self.login("SuperAdmin", "password123")

        # 1. Aanmaken
        data = {
            'naam': 'Test Categorie AI',
            'omschrijving': 'Vragen over testen en AI analyse.',
            'actief': 'on'
        }
        res = self.client.post('/platform/vraagcategorieen/nieuw', data=data, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn("Test Categorie AI", res.data.decode('utf-8'))

        cat = QuestionCategory.query.filter_by(naam='Test Categorie AI').first()
        self.assertIsNotNone(cat)
        self.assertTrue(cat.actief)

        # 2. Bewerken
        edit_data = {
            'naam': 'Gewijzigde Categorie AI',
            'omschrijving': 'Aangepaste omschrijving.',
            'actief': 'on'
        }
        res = self.client.post(f'/platform/vraagcategorieen/{cat.id}/wijzig', data=edit_data, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn("Gewijzigde Categorie AI", res.data.decode('utf-8'))

        cat_updated = db.session.get(QuestionCategory, cat.id)
        self.assertEqual(cat_updated.naam, 'Gewijzigde Categorie AI')

        # 3. Toggle status
        res = self.client.post(f'/platform/vraagcategorieen/{cat.id}/toggle', follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertFalse(cat_updated.actief)

        # 4. Verwijderen
        res = self.client.post(f'/platform/vraagcategorieen/{cat.id}/verwijderen', follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIsNone(db.session.get(QuestionCategory, cat.id))

    def test_vraagclassificatie_handmatige_override(self):
        self.login("SuperAdmin", "password123")

        # Maak categorie en registratie aan
        cat1 = QuestionCategory(naam="Cat 1", omschrijving="Omschrijving 1", volgorde=1, actief=True)
        cat2 = QuestionCategory(naam="Cat 2", omschrijving="Omschrijving 2", volgorde=2, actief=True)
        db.session.add_all([cat1, cat2])
        db.session.commit()

        reg = Registration(
            registratienummer="2026-0001",
            datum=date(2026, 3, 1),
            client="Klant Test",
            digidokter_id=self.digidokter.id,
            leeftijdscategorie_id=self.age_category.id,
            toestel_id=self.device.id,
            organisatie_id=self.org.id,
            onderwerp="Probleem met bankieren app"
        )
        db.session.add(reg)
        db.session.commit()

        cls = QuestionClassification(
            registration_id=reg.id,
            category_id=cat1.id,
            zekerheid=0.85,
            toelichting="Oorspronkelijke AI toelichting",
            model_naam="gemini-3.5-flash",
            is_handmatig_aangepast=False
        )
        db.session.add(cls)
        db.session.commit()

        # GET formulier controle op aanwezigheid van CSRF token
        get_res = self.client.get(f'/platform/vraagclassificaties/{cls.id}/wijzig')
        self.assertEqual(get_res.status_code, 200)
        self.assertIn('name="csrf_token"', get_res.data.decode('utf-8'))

        # Wijzig handmatig naar cat2
        edit_data = {
            'category_id': cat2.id,
            'toelichting': 'Handmatige correctie door beheerder.'
        }
        res = self.client.post(f'/platform/vraagclassificaties/{cls.id}/wijzig', data=edit_data, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        cls_updated = db.session.get(QuestionClassification, cls.id)
        self.assertEqual(cls_updated.category_id, cat2.id)
        self.assertTrue(cls_updated.is_handmatig_aangepast)
        self.assertEqual(cls_updated.toelichting, 'Handmatige correctie door beheerder.')
        self.assertEqual(cls_updated.aangepast_door_id, self.platform_admin.id)

    def test_statistieken_vragenanalyse_tab(self):
        self.login("AdminMark", "password123")
        self.select_organisatie(self.org.id)

        res = self.client.get('/statistieken')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        self.assertIn('id="questions-tab"', html)
        self.assertIn('id="questions-pane"', html)
        self.assertIn('Vragen & AI-Analyse', html)

    def test_statistieken_behoudt_actieve_tab(self):
        self.login("AdminMark", "password123")
        self.select_organisatie(self.org.id)

        # Tab questions
        res = self.client.get('/statistieken?jaar=2024&tab=questions')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        self.assertIn('<input type="hidden" name="tab" id="activeTabInput" value="questions">', html)
        self.assertIn('id="questions-tab"', html)
        self.assertIn('id="questions-pane" role="tabpanel" aria-labelledby="questions-tab" tabindex="0"', html)
        self.assertTrue('class="nav-link active" id="questions-tab"' in html or 'class="nav-link  active"' in html or 'class="nav-link active "' in html or 'active' in html)

        # Tab volunteers
        res2 = self.client.get('/statistieken?jaar=2025&tab=volunteers')
        self.assertEqual(res2.status_code, 200)
        html2 = res2.data.decode('utf-8')
        self.assertIn('<input type="hidden" name="tab" id="activeTabInput" value="volunteers">', html2)

    def test_statistieken_alle_jaren(self):
        self.login("AdminMark", "password123")
        self.select_organisatie(self.org.id)

        cat = QuestionCategory(naam="TestCategorie", omschrijving="Test omschrijving", volgorde=1, actief=True)
        db.session.add(cat)
        db.session.commit()

        reg = Registration(
            registratienummer="2026-0099",
            datum=date(2026, 3, 1),
            client="Klant Test",
            digidokter_id=self.digidokter.id,
            leeftijdscategorie_id=self.age_category.id,
            toestel_id=self.device.id,
            organisatie_id=self.org.id,
            onderwerp="Probleem met bankieren app"
        )
        db.session.add(reg)
        db.session.commit()

        cls = QuestionClassification(
            registration_id=reg.id,
            category_id=cat.id,
            zekerheid=0.92,
            toelichting="AI motivatie",
            model_naam="gemini-3.5-flash"
        )
        db.session.add(cls)
        db.session.commit()

        res = self.client.get('/statistieken?jaar=alle')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        self.assertIn('<option value="alle" selected>Alle jaren</option>', html)
        self.assertIn('Bezoeken (alle jaren)', html)
        self.assertIn('Gepresteerde uren (alle jaren)', html)
        self.assertIn('id="yearsChart"', html)
        self.assertNotIn('id="weekChart"', html)

        # Controleer ook combinatie met tab
        res_tab = self.client.get('/statistieken?jaar=alle&tab=questions')
        self.assertEqual(res_tab.status_code, 200)
        html_tab = res_tab.data.decode('utf-8')
        self.assertIn('<input type="hidden" name="tab" id="activeTabInput" value="questions">', html_tab)
        self.assertIn('Verdeling per Vraagcategorie (alle jaren)', html_tab)

    def test_asynchrone_classificatie_bij_nieuwe_registratie(self):
        from unittest.mock import patch
        self.app.config['ENABLE_ASYNC_CLASSIFIER_TEST'] = True
        try:
            with patch('utils.ai_classifier.classificeer_enkele_registratie') as mock_classify:
                self.login("AdminMark", "password123")
                self.select_organisatie(self.org.id)

                data = {
                    'datum': '2026-03-15',
                    'client': 'Nieuwe Bezoeker',
                    'digidokter_id': self.digidokter.id,
                    'nieuwe_klant': 'nee',
                    'geslacht': 'vrouw',
                    'onderwerp': 'Probleem met WhatsApp op iPhone',
                    'leeftijdscategorie_id': self.age_category.id,
                    'toestel_id': self.device.id
                }
                res = self.client.post('/registraties/nieuw', data=data, follow_redirects=True)
                self.assertEqual(res.status_code, 200)

                # Controleer of thread is gestart en mock_classify is aangeroepen
                import time
                time.sleep(0.2)
                self.assertTrue(mock_classify.called)
        finally:
            self.app.config['ENABLE_ASYNC_CLASSIFIER_TEST'] = False
