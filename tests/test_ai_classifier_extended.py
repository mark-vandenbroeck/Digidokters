import os
import json
from unittest.mock import patch, MagicMock
from tests.base import BaseTestCase
from extensions import db
from models.question_category import QuestionCategory
from models.question_classification import QuestionClassification
from models.registration import Registration
from models.digidokter import Digidokter
from models.age_category import AgeCategory
from models.device import Device
from datetime import date
import requests
from utils.ai_classifier import (
    seed_standaard_categorieen,
    classificeer_vragen_batch,
    seed_retroactieve_classificaties,
    classificeer_enkele_registratie,
    trigger_asynchrone_classificatie,
    get_batch_status,
    trigger_asynchrone_batch_analyse,
    STANDAARD_CATEGORIEEN,
    _batch_lock,
    _batch_status
)

class TestAiClassifierExtended(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.dd = Digidokter(naam="Dokter AI", actief=True, organisatie_id=self.org.id)
        self.age = AgeCategory(naam="65+", actief=True, organisatie_id=self.org.id)
        self.device = Device(naam="Smartphone", actief=True, organisatie_id=self.org.id)
        db.session.add_all([self.dd, self.age, self.device])
        db.session.commit()

    def test_seed_standaard_categorieen(self):
        # First seed should add categories
        added = seed_standaard_categorieen()
        self.assertGreater(added, 0)

        # Second seed should be idempotent
        added_second = seed_standaard_categorieen()
        self.assertEqual(added_second, 0)
        self.assertEqual(QuestionCategory.query.count(), len(STANDAARD_CATEGORIEEN))

    def test_classificeer_vragen_batch_empty_and_no_key(self):
        self.assertEqual(classificeer_vragen_batch([]), [])

        with patch.dict(os.environ, {'GEMINI_API_KEY': ''}):
            with self.assertRaises(ValueError):
                classificeer_vragen_batch([{'id': 1, 'tekst': 'Vraag'}])

    def test_classificeer_vragen_batch_success(self):
        seed_standaard_categorieen()
        cat = QuestionCategory.query.first()

        mock_payload = [
            {
                "id": 10,
                "categorie": cat.naam,
                "zekerheid": 0.95,
                "toelichting": "Duidelijke vraag over itsme"
            }
        ]

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            'candidates': [{
                'content': {
                    'parts': [{'text': f"```json\n{json.dumps(mock_payload)}\n```"}]
                }
            }]
        }

        with patch.dict(os.environ, {'GEMINI_API_KEY': 'dummy-key'}):
            with patch('requests.post', return_value=mock_resp):
                res = classificeer_vragen_batch([{'id': 10, 'tekst': 'Hoe installeer ik itsme?'}])
                self.assertEqual(len(res), 1)
                self.assertEqual(res[0]['registration_id'], 10)
                self.assertEqual(res[0]['category_id'], cat.id)
                self.assertEqual(res[0]['zekerheid'], 0.95)
                self.assertEqual(res[0]['toelichting'], "Duidelijke vraag over itsme")

    def test_classificeer_vragen_batch_retry_and_all_fail(self):
        seed_standaard_categorieen()

        # Test retry: first 503, second 200
        resp_503 = MagicMock()
        resp_503.status_code = 503
        resp_503.text = "Service unavailable"

        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.json.return_value = {
            'candidates': [{
                'content': {
                    'parts': [{'text': json.dumps([{"id": 1, "categorie": STANDAARD_CATEGORIEEN[0]["naam"], "zekerheid": 0.9, "toelichting": "ok"}])}]
                }
            }]
        }

        with patch.dict(os.environ, {'GEMINI_API_KEY': 'dummy-key'}):
            with patch('requests.post', side_effect=[resp_503, resp_200]):
                res = classificeer_vragen_batch([{'id': 1, 'tekst': 'Vraag'}])
                self.assertEqual(len(res), 1)

            # Test all fail
            with patch('requests.post', side_effect=requests.exceptions.RequestException("Timeout")):
                with self.assertRaises(Exception) as ctx:
                    classificeer_vragen_batch([{'id': 1, 'tekst': 'Vraag'}])
                self.assertIn("Alle Gemini modellen faalden", str(ctx.exception))

    def test_seed_retroactieve_classificaties_and_enkele(self):
        seed_standaard_categorieen()
        cat = QuestionCategory.query.first()

        # Maak 2 registraties zonder classificatie
        r1 = Registration(
            registratienummer="2026-9001",
            datum=date(2026, 7, 1),
            client="Klant 1",
            onderwerp="Probleem met printer",
            digidokter_id=self.dd.id,
            leeftijdscategorie_id=self.age.id,
            toestel_id=self.device.id,
            organisatie_id=self.org.id
        )
        r2 = Registration(
            registratienummer="2026-9002",
            datum=date(2026, 7, 2),
            client="Klant 2",
            onderwerp="Probleem met WhatsApp",
            digidokter_id=self.dd.id,
            leeftijdscategorie_id=self.age.id,
            toestel_id=self.device.id,
            organisatie_id=self.org.id
        )
        db.session.add_all([r1, r2])
        db.session.commit()

        mock_results = [
            {'registration_id': r1.id, 'category_id': cat.id, 'categorie_naam': cat.naam, 'zekerheid': 0.88, 'toelichting': 'Printer', 'model_naam': 'gemini-3.5-flash'},
            {'registration_id': r2.id, 'category_id': cat.id, 'categorie_naam': cat.naam, 'zekerheid': 0.92, 'toelichting': 'WhatsApp', 'model_naam': 'gemini-3.5-flash'}
        ]

        progress_calls = []
        def on_progress(done, total, errors):
            progress_calls.append((done, total, errors))

        with patch('utils.ai_classifier.classificeer_vragen_batch', return_value=mock_results):
            verwerkt, fouten = seed_retroactieve_classificaties(batch_size=2, progress_callback=on_progress)
            self.assertEqual(verwerkt, 2)
            self.assertEqual(fouten, 0)
            self.assertTrue(len(progress_calls) > 0)

            # Check DB
            cls1 = QuestionClassification.query.filter_by(registration_id=r1.id).first()
            self.assertIsNotNone(cls1)
            self.assertEqual(cls1.category_id, cat.id)

        # Test classify single registration
        with patch('utils.ai_classifier.classificeer_vragen_batch', return_value=[mock_results[0]]):
            cls_single = classificeer_enkele_registratie(r1.id)
            self.assertIsNotNone(cls_single)
            self.assertEqual(cls_single.registration_id, r1.id)

        # Single with non-existing ID or empty onderwerp
        self.assertIsNone(classificeer_enkele_registratie(999999))
        r1.onderwerp = ""
        db.session.commit()
        self.assertIsNone(classificeer_enkele_registratie(r1.id))

    def test_classificeer_vragen_batch_no_categories_and_http_error(self):
        # Empty categories in DB should trigger auto-seed
        QuestionCategory.query.delete()
        db.session.commit()

        mock_payload = [{"id": 1, "categorie": "Overig / Niet-digitaal", "zekerheid": 0.8, "toelichting": "test"}]
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            'candidates': [{'content': {'parts': [{'text': json.dumps(mock_payload)}]}}]
        }

        with patch.dict(os.environ, {'GEMINI_API_KEY': 'dummy-key'}):
            with patch('requests.post', return_value=mock_resp):
                res = classificeer_vragen_batch([{'id': 1, 'tekst': 'Vraag'}])
                self.assertEqual(len(res), 1)

            # Test 500 error from API
            resp_500 = MagicMock()
            resp_500.status_code = 500
            resp_500.text = "Internal Server Error"
            with patch('requests.post', return_value=resp_500):
                with self.assertRaises(Exception) as ctx:
                    classificeer_vragen_batch([{'id': 1, 'tekst': 'Vraag'}])
                self.assertIn("Gemini API fout (500)", str(ctx.exception))

    def test_seed_retroactieve_classificaties_edge_cases(self):
        # No registrations to classify
        Registration.query.delete()
        QuestionClassification.query.delete()
        db.session.commit()
        verwerkt, fouten = seed_retroactieve_classificaties()
        self.assertEqual((verwerkt, fouten), (0, 0))

        # Create registration with existing classification to test update
        cat = QuestionCategory.query.first()
        r = Registration(
            registratienummer="2026-9099",
            datum=date(2026, 7, 1),
            client="Klant X",
            onderwerp="Probleem",
            digidokter_id=self.dd.id,
            leeftijdscategorie_id=self.age.id,
            toestel_id=self.device.id,
            organisatie_id=self.org.id
        )
        db.session.add(r)
        db.session.commit()

        # Existing classification
        cls_old = QuestionClassification(
            registration_id=r.id,
            category_id=cat.id,
            zekerheid=0.5,
            toelichting="Oud",
            is_handmatig_aangepast=False
        )
        db.session.add(cls_old)
        db.session.commit()

        # Test single classification update
        mock_res = [{'registration_id': r.id, 'category_id': cat.id, 'categorie_naam': cat.naam, 'zekerheid': 0.99, 'toelichting': 'Nieuw', 'model_naam': 'm'}]
        with patch('utils.ai_classifier.classificeer_vragen_batch', return_value=mock_res):
            cls_updated = classificeer_enkele_registratie(r.id)
            self.assertEqual(cls_updated.zekerheid, 0.99)
            self.assertEqual(cls_updated.toelichting, 'Nieuw')

        # Test error during seed_retroactieve_classificaties
        QuestionClassification.query.delete()
        db.session.commit()
        with patch('utils.ai_classifier.classificeer_vragen_batch', side_effect=Exception("API failure")):
            verwerkt, fouten = seed_retroactieve_classificaties(batch_size=1)
            self.assertEqual(verwerkt, 0)
            self.assertEqual(fouten, 1)

    def test_asynchrone_triggers_and_batch_status(self):
        # Test trigger_asynchrone_classificatie when disabled in TESTING
        t_disabled = trigger_asynchrone_classificatie(1, app=self.app)
        self.assertIsNone(t_disabled)

        # Test trigger_asynchrone_classificatie when enabled
        with patch.dict(self.app.config, {'ENABLE_ASYNC_CLASSIFIER_TEST': True}):
            with patch('threading.Thread.start') as mock_tstart:
                t_enabled = trigger_asynchrone_classificatie(1, app=self.app)
                self.assertIsNotNone(t_enabled)
                mock_tstart.assert_called_once()

        # Test get_batch_status
        status = get_batch_status()
        self.assertIn('is_running', status)
        self.assertIn('total', status)

        # Test trigger_asynchrone_batch_analyse when already running
        with _batch_lock:
            _batch_status['is_running'] = True
        try:
            started, msg = trigger_asynchrone_batch_analyse(app=self.app)
            self.assertFalse(started)
            self.assertIn("al een batch-analyse actief", msg)
        finally:
            with _batch_lock:
                _batch_status['is_running'] = False

        # Test trigger_asynchrone_batch_analyse execution of background worker
        with patch('utils.ai_classifier.seed_retroactieve_classificaties', return_value=(5, 0)):
            # Run without threading to test _async_batch_worker logic directly
            started, msg = trigger_asynchrone_batch_analyse(app=self.app)
            self.assertTrue(started)
        with _batch_lock:
            _batch_status['is_running'] = False
