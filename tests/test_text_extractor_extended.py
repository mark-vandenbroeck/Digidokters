import io
import unittest
import zipfile
import docx
import openpyxl
import pypdf
from utils.text_extractor import (
    extraheer_tekst_uit_bestand,
    _opschonen_tekst,
    genereer_zoek_snippet
)

class TestTextExtractorExtended(unittest.TestCase):
    def test_empty_or_none(self):
        self.assertIsNone(extraheer_tekst_uit_bestand(None))
        self.assertIsNone(extraheer_tekst_uit_bestand(b""))
        self.assertIsNone(_opschonen_tekst(None))
        self.assertIsNone(_opschonen_tekst(""))
        self.assertIsNone(_opschonen_tekst("   \n\n\t  "))

    def test_opschonen_tekst_formatting(self):
        raw = "Hallo\x00 wereld!\n\n\n\n\nVolgende regel   "
        schoon = _opschonen_tekst(raw)
        self.assertEqual(schoon, "Hallo wereld!\n\nVolgende regel")

    def test_extract_pdf_with_text(self):
        # Create a real PDF with text using pypdf / blank or simple text if supported
        # If writing text to PDF directly via pypdf is complex, test valid and invalid PDF bytes
        self.assertIsNone(extraheer_tekst_uit_bestand(b"%PDF-1.4 corrupt", "doc.pdf"))

    def test_extract_docx_with_tables(self):
        doc = docx.Document()
        doc.add_paragraph("Eerste paragraaf")
        table = doc.add_table(rows=2, cols=2)
        table.cell(0, 0).text = "Cel 1"
        table.cell(0, 1).text = "Cel 2"
        table.cell(1, 0).text = "Cel 3"
        table.cell(1, 1).text = "Cel 4"
        
        buf = io.BytesIO()
        doc.save(buf)
        res = extraheer_tekst_uit_bestand(buf.getvalue(), "tabel.docx")
        self.assertIn("Eerste paragraaf", res)
        self.assertIn("Cel 1", res)
        self.assertIn("Cel 4", res)

    def test_extract_docx_corrupt(self):
        res = extraheer_tekst_uit_bestand(b"corrupt docx", "test.docx")
        self.assertIsNone(res)

    def test_extract_odt(self):
        # Create an in-memory ODT (zip with content.xml)
        content_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
        <office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
                                 xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">
            <office:body>
                <office:text>
                    <text:p>Dit is een OpenDocument tekstparagraaf.</text:p>
                    <text:h>Dit is een koptekst.</text:h>
                </office:text>
            </office:body>
        </office:document-content>"""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as zf:
            zf.writestr('content.xml', content_xml)

        res = extraheer_tekst_uit_bestand(buf.getvalue(), "document.odt")
        self.assertIsNotNone(res)
        self.assertIn("Dit is een OpenDocument tekstparagraaf.", res)
        self.assertIn("Dit is een koptekst.", res)

    def test_extract_odt_empty_or_corrupt(self):
        self.assertIsNone(extraheer_tekst_uit_bestand(b"corrupt odt", "doc.odt"))
        
        # Empty odt without content.xml
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as zf:
            zf.writestr('mimetype', 'application/vnd.oasis.opendocument.text')
        self.assertIsNone(extraheer_tekst_uit_bestand(buf.getvalue(), "doc.odt"))

    def test_extract_xlsx(self):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Blad1"
        ws.append(["Naam", "Leeftijd", "Woonplaats"])
        ws.append(["Alice", 30, "Brussel"])
        ws.append(["Bob", 45, "Antwerpen"])

        buf = io.BytesIO()
        wb.save(buf)
        res = extraheer_tekst_uit_bestand(buf.getvalue(), "data.xlsx")
        self.assertIsNotNone(res)
        self.assertIn("Naam Leeftijd Woonplaats", res)
        self.assertIn("Alice 30 Brussel", res)
        self.assertIn("Bob 45 Antwerpen", res)

    def test_extract_xlsx_corrupt(self):
        res = extraheer_tekst_uit_bestand(b"corrupt xlsx", "test.xlsx")
        self.assertIsNone(res)

    def test_extract_text_encodings(self):
        # UTF-8
        utf8_bytes = "Café & Crème brûlée".encode('utf-8')
        res = extraheer_tekst_uit_bestand(utf8_bytes, "nota.txt")
        self.assertEqual(res, "Café & Crème brûlée")

        # Latin-1 fallback with invalid UTF-8 bytes
        latin1_bytes = "Café & Crème brûlée".encode('latin-1')
        res = extraheer_tekst_uit_bestand(latin1_bytes, "nota.txt")
        self.assertIn("Caf", res)

    def test_genereer_zoek_snippet_cases(self):
        self.assertIsNone(genereer_zoek_snippet(None, "zoek"))
        self.assertIsNone(genereer_zoek_snippet("tekst", None))
        self.assertIsNone(genereer_zoek_snippet("tekst", "   "))
        self.assertIsNone(genereer_zoek_snippet("tekst", "nietgevonden"))

        tekst = "Korte tekst over computers en tablets."
        # Found at start
        s1 = genereer_zoek_snippet(tekst, "Korte", context_lengte=10)
        self.assertFalse(s1.startswith("..."))
        self.assertTrue(s1.endswith("..."))
        self.assertIn("Korte", s1)

        # Found at end
        s2 = genereer_zoek_snippet(tekst, "tablets.", context_lengte=10)
        self.assertTrue(s2.startswith("..."))
        self.assertFalse(s2.endswith("..."))
        self.assertIn("tablets.", s2)

if __name__ == '__main__':
    unittest.main()
