import io
import os
import tempfile
from datetime import date, datetime
import pandas as pd
from tests.base import BaseTestCase
from extensions import db
from models.digidokter import Digidokter
from models.age_category import AgeCategory
from models.device import Device
from models.herkomst import Herkomst
from models.registration import Registration
from utils.import_handler import (
    _parse_nieuwe_klant,
    _parse_geslacht,
    _parse_date,
    _setup_logger,
    verwerk_import,
    KOLOM_MAP,
    VERPLICHTE_KOLOMMEN
)

class TestImportHandler(BaseTestCase):
    def test_parse_nieuwe_klant(self):
        self.assertFalse(_parse_nieuwe_klant(None))
        self.assertFalse(_parse_nieuwe_klant(float('nan')))
        self.assertFalse(_parse_nieuwe_klant("nee"))
        self.assertFalse(_parse_nieuwe_klant("0"))
        self.assertTrue(_parse_nieuwe_klant("1"))
        self.assertTrue(_parse_nieuwe_klant("ja"))
        self.assertTrue(_parse_nieuwe_klant("JA"))
        self.assertTrue(_parse_nieuwe_klant("nieuwe klant"))
        self.assertTrue(_parse_nieuwe_klant("nieuwe bezoeker"))
        self.assertTrue(_parse_nieuwe_klant("true"))
        self.assertTrue(_parse_nieuwe_klant("waar"))

    def test_parse_geslacht(self):
        self.assertIsNone(_parse_geslacht(None))
        self.assertIsNone(_parse_geslacht(float('nan')))
        self.assertIsNone(_parse_geslacht("onbekend"))
        self.assertEqual(_parse_geslacht("man"), "man")
        self.assertEqual(_parse_geslacht("M"), "man")
        self.assertEqual(_parse_geslacht("male"), "man")
        self.assertEqual(_parse_geslacht("vrouw"), "vrouw")
        self.assertEqual(_parse_geslacht("V"), "vrouw")
        self.assertEqual(_parse_geslacht("female"), "vrouw")

    def test_parse_date(self):
        d = date(2026, 5, 10)
        dt = datetime(2026, 5, 10, 14, 30)
        self.assertEqual(_parse_date(d), d)
        self.assertEqual(_parse_date(dt), d)
        self.assertIsNone(_parse_date(None))
        self.assertIsNone(_parse_date(float('nan')))
        self.assertEqual(_parse_date("10/05/2026"), d)
        self.assertEqual(_parse_date("10-05-2026 14:00:00"), d)
        self.assertEqual(_parse_date("2026-05-10"), d)
        self.assertEqual(_parse_date("10.05.2026"), d)
        self.assertIsNone(_parse_date("geen-datum"))

    def test_setup_logger(self):
        with tempfile.NamedTemporaryFile(suffix='.log', delete=False) as f:
            log_path = f.name
        try:
            logger = _setup_logger(log_path)
            logger.info("Test log regel")
            for h in list(logger.handlers):
                h.close()
                logger.removeHandler(h)
            with open(log_path, 'r', encoding='utf-8') as f:
                content = f.read()
            self.assertIn("Test log regel", content)
        finally:
            if os.path.exists(log_path):
                os.remove(log_path)

    def test_verwerk_import_invalid_format(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "test.txt")
            with open(file_path, "w") as f:
                f.write("dummy")
            with self.app.test_request_context():
                with self.client.session_transaction() as sess:
                    sess['organisatie_id'] = self.org.id
                from flask import session
                session['organisatie_id'] = self.org.id

                result = verwerk_import(file_path, "test.txt", tmpdir)
                self.assertIn("Niet-ondersteund bestandsformaat", result['fouten'][0])
                self.assertEqual(result['toegevoegd'], 0)

    def test_verwerk_import_read_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "corrupt.xlsx")
            with open(file_path, "wb") as f:
                f.write(b"not a valid excel file")
            with self.app.test_request_context():
                from flask import session
                session['organisatie_id'] = self.org.id

                result = verwerk_import(file_path, "corrupt.xlsx", tmpdir)
                self.assertTrue(any("Fout bij lezen" in err for err in result['fouten']))
                self.assertEqual(result['toegevoegd'], 0)

    def test_verwerk_import_missing_columns(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "missing.csv")
            df = pd.DataFrame({'datum': ['2026-05-10'], 'client': ['Jan']})
            df.to_csv(csv_path, index=False)

            with self.app.test_request_context():
                from flask import session
                session['organisatie_id'] = self.org.id

                result = verwerk_import(csv_path, "missing.csv", tmpdir)
                self.assertTrue(any("Ontbrekende verplichte kolommen" in err for err in result['fouten']))
                self.assertEqual(result['toegevoegd'], 0)

    def test_verwerk_import_csv_success_and_skips(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "valid.csv")
            data = {
                'datum': ['2026-05-10', 'ongeldig', '2026-05-11', '2026-05-10', '2026-05-12', '2026-05-13'],
                'client': ['Jan Klaassen', 'Piet', '', 'Jan Klaassen', 'Karel', 'Els'],
                'digidokter': ['Dokter Bob', 'Dokter Bob', 'Dokter Bob', 'Dokter Bob', '', 'Dokter Bob'],
                'onderwerp': ['Hulp met e-mail', 'Vraag', 'Vraag', 'Hulp met e-mail', 'Vraag', 'Vraag'],
                'leeftijdscategorie': ['65+', '65+', '65+', '65+', '65+', ''],
                'toestel': ['Laptop', 'Laptop', 'Laptop', 'Laptop', 'Laptop', ''],
                'herkomst': ['Website', 'Flyer', 'Flyer', 'Website', 'Flyer', 'Flyer'],
                'geslacht': ['Man', 'Vrouw', 'Man', 'Man', 'Man', 'Vrouw'],
                'nieuwe klant': ['Ja', 'Nee', 'Nee', 'Ja', 'Nee', 'Nee']
            }
            df = pd.DataFrame(data)
            df.to_csv(csv_path, index=False, encoding='utf-8-sig')

            with self.app.test_request_context():
                from flask import session
                session['organisatie_id'] = self.org.id

                result = verwerk_import(csv_path, "valid.csv", tmpdir)
                self.assertEqual(result['totaal'], 6)
                self.assertEqual(result['toegevoegd'], 1)  # Only first row is fully valid and non-duplicate
                # Row 2: invalid date
                # Row 3: missing client
                # Row 4: duplicate (same datum, client, digidokter)
                # Row 5: missing digidokter
                # Row 6: missing leeftijdscategorie
                self.assertEqual(result['overgeslagen'], 5)

                # Check that created records exist
                reg = Registration.query.filter_by(client='Jan Klaassen', organisatie_id=self.org.id).first()
                self.assertIsNotNone(reg)
                self.assertEqual(reg.onderwerp, 'Hulp met e-mail')
                self.assertTrue(reg.nieuwe_klant)
                self.assertEqual(reg.geslacht.lower(), 'man')

    def test_verwerk_import_xlsx_success(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            xlsx_path = os.path.join(tmpdir, "valid.xlsx")
            data = {
                'datum': ['2026-06-15'],
                'client': ['Marie Curie'],
                'digidokter': ['Dokter Alice'],
                'onderwerp': ['Printers instellen'],
                'leeftijdscategorie': ['50-64'],
                'toestel': ['Tablet'],
                'herkomst': ['Bibliotheek'],
                'geslacht': ['vrouw'],
                'nieuwe klant': ['1']
            }
            df = pd.DataFrame(data)
            df.to_excel(xlsx_path, index=False)

            with self.app.test_request_context():
                from flask import session
                session['organisatie_id'] = self.org.id

                result = verwerk_import(xlsx_path, "valid.xlsx", tmpdir)
                self.assertEqual(result['totaal'], 1)
                self.assertEqual(result['toegevoegd'], 1)

                reg = Registration.query.filter_by(client='Marie Curie', organisatie_id=self.org.id).first()
                self.assertIsNotNone(reg)
                self.assertEqual(reg.onderwerp, 'Printers instellen')
                self.assertEqual(reg.geslacht.lower(), 'vrouw')
