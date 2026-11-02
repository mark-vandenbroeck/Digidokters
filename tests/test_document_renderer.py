import csv
import io
import json
import unittest
from unittest.mock import patch
import zipfile

import docx
import openpyxl

from utils.document_renderer import (
    _bepaal_extensie,
    _render_odt,
    _render_docx,
    _render_excel,
    _render_markdown,
    _render_text_or_code,
    _render_html,
    render_document_preview,
)


class TestDocumentRenderer(unittest.TestCase):
    """Uitgebreide unit tests voor utils/document_renderer.py."""

    # -------------------------------------------------------------------------
    # 1. _bepaal_extensie
    # -------------------------------------------------------------------------
    def test_bepaal_extensie_met_bestandsnaam(self):
        """Test bepalen van de extensie wanneer er een extensie in de bestandsnaam zit."""
        self.assertEqual(_bepaal_extensie("rapport.PDF"), "pdf")
        self.assertEqual(_bepaal_extensie("document.docx"), "docx")
        self.assertEqual(_bepaal_extensie("document.docm"), "docm")
        self.assertEqual(_bepaal_extensie("document.odt"), "odt")
        self.assertEqual(_bepaal_extensie("data.XLSX"), "xlsx")
        self.assertEqual(_bepaal_extensie("data.csv"), "csv")
        self.assertEqual(_bepaal_extensie("data.tsv"), "tsv")
        self.assertEqual(_bepaal_extensie("README.md"), "md")
        self.assertEqual(_bepaal_extensie("pagina.html"), "html")
        self.assertEqual(_bepaal_extensie("foto.png"), "png")
        self.assertEqual(_bepaal_extensie("script.py"), "py")

    def test_bepaal_extensie_fallback_op_mime_type(self):
        """Test bepalen van de extensie op basis van MIME-type wanneer de bestandsnaam geen extensie heeft."""
        self.assertEqual(_bepaal_extensie("bestand_zonder_ext", "application/pdf"), "pdf")
        self.assertEqual(_bepaal_extensie("", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"), "docx")
        self.assertEqual(_bepaal_extensie(None, "application/msword"), "docx")
        self.assertEqual(_bepaal_extensie("doc", "application/vnd.oasis.opendocument.text"), "odt")
        self.assertEqual(_bepaal_extensie("doc", "application/x-odt"), "odt")
        self.assertEqual(_bepaal_extensie("sheet", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"), "xlsx")
        self.assertEqual(_bepaal_extensie("tabel", "text/csv"), "csv")
        self.assertEqual(_bepaal_extensie("notities", "text/markdown"), "md")
        self.assertEqual(_bepaal_extensie("notities", "text/x-md"), "md")
        self.assertEqual(_bepaal_extensie("webpagina", "text/html"), "html")
        self.assertEqual(_bepaal_extensie("afbeelding", "image/jpeg"), "png")
        self.assertEqual(_bepaal_extensie("onbekend", "application/octet-stream"), "txt")
        self.assertEqual(_bepaal_extensie("", ""), "txt")

    # -------------------------------------------------------------------------
    # 2. _render_odt
    # -------------------------------------------------------------------------
    def test_render_odt_success(self):
        """Test succesvol renderen van een ODT-bestand met stijlen, koppen, alinea's, lijsten en tabellen."""
        content_xml = """<?xml version="1.0" encoding="UTF-8"?>
<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
                         xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"
                         xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0"
                         xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0"
                         xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0"
                         xmlns:xlink="http://www.w3.org/1999/xlink">
  <office:body>
    <office:text>
      <text:h text:outline-level="1">Hoofdtitel ODT</text:h>
      <text:h text:outline-level="2">Kop niveau 2</text:h>
      <text:h text:outline-level="3">Kop niveau 3</text:h>
      <text:h text:outline-level="4">Kop niveau 4</text:h>
      <text:h text:outline-level="1">   </text:h>
      <text:p>Dit is gewone tekst met <text:s text:c="4"/>extra spaties, een<text:tab/>tab, een afbreking<text:line-break/>en een <text:a xlink:href="https://digidokters.be">link</text:a>.</text:p>
      <text:p>
        <text:span text:style-name="StijlVet">vetgedrukt</text:span>,
        <text:span text:style-name="StijlCursief">cursief</text:span>,
        <text:span text:style-name="StijlOnderlijnd">onderlijnd</text:span> en
        <text:span text:style-name="StijlDoorstreept">doorstreept</text:span>.
        <text:custom>onbekende tag <text:span text:style-name="StijlVet">diep</text:span></text:custom>staart
      </text:p>
      <text:list>
        <text:list-item><text:p>Eerste opsomming</text:p></text:list-item>
        <text:list-item><text:p>Tweede opsomming</text:p></text:list-item>
      </text:list>
      <table:table>
        <table:table-row>
          <table:table-cell><text:p>Tabelkop A</text:p></table:table-cell>
          <table:table-cell><text:p>Tabelkop B</text:p></table:table-cell>
        </table:table-row>
        <table:table-row>
          <table:table-cell><text:p>Cel 1</text:p></table:table-cell>
          <table:table-cell><text:p>Cel 2</text:p></table:table-cell>
        </table:table-row>
      </table:table>
    </office:text>
  </office:body>
</office:document-content>"""

        styles_xml = """<?xml version="1.0" encoding="UTF-8"?>
<office:document-styles xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
                        xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0"
                        xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0">
  <office:styles>
    <style:style style:name="StijlVet"><style:text-properties fo:font-weight="bold"/></style:style>
    <style:style style:name="StijlCursief"><style:text-properties fo:font-style="italic"/></style:style>
    <style:style style:name="StijlOnderlijnd"><style:text-properties style:text-underline-style="solid"/></style:style>
    <style:style style:name="StijlDoorstreept"><style:text-properties style:text-line-through-style="solid"/></style:style>
  </office:styles>
</office:document-styles>"""

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("content.xml", content_xml)
            zf.writestr("styles.xml", styles_xml)

        res = _render_odt(buf.getvalue())
        self.assertEqual(res["viewer_type"], "word")
        self.assertGreaterEqual(res["paragraph_count"], 7)
        self.assertEqual(res["table_count"], 1)

        html = res["html_content"]
        self.assertIn("docx-h1", html)
        self.assertIn("docx-h2", html)
        self.assertIn("docx-h3", html)
        self.assertIn("docx-h4", html)
        self.assertIn("<strong>vetgedrukt</strong>", html)
        self.assertIn("<em>cursief</em>", html)
        self.assertIn("<u>onderlijnd</u>", html)
        self.assertIn("<del>doorstreept</del>", html)
        self.assertIn('&emsp;', html)
        self.assertIn('<br>', html)
        self.assertIn('href="https://digidokters.be"', html)
        self.assertIn("<ul", html)
        self.assertIn("<table", html)
        self.assertIn("<th", html)
        self.assertIn("<td", html)

    def test_render_odt_geen_office_text(self):
        """Test ODT zonder office:text element."""
        content_xml = """<?xml version="1.0" encoding="UTF-8"?>
<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0">
  <office:body></office:body>
</office:document-content>"""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("content.xml", content_xml)

        res = _render_odt(buf.getvalue())
        self.assertEqual(res["viewer_type"], "word")
        self.assertIn("geen leesbare tekst", res["html_content"])

    def test_render_odt_zonder_content_xml(self):
        """Test ODT-archief waar content.xml ontbreekt."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("dummy.txt", "geen content")

        res = _render_odt(buf.getvalue())
        self.assertEqual(res["viewer_type"], "error")
        self.assertIn("content.xml ontbreekt", res["error_message"])

    def test_render_odt_corrupt_bestand(self):
        """Test ODT met corrupte binaire bytes."""
        res = _render_odt(b"dit is geen geldig zip archief")
        self.assertEqual(res["viewer_type"], "error")
        self.assertIn("Kon ODT-archief niet openen", res["error_message"])

    def test_render_odt_ongeldige_xml(self):
        """Test ODT met corrupte XML in content.xml."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("content.xml", "<office:document-content>ongeldige xml zonder sluiting")

        res = _render_odt(buf.getvalue())
        self.assertEqual(res["viewer_type"], "error")
        self.assertIn("Fout bij verwerken van ODT-inhoud", res["error_message"])

    # -------------------------------------------------------------------------
    # 3. _render_docx
    # -------------------------------------------------------------------------
    def test_render_docx_success(self):
        """Test succesvol renderen van een Word (.docx) document met koppen, stijlen, opmaak en tabellen."""
        doc = docx.Document()
        doc.add_heading("Document Titel", level=0)
        doc.add_heading("Kop Niveau 1", level=1)
        doc.add_heading("Kop Niveau 2", level=2)
        doc.add_heading("Kop Niveau 3", level=3)
        doc.add_heading("Kop Niveau 4", level=4)

        p_list = doc.add_paragraph("Opsommingsitem", style="List Bullet")
        p_quote = doc.add_paragraph("Citaat tekst", style="Quote")

        p_styled = doc.add_paragraph()
        r_empty = p_styled.add_run("")
        r_bold = p_styled.add_run("Vetgedrukt")
        r_bold.bold = True
        r_italic = p_styled.add_run(" Cursief")
        r_italic.italic = True
        r_under = p_styled.add_run(" Onderlijnd")
        r_under.underline = True
        r_strike = p_styled.add_run(" Doorstreept")
        r_strike.font.strike = True

        doc.add_paragraph("")  # lege paragraaf

        tbl = doc.add_table(rows=2, cols=2)
        tbl.rows[0].cells[0].text = "Header 1"
        tbl.rows[0].cells[1].text = "Header 2"
        tbl.rows[1].cells[0].text = "Data 1"
        tbl.rows[1].cells[1].text = "Data 2"

        buf = io.BytesIO()
        doc.save(buf)

        res = _render_docx(buf.getvalue())
        self.assertEqual(res["viewer_type"], "word")
        self.assertGreaterEqual(res["paragraph_count"], 5)
        self.assertEqual(res["table_count"], 1)

        html = res["html_content"]
        self.assertIn("docx-h1", html)
        self.assertIn("docx-h2", html)
        self.assertIn("docx-h3", html)
        self.assertIn("docx-h4", html)
        self.assertIn("docx-li", html)
        self.assertIn("blockquote", html)
        self.assertIn("<strong>Vetgedrukt</strong>", html)
        self.assertIn("<em> Cursief</em>", html)
        self.assertIn("<u> Onderlijnd</u>", html)
        self.assertIn("<del> Doorstreept</del>", html)
        self.assertIn("docx-table", html)
        self.assertIn("Header 1", html)
        self.assertIn("Data 1", html)

    def test_render_docx_leeg_document(self):
        """Test Word document zonder enige alinea's of tabellen."""
        doc = docx.Document()
        buf = io.BytesIO()
        doc.save(buf)

        res = _render_docx(buf.getvalue())
        self.assertEqual(res["viewer_type"], "word")
        self.assertEqual(res["paragraph_count"], 0)
        self.assertIn("geen leesbare tekst", res["html_content"])

    def test_render_docx_corrupt(self):
        """Test Word document met corrupte binaire bytes."""
        res = _render_docx(b"dit is geen geldige docx zip")
        self.assertEqual(res["viewer_type"], "error")
        self.assertIn("Kon Word-document niet inlezen", res["error_message"])

    # -------------------------------------------------------------------------
    # 4. _render_excel
    # -------------------------------------------------------------------------
    def test_render_excel_csv_en_tsv(self):
        """Test CSV (met komma en puntkomma) en TSV bestanden inclusief UTF-8 en Latin-1 fallback."""
        # 1. Puntkomma CSV (UTF-8)
        csv_semicolon = "Naam;Rol;Gemeente\nJan;Digidokter;Londerzeel\nPiet;Beheerder;Gent"
        res_csv = _render_excel(csv_semicolon.encode("utf-8"), "csv")
        self.assertEqual(res_csv["viewer_type"], "excel")
        self.assertEqual(len(res_csv["sheets"]), 1)
        sheet = res_csv["sheets"][0]
        self.assertEqual(sheet["headers"], ["Naam", "Rol", "Gemeente"])
        self.assertEqual(len(sheet["rows"]), 2)
        self.assertEqual(sheet["total_rows"], 3)
        self.assertFalse(sheet["is_truncated"])

        # 2. Komma CSV met Latin-1 karakters (niet-UTF8)
        csv_latin1 = b"Naam,Plaats\r\nRen\xe9,Brussel\r\nFran\xe7ois,Luik"
        res_latin1 = _render_excel(csv_latin1, "csv")
        self.assertEqual(res_latin1["viewer_type"], "excel")
        self.assertEqual(res_latin1["sheets"][0]["headers"], ["Naam", "Plaats"])
        self.assertIn("René", res_latin1["sheets"][0]["rows"][0])

        # 3. TSV (tab-gescheiden)
        tsv_data = "KolomA\tKolomB\r\n1\t2"
        res_tsv = _render_excel(tsv_data.encode("utf-8"), "tsv")
        self.assertEqual(res_tsv["viewer_type"], "excel")
        self.assertEqual(res_tsv["sheets"][0]["headers"], ["KolomA", "KolomB"])

        # 4. Grote CSV met meer dan 500 rijen (truncated)
        grote_csv = "ID;Waarde\n" + "\n".join(f"{i};test" for i in range(505))
        res_groot = _render_excel(grote_csv.encode("utf-8"), "csv")
        self.assertTrue(res_groot["sheets"][0]["is_truncated"])
        self.assertEqual(len(res_groot["sheets"][0]["rows"]), 499)

    def test_render_excel_csv_error(self):
        """Test foutafhandeling bij CSV verwerking."""
        with patch("csv.reader", side_effect=Exception("CSV leesfout")):
            res = _render_excel(b"a,b,c", "csv")
            self.assertEqual(res["viewer_type"], "error")
            self.assertIn("Kon CSV-bestand niet verwerken", res["error_message"])

    def test_render_excel_xlsx(self):
        """Test Excel (.xlsx) werkbladen met meerdere tabbladen, float opmaak en lege cellen."""
        wb = openpyxl.Workbook()
        ws1 = wb.active
        ws1.title = "Blad1"
        ws1.append(["Titel", "Bedrag", "Aantal"])
        ws1.append(["Consultatie", 12.3456, 5])
        ws1.append(["Vrijwilliger", 20.0, None])
        ws1.append([None, None, None])  # lege rij

        ws2 = wb.create_sheet(title="Blad2")
        ws2.append(["Code", "Status"])
        ws2.append(["A1", "Actief"])

        # Leeg blad
        wb.create_sheet(title="LeegBlad")

        buf = io.BytesIO()
        wb.save(buf)

        res = _render_excel(buf.getvalue(), "xlsx")
        self.assertEqual(res["viewer_type"], "excel")
        self.assertEqual(len(res["sheets"]), 2)  # Blad1 en Blad2 (LeegBlad wordt overgeslagen)

        s1 = res["sheets"][0]
        self.assertEqual(s1["name"], "Blad1")
        self.assertEqual(s1["headers"], ["Titel", "Bedrag", "Aantal"])
        self.assertEqual(len(s1["rows"]), 2)

        s2 = res["sheets"][1]
        self.assertEqual(s2["name"], "Blad2")
        self.assertEqual(s2["headers"], ["Code", "Status"])

    def test_render_excel_xlsx_geen_data(self):
        """Test Excel workbook waarin geen enkel blad rijen met inhoud bevat."""
        wb = openpyxl.Workbook()
        ws = wb.active
        # Geen rijen toevoegen
        buf = io.BytesIO()
        wb.save(buf)

        res = _render_excel(buf.getvalue(), "xlsx")
        self.assertEqual(res["viewer_type"], "excel")
        self.assertEqual(len(res["sheets"]), 1)
        self.assertEqual(res["sheets"][0]["name"], "Blad 1")
        self.assertEqual(res["sheets"][0]["total_rows"], 0)

    def test_render_excel_xlsx_corrupt(self):
        """Test Excel met corrupte binaire bytes."""
        res = _render_excel(b"corrupt xlsx bestand", "xlsx")
        self.assertEqual(res["viewer_type"], "error")
        self.assertIn("Kon Excel-spreadsheet niet verwerken", res["error_message"])

    # -------------------------------------------------------------------------
    # 5. _render_markdown
    # -------------------------------------------------------------------------
    def test_render_markdown_success(self):
        """Test Markdown verwerking naar HTML met tabellen, koppen en codeblokken."""
        md_text = """# Hoofdtitel
Dit is **vet** en *cursief*.

| Kolom 1 | Kolom 2 |
|---------|---------|
| A       | B       |

```python
print("Hello world")
```
"""
        res = _render_markdown(md_text.encode("utf-8"))
        self.assertEqual(res["viewer_type"], "markdown")
        self.assertIn("<h1", res["html_content"])
        self.assertIn("<table", res["html_content"])
        self.assertIn("<code", res["html_content"])
        self.assertEqual(res["line_count"], len(md_text.splitlines()))

    def test_render_markdown_latin1_fallback(self):
        """Test Markdown verwerking met niet-UTF8 tekens."""
        md_bytes = b"# Titel met caf\xe9 en cr\xe8me"
        res = _render_markdown(md_bytes)
        self.assertEqual(res["viewer_type"], "markdown")
        self.assertIn("café", res["html_content"])

    def test_render_markdown_error(self):
        """Test foutafhandeling bij Markdown fout."""
        with patch("markdown.markdown", side_effect=Exception("Markdown error")):
            res = _render_markdown(b"# Hallo")
            self.assertEqual(res["viewer_type"], "error")
            self.assertIn("Kon Markdown niet renderen", res["error_message"])

    # -------------------------------------------------------------------------
    # 6. _render_text_or_code
    # -------------------------------------------------------------------------
    def test_render_text_or_code_success(self):
        """Test platte tekst en codebestanden met regelnummering en JSON-formattering."""
        # 1. Platte tekst
        txt = "Regel 1\nRegel 2\nRegel 3"
        res_txt = _render_text_or_code(txt.encode("utf-8"), "txt")
        self.assertEqual(res_txt["viewer_type"], "text")
        self.assertEqual(res_txt["line_count"], 3)
        self.assertEqual(res_txt["lines"], ["Regel 1", "Regel 2", "Regel 3"])

        # 2. Geldige JSON formatting
        json_raw = '{"naam": "Digidokter", "actief": true}'
        res_json = _render_text_or_code(json_raw.encode("utf-8"), "json")
        self.assertEqual(res_json["viewer_type"], "text")
        self.assertIn('  "naam": "Digidokter"', res_json["raw_text"])

        # 3. Ongeldige JSON (moet niet crashen, maar als gewone tekst tonen)
        res_bad_json = _render_text_or_code(b"{geen geldige json:", "json")
        self.assertEqual(res_bad_json["viewer_type"], "text")

        # 4. Latin-1 fallback
        latin1_txt = b"Hallo Ren\xe9"
        res_lat = _render_text_or_code(latin1_txt, "txt")
        self.assertEqual(res_lat["viewer_type"], "text")
        self.assertIn("René", res_lat["raw_text"])

    def test_render_text_or_code_error(self):
        """Test foutafhandeling in _render_text_or_code."""
        mock_bytes = unittest.mock.MagicMock()
        mock_bytes.decode.side_effect = Exception("Decodefout")
        res = _render_text_or_code(mock_bytes, "txt")
        self.assertEqual(res["viewer_type"], "error")
        self.assertIn("Kon tekstbestand niet inlezen", res["error_message"])

    # -------------------------------------------------------------------------
    # 7. _render_html
    # -------------------------------------------------------------------------
    def test_render_html_success(self):
        """Test HTML documenten met UTF-8 en Latin-1 fallback."""
        html_utf8 = "<!DOCTYPE html><html><body><h1>Welkom</h1></body></html>"
        res = _render_html(html_utf8.encode("utf-8"))
        self.assertEqual(res["viewer_type"], "html")
        self.assertEqual(res["ext"], "html")
        self.assertIn("<h1>Welkom</h1>", res["raw_text"])

        # Latin-1 fallback
        html_latin1 = b"<html><body>Caf\xe9</body></html>"
        res_lat = _render_html(html_latin1)
        self.assertEqual(res_lat["viewer_type"], "html")
        self.assertIn("Café", res_lat["raw_text"])

    def test_render_html_error(self):
        """Test foutafhandeling in _render_html."""
        mock_bytes = unittest.mock.MagicMock()
        mock_bytes.decode.side_effect = Exception("HTML decodefout")
        res = _render_html(mock_bytes)
        self.assertEqual(res["viewer_type"], "error")
        self.assertIn("Kon HTML-bestand niet inlezen", res["error_message"])

    # -------------------------------------------------------------------------
    # 8. render_document_preview (Hoofdfunctie)
    # -------------------------------------------------------------------------
    def test_render_document_preview_leeg_bestand(self):
        """Test render_document_preview met lege inhoud."""
        res_empty = render_document_preview(b"", "leeg.txt")
        self.assertEqual(res_empty["viewer_type"], "error")
        self.assertIn("Het bestand is leeg", res_empty["error_message"])

        res_none = render_document_preview(None, "geen.txt")
        self.assertEqual(res_none["viewer_type"], "error")

    def test_render_document_preview_pdf(self):
        """Test PDF bestand."""
        res = render_document_preview(b"%PDF-1.4...", "document.pdf", "application/pdf")
        self.assertEqual(res["viewer_type"], "pdf")
        self.assertEqual(res["ext"], "pdf")

    def test_render_document_preview_afbeeldingen(self):
        """Test diverse afbeeldingsformaten (png, jpg, gif, webp, svg en MIME)."""
        for ext in ["png", "jpg", "jpeg", "gif", "webp", "svg"]:
            res = render_document_preview(b"fake image data", f"afbeelding.{ext}")
            self.assertEqual(res["viewer_type"], "image")

        res_mime = render_document_preview(b"fake image data", "afbeelding_zonder_ext", "image/png")
        self.assertEqual(res_mime["viewer_type"], "image")

    def test_render_document_preview_word_en_odt(self):
        """Test Word en ODT routering via render_document_preview."""
        doc = docx.Document()
        doc.add_paragraph("Test Word")
        buf = io.BytesIO()
        doc.save(buf)

        res_word = render_document_preview(buf.getvalue(), "handleiding.docx")
        self.assertEqual(res_word["viewer_type"], "word")

        # ODT
        buf_odt = io.BytesIO()
        with zipfile.ZipFile(buf_odt, "w") as zf:
            zf.writestr("content.xml", "<office:document-content xmlns:office='urn:oasis:names:tc:opendocument:xmlns:office:1.0'><office:body><office:text><text:p xmlns:text='urn:oasis:names:tc:opendocument:xmlns:text:1.0'>ODT test</text:p></office:text></office:body></office:document-content>")

        res_odt = render_document_preview(buf_odt.getvalue(), "handleiding.odt")
        self.assertEqual(res_odt["viewer_type"], "word")

    def test_render_document_preview_excel_en_csv(self):
        """Test Excel en CSV routering via render_document_preview."""
        res_csv = render_document_preview(b"a,b,c\n1,2,3", "data.csv")
        self.assertEqual(res_csv["viewer_type"], "excel")

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["A", "B"])
        buf = io.BytesIO()
        wb.save(buf)
        res_xlsx = render_document_preview(buf.getvalue(), "data.xlsx")
        self.assertEqual(res_xlsx["viewer_type"], "excel")

    def test_render_document_preview_markdown(self):
        """Test Markdown routering via render_document_preview."""
        res = render_document_preview(b"# Titel", "info.md")
        self.assertEqual(res["viewer_type"], "markdown")

    def test_render_document_preview_html(self):
        """Test HTML routering via render_document_preview."""
        res = render_document_preview(b"<h1>Hallo</h1>", "pagina.html")
        self.assertEqual(res["viewer_type"], "html")

    def test_render_document_preview_tekst_en_code(self):
        """Test Tekst en Code routering via render_document_preview."""
        res_txt = render_document_preview(b"Platte tekst", "notitie.txt")
        self.assertEqual(res_txt["viewer_type"], "text")

        res_py = render_document_preview(b"print(1)", "script.py")
        self.assertEqual(res_py["viewer_type"], "text")

        res_sql = render_document_preview(b"SELECT 1;", "query.sql")
        self.assertEqual(res_sql["viewer_type"], "text")

        res_json = render_document_preview(b'{"key": "value"}', "config.json")
        self.assertEqual(res_json["viewer_type"], "text")

    def test_render_document_preview_onbekend_formaat(self):
        """Test niet-ondersteund formaat via render_document_preview."""
        res = render_document_preview(b"MZ\x90\x00...", "programma.exe", "application/x-msdownload")
        self.assertEqual(res["viewer_type"], "unsupported")
        self.assertIn('Voor bestandstype ".exe" is geen directe browser-viewer beschikbaar', res["error_message"])
