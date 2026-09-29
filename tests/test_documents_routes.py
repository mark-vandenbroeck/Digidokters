import io
from tests.base import BaseTestCase
from extensions import db
from models.document import Folder, Document
from models.organisatie import Organisatie, UserOrganisatie
from models.user import User
from werkzeug.security import generate_password_hash


class TestDocumentsRoutes(BaseTestCase):
    def login_admin(self):
        with self.client.session_transaction() as sess:
            sess['organisatie_id'] = self.org.id
        return self.client.post('/login', data={
            'email': 'admin@test.com',
            'wachtwoord': 'password123'
        }, follow_redirects=True)

    def login_medewerker(self):
        with self.client.session_transaction() as sess:
            sess['organisatie_id'] = self.org.id
        return self.client.post('/login', data={
            'email': 'tim@test.com',
            'wachtwoord': 'password123'
        }, follow_redirects=True)

    def test_documents_index_root_breadcrumbs_and_stats(self):
        """Test documenten rootweergave, breadcrumbs en statistieken."""
        self.login_admin()

        # Maak root document en geneste mappen
        root_folder = Folder(naam="Handleidingen", organisatie_id=self.org.id, aangemaakt_door_id=self.admin_user.id)
        root_doc = Document(
            organisatie_id=self.org.id,
            map_id=None,
            bestandsnaam="Root_Handleiding.pdf",
            type="pdf",
            mime_type="application/pdf",
            bestandsgrootte=1024 * 500,  # 500 KB
            inhoud=b"%PDF-1.4 test root content",
            aangemaakt_door_id=self.admin_user.id
        )
        db.session.add_all([root_folder, root_doc])
        db.session.commit()

        sub_folder = Folder(naam="Senioren", parent_id=root_folder.id, organisatie_id=self.org.id, aangemaakt_door_id=self.admin_user.id)
        sub_doc = Document(
            organisatie_id=self.org.id,
            map_id=root_folder.id,
            bestandsnaam="Handleiding_itsme.pdf",
            type="pdf",
            mime_type="application/pdf",
            bestandsgrootte=1024 * 200,
            inhoud=b"%PDF-1.4 test sub content",
            aangemaakt_door_id=self.admin_user.id
        )
        db.session.add_all([sub_folder, sub_doc])
        db.session.commit()

        # 1. Root weergave (toont root mappen en root documenten)
        res_root = self.client.get('/documenten/')
        self.assertEqual(res_root.status_code, 200)
        self.assertIn("Handleidingen", res_root.get_data(as_text=True))
        self.assertIn("Root_Handleiding.pdf", res_root.get_data(as_text=True))

        # 2. Geneste map bekijken (breadcrumbs en mapinhoud)
        res_sub = self.client.get(f'/documenten/?map_id={root_folder.id}')
        self.assertEqual(res_sub.status_code, 200)
        html = res_sub.get_data(as_text=True)
        self.assertIn("Handleidingen", html)
        self.assertIn("Senioren", html)
        self.assertIn("Handleiding_itsme.pdf", html)

        # 3. Niet-bestaande map opvragen -> waarschuwing en redirect naar root
        res_invalid_folder = self.client.get('/documenten/?map_id=99999', follow_redirects=True)
        self.assertEqual(res_invalid_folder.status_code, 200)
        self.assertIn("gevraagde map werd niet gevonden", res_invalid_folder.get_data(as_text=True).lower())

    def test_folder_crud_and_validation(self):
        """Test toevoegen, hernoemen, valideren en verwijderen van mappen."""
        self.login_admin()

        # 1. Map toevoegen zonder naam -> foutmelding
        res_empty = self.client.post('/documenten/mappen/nieuw', data={'naam': ''}, follow_redirects=True)
        self.assertEqual(res_empty.status_code, 200)
        self.assertIn("vul een mapnaam in", res_empty.get_data(as_text=True).lower())

        # 2. Map toevoegen met ongeldige parent_id -> foutmelding
        res_inv_parent = self.client.post('/documenten/mappen/nieuw', data={'naam': 'Submap', 'parent_id': 99999}, follow_redirects=True)
        self.assertEqual(res_inv_parent.status_code, 200)
        self.assertIn("bovenliggende map niet gevonden", res_inv_parent.get_data(as_text=True).lower())

        # 3. Geldige map toevoegen
        res_add = self.client.post('/documenten/mappen/nieuw', data={'naam': 'Test Map'}, follow_redirects=True)
        self.assertEqual(res_add.status_code, 200)
        self.assertIn("succesvol aangemaakt", res_add.get_data(as_text=True).lower())
        folder = Folder.query.filter_by(naam='Test Map', organisatie_id=self.org.id).first()
        self.assertIsNotNone(folder)

        # 4. Map hernoemen met lege naam -> foutmelding
        res_ren_empty = self.client.post(f'/documenten/mappen/{folder.id}/hernoemen', data={'naam': ''}, follow_redirects=True)
        self.assertIn("mapnaam mag niet leeg zijn", res_ren_empty.get_data(as_text=True).lower())

        # 5. Map hernoemen met geldige naam
        res_ren_ok = self.client.post(f'/documenten/mappen/{folder.id}/hernoemen', data={'naam': 'Hernoemde Map', 'return_to': 'self'}, follow_redirects=True)
        self.assertEqual(res_ren_ok.status_code, 200)
        db.session.refresh(folder)
        self.assertEqual(folder.naam, 'Hernoemde Map')

        # 6. Map verwijderen
        res_del = self.client.post(f'/documenten/mappen/{folder.id}/verwijderen', follow_redirects=True)
        self.assertEqual(res_del.status_code, 200)
        self.assertIn("succesvol verwijderd", res_del.get_data(as_text=True).lower())
        self.assertIsNone(db.session.get(Folder, folder.id))

    def test_document_upload_validation_and_success(self):
        """Test upload validaties (geen bestand, te groot bestand, geldige upload)."""
        self.login_admin()

        # 1. Upload zonder bestand
        res_no_file = self.client.post('/documenten/upload', data={}, follow_redirects=True)
        self.assertIn("geen bestand geselecteerd", res_no_file.get_data(as_text=True).lower())

        # 2. Upload met bestand groter dan 16MB -> Flask / Werkzeug 413
        big_content = b"x" * (16 * 1024 * 1024 + 10)  # >16MB
        res_big = self.client.post('/documenten/upload', data={
            'bestand': (io.BytesIO(big_content), 'groot_bestand.zip')
        }, follow_redirects=True)
        self.assertEqual(res_big.status_code, 413)

        # 3. Succesvolle upload van tekstbestand
        valid_content = "Stappenplan voor digidokters over itsme activatie.".encode('utf-8')
        res_ok = self.client.post('/documenten/upload', data={
            'bestand': (io.BytesIO(valid_content), 'stappenplan.txt'),
            'omschrijving': 'Handige instructies'
        }, follow_redirects=True)
        self.assertEqual(res_ok.status_code, 200)
        self.assertIn("succesvol geüpload", res_ok.get_data(as_text=True).lower())

        doc = Document.query.filter_by(bestandsnaam='stappenplan.txt', organisatie_id=self.org.id).first()
        self.assertIsNotNone(doc)
        self.assertEqual(doc.type, 'txt')
        self.assertEqual(doc.omschrijving, 'Handige instructies')
        self.assertEqual(doc.bestandsgrootte, len(valid_content))
        self.assertIn("itsme activatie", doc.tekst_inhoud)
        self.assertEqual(doc.versie, 1)

    def test_document_download_and_secure_viewing(self):
        """Test downloaden en inline bekijken met Content-Security-Policy sandbox header."""
        self.login_admin()

        # PDF document (veilig voor inline weergave)
        doc_pdf = Document(
            organisatie_id=self.org.id,
            bestandsnaam="test.pdf",
            type="pdf",
            mime_type="application/pdf",
            bestandsgrootte=20,
            inhoud=b"%PDF-1.4 test pdf content",
            aangemaakt_door_id=self.admin_user.id
        )
        # HTML document (onveilig voor directe rendering, moet geforceerd gedownload worden)
        doc_html = Document(
            organisatie_id=self.org.id,
            bestandsnaam="gevaarlijk.html",
            type="html",
            mime_type="text/html",
            bestandsgrootte=25,
            inhoud=b"<script>alert(1)</script>",
            aangemaakt_door_id=self.admin_user.id
        )
        db.session.add_all([doc_pdf, doc_html])
        db.session.commit()

        # 1. Download route
        res_dl = self.client.get(f'/documenten/{doc_pdf.id}/download')
        self.assertEqual(res_dl.status_code, 200)
        self.assertEqual(res_dl.data, b"%PDF-1.4 test pdf content")
        self.assertIn("attachment", res_dl.headers.get('Content-Disposition', ''))

        # 2. Bekijken route voor PDF (laadt document viewer HTML template)
        res_view_pdf = self.client.get(f'/documenten/{doc_pdf.id}/bekijken')
        self.assertEqual(res_view_pdf.status_code, 200)
        self.assertIn("test.pdf", res_view_pdf.get_data(as_text=True))
        self.assertIn("iframe", res_view_pdf.get_data(as_text=True))

        # 3. Raw bekijken route voor PDF (inline stream met CSP sandbox)
        res_raw_pdf = self.client.get(f'/documenten/{doc_pdf.id}/bekijken?raw=1')
        self.assertEqual(res_raw_pdf.status_code, 200)
        self.assertEqual(res_raw_pdf.data, b"%PDF-1.4 test pdf content")
        self.assertIn("sandbox", res_raw_pdf.headers.get('Content-Security-Policy', ''))
        self.assertNotIn("attachment", res_raw_pdf.headers.get('Content-Disposition', ''))

        # 4. Raw bekijken route voor onveilige HTML (moet attachment forceren)
        res_raw_html = self.client.get(f'/documenten/{doc_html.id}/bekijken?raw=1')
        self.assertEqual(res_raw_html.status_code, 200)
        self.assertIn("attachment", res_raw_html.headers.get('Content-Disposition', ''))

    def test_document_overwrite_and_edit_and_delete(self):
        """Test overschrijven (versie bump), bewerken van metagegevens en verwijderen van documenten."""
        self.login_admin()

        doc = Document(
            organisatie_id=self.org.id,
            bestandsnaam="v1_bestand.txt",
            type="txt",
            mime_type="text/plain",
            bestandsgrootte=10,
            inhoud=b"Versie 1",
            versie=1,
            aangemaakt_door_id=self.admin_user.id
        )
        db.session.add(doc)
        db.session.commit()

        # 1. Overschrijven met nieuw bestand
        nieuw_content = b"Versie 2 bijgewerkt"
        res_over = self.client.post(f'/documenten/{doc.id}/overschrijven', data={
            'bestand': (io.BytesIO(nieuw_content), 'v2_bestand.txt')
        }, follow_redirects=True)
        self.assertEqual(res_over.status_code, 200)
        self.assertIn("v2", res_over.get_data(as_text=True))

        db.session.refresh(doc)
        self.assertEqual(doc.bestandsnaam, 'v2_bestand.txt')
        self.assertEqual(doc.inhoud, nieuw_content)
        self.assertEqual(doc.versie, 2)
        self.assertEqual(doc.gewijzigd_door_id, self.admin_user.id)

        # 2. Metagegevens bewerken
        res_edit = self.client.post(f'/documenten/{doc.id}/bewerken', data={
            'bestandsnaam': 'document_definitief.txt',
            'omschrijving': 'Bijgewerkte definitieve versie'
        }, follow_redirects=True)
        self.assertEqual(res_edit.status_code, 200)
        db.session.refresh(doc)
        self.assertEqual(doc.bestandsnaam, 'document_definitief.txt')
        self.assertEqual(doc.omschrijving, 'Bijgewerkte definitieve versie')

        # 3. Document verwijderen
        res_del = self.client.post(f'/documenten/{doc.id}/verwijderen', follow_redirects=True)
        self.assertEqual(res_del.status_code, 200)
        self.assertIn("verwijderd", res_del.get_data(as_text=True).lower())
        self.assertIsNone(db.session.get(Document, doc.id))

    def test_documents_cross_tenant_isolation_and_lezer_permissions(self):
        """Test dat een gebruiker van Org 1 geen documenten/mappen van Org 2 kan openen en lezer geen schrijfrechten heeft."""
        org2 = Organisatie(naam="Org Twee", slug="org-twee", actief=True)
        db.session.add(org2)
        db.session.commit()

        user_org2 = User(naam="UserOrg2", email="org2@test.com", wachtwoord_hash="hash", rol="beheerder", actief=True)
        db.session.add(user_org2)
        db.session.commit()

        folder_org2 = Folder(naam="Geheime Map Org 2", organisatie_id=org2.id, aangemaakt_door_id=user_org2.id)
        doc_org2 = Document(
            organisatie_id=org2.id,
            bestandsnaam="geheim_org2.txt",
            type="txt",
            mime_type="text/plain",
            bestandsgrootte=10,
            inhoud=b"Geheim Org2",
            aangemaakt_door_id=user_org2.id
        )
        db.session.add_all([folder_org2, doc_org2])
        db.session.commit()

        self.login_admin()

        # 1. Org 1 probeert document van Org 2 te downloaden -> 404
        res_dl = self.client.get(f'/documenten/{doc_org2.id}/download')
        self.assertEqual(res_dl.status_code, 404)

        # 2. Org 1 probeert map van Org 2 te hernoemen -> 404
        res_ren = self.client.post(f'/documenten/mappen/{folder_org2.id}/hernoemen', data={'naam': 'Hack'})
        self.assertEqual(res_ren.status_code, 404)

        # 3. Org 1 probeert document van Org 2 te bewerken of verwijderen -> 404
        res_edit = self.client.post(f'/documenten/{doc_org2.id}/bewerken', data={'bestandsnaam': 'Hack.txt'})
        self.assertEqual(res_edit.status_code, 404)

        res_del = self.client.post(f'/documenten/{doc_org2.id}/verwijderen')
        self.assertEqual(res_del.status_code, 404)

        # 4. Lezer gebruiker mag geen documenten uploaden of mappen aanmaken
        self.logout()
        lezer = User(
            naam="UserLezerDoc",
            email="lezerdoc@test.com",
            wachtwoord_hash=generate_password_hash("pass"),
            rol="lezer",
            actief=True
        )
        db.session.add(lezer)
        db.session.commit()
        db.session.add(UserOrganisatie(user_id=lezer.id, organisatie_id=self.org.id, rol="lezer", actief=True))
        db.session.commit()

        with self.client.session_transaction() as sess:
            sess['organisatie_id'] = self.org.id
        self.client.post('/login', data={'email': 'lezerdoc@test.com', 'wachtwoord': 'pass'}, follow_redirects=True)

        res_lezer_upload = self.client.post('/documenten/upload', data={}, follow_redirects=True)
        self.assertIn("geen schrijfrechten", res_lezer_upload.get_data(as_text=True).lower())

    def test_rich_document_viewers(self):
        """Test the in-browser viewer for Word (.docx), Excel (.xlsx), Markdown (.md), and CSV."""
        self.login_admin()
        import docx
        import openpyxl

        # 1. Word Document (.docx)
        doc_obj = docx.Document()
        doc_obj.add_heading("Digidokters Verslag", level=1)
        doc_obj.add_paragraph("Dit is een test paragraaf in Word formaat.")
        docx_io = io.BytesIO()
        doc_obj.save(docx_io)
        docx_bytes = docx_io.getvalue()

        doc_word = Document(
            organisatie_id=self.org.id,
            bestandsnaam="verslag.docx",
            type="docx",
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            bestandsgrootte=len(docx_bytes),
            inhoud=docx_bytes,
            aangemaakt_door_id=self.admin_user.id
        )

        # 2. Excel Spreadsheet (.xlsx)
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Overzicht"
        ws.append(["ID", "Naam", "Aantal"])
        ws.append([1, "Mark", 42])
        xlsx_io = io.BytesIO()
        wb.save(xlsx_io)
        xlsx_bytes = xlsx_io.getvalue()

        doc_excel = Document(
            organisatie_id=self.org.id,
            bestandsnaam="statistieken.xlsx",
            type="xlsx",
            mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            bestandsgrootte=len(xlsx_bytes),
            inhoud=xlsx_bytes,
            aangemaakt_door_id=self.admin_user.id
        )

        # 3. Markdown (.md)
        md_bytes = b"# Handleiding Digidokters\n\n- Punt 1\n- Punt 2\n\n**Belangrijk:** Altijd testen!"
        doc_md = Document(
            organisatie_id=self.org.id,
            bestandsnaam="handleiding.md",
            type="md",
            mime_type="text/markdown",
            bestandsgrootte=len(md_bytes),
            inhoud=md_bytes,
            aangemaakt_door_id=self.admin_user.id
        )

        # 4. CSV (.csv)
        csv_bytes = b"Datum,Gebruiker,Status\n2026-09-29,Mark,Actief\n2026-09-30,Jan,Inactief"
        doc_csv = Document(
            organisatie_id=self.org.id,
            bestandsnaam="export.csv",
            type="csv",
            mime_type="text/csv",
            bestandsgrootte=len(csv_bytes),
            inhoud=csv_bytes,
            aangemaakt_door_id=self.admin_user.id
        )

        # 5. OpenDocument Tekst (.odt)
        import zipfile
        odt_io = io.BytesIO()
        with zipfile.ZipFile(odt_io, 'w') as zf:
            content_xml = '''<?xml version="1.0" encoding="UTF-8"?>
            <office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
                                     xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"
                                     xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0"
                                     xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0"
                                     xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0">
              <office:automatic-styles>
                <style:style style:name="T1" style:family="text">
                  <style:text-properties fo:font-weight="bold"/>
                </style:style>
              </office:automatic-styles>
              <office:body>
                <office:text>
                  <text:h text:outline-level="1">OpenDocument Notulen</text:h>
                  <text:p>Dit is een <text:span text:style-name="T1">belangrijke</text:span> ODT alinea.</text:p>
                  <text:list>
                    <text:list-item><text:p>ODT Actiepunt 1</text:p></text:list-item>
                  </text:list>
                </office:text>
              </office:body>
            </office:document-content>'''
            zf.writestr('content.xml', content_xml.encode('utf-8'))
        odt_bytes = odt_io.getvalue()

        doc_odt = Document(
            organisatie_id=self.org.id,
            bestandsnaam="notulen.odt",
            type="odt",
            mime_type="application/vnd.oasis.opendocument.text",
            bestandsgrootte=len(odt_bytes),
            inhoud=odt_bytes,
            aangemaakt_door_id=self.admin_user.id
        )

        db.session.add_all([doc_word, doc_excel, doc_md, doc_csv, doc_odt])
        db.session.commit()

        # Test Word Viewer
        res_word = self.client.get(f'/documenten/{doc_word.id}/bekijken')
        self.assertEqual(res_word.status_code, 200)
        word_html = res_word.get_data(as_text=True)
        self.assertIn("Digidokters Verslag", word_html)
        self.assertIn("Dit is een test paragraaf in Word formaat.", word_html)
        self.assertIn("docx-paper", word_html)

        # Test Excel Viewer
        res_excel = self.client.get(f'/documenten/{doc_excel.id}/bekijken')
        self.assertEqual(res_excel.status_code, 200)
        excel_html = res_excel.get_data(as_text=True)
        self.assertIn("Overzicht", excel_html)
        self.assertIn("Mark", excel_html)
        self.assertIn("excel-container", excel_html)

        # Test Markdown Viewer
        res_md = self.client.get(f'/documenten/{doc_md.id}/bekijken')
        self.assertEqual(res_md.status_code, 200)
        md_html = res_md.get_data(as_text=True)
        self.assertIn("Handleiding Digidokters", md_html)
        self.assertIn("<strong>Belangrijk:</strong>", md_html)
        self.assertIn("markdown-paper", md_html)

        # Test CSV Viewer
        res_csv = self.client.get(f'/documenten/{doc_csv.id}/bekijken')
        self.assertEqual(res_csv.status_code, 200)
        csv_html = res_csv.get_data(as_text=True)
        self.assertIn("Gebruiker", csv_html)
        self.assertIn("Actief", csv_html)

        # Test ODT Viewer
        res_odt = self.client.get(f'/documenten/{doc_odt.id}/bekijken')
        self.assertEqual(res_odt.status_code, 200)
        odt_html = res_odt.get_data(as_text=True)
        self.assertIn("OpenDocument Notulen", odt_html)
        self.assertIn("<strong>belangrijke</strong>", odt_html)
        self.assertIn("ODT Actiepunt 1", odt_html)
        self.assertIn("docx-paper", odt_html)
