import io
from tests.base import BaseTestCase
from extensions import db
from models.app_document import AppFolder, AppDocument
from models.user import User
from models.organisatie import Organisatie, UserOrganisatie
from werkzeug.security import generate_password_hash


class TestAppDocuments(BaseTestCase):
    def setUp(self):
        super().setUp()

        # Maak platformbeheerder aan
        self.platform_admin = User(
            naam="SuperAdmin",
            email="platform@test.com",
            wachtwoord_hash=generate_password_hash("password123"),
            rol="platformbeheerder",
            actief=True,
            moet_wachtwoord_wijzigen=False
        )
        db.session.add(self.platform_admin)

        # Maak medewerker van organisatie 1 aan
        self.medewerker = User(
            naam="MedewerkerJan",
            email="jan@test.com",
            wachtwoord_hash=generate_password_hash("password123"),
            rol="medewerker",
            actief=True,
            moet_wachtwoord_wijzigen=False
        )
        db.session.add(self.medewerker)
        db.session.commit()

        uo = UserOrganisatie(
            user_id=self.medewerker.id,
            organisatie_id=self.org.id,
            rol="medewerker",
            actief=True
        )
        db.session.add(uo)

        # Maak tweede organisatie met eigen gebruiker aan
        self.org2 = Organisatie(naam="Tweede Gemeente", slug="tweede-gemeente", actief=True)
        db.session.add(self.org2)
        db.session.commit()

        self.user_org2 = User(
            naam="LidOrg2",
            email="org2@test.com",
            wachtwoord_hash=generate_password_hash("password123"),
            rol="medewerker",
            actief=True,
            moet_wachtwoord_wijzigen=False
        )
        db.session.add(self.user_org2)
        db.session.commit()

        uo2 = UserOrganisatie(
            user_id=self.user_org2.id,
            organisatie_id=self.org2.id,
            rol="medewerker",
            actief=True
        )
        db.session.add(uo2)
        db.session.commit()

    def test_unauthenticated_redirect(self):
        res = self.client.get('/app-documentatie/')
        self.assertEqual(res.status_code, 302)
        self.assertIn('/login', res.headers['Location'])

    def test_shared_access_and_read_across_organizations(self):
        # 1. Platform admin maakt map en document aan
        folder = AppFolder(naam="Handleidingen", aangemaakt_door_id=self.platform_admin.id)
        db.session.add(folder)
        db.session.commit()

        doc = AppDocument(
            map_id=folder.id,
            bestandsnaam="Gebruikersgids_v1.txt",
            omschrijving="Algemene handleiding voor alle vrijwilligers",
            type="txt",
            mime_type="text/plain",
            bestandsgrootte=25,
            inhoud=b"Dit is de handleiding.",
            tekst_inhoud="Dit is de handleiding.",
            aangemaakt_door_id=self.platform_admin.id
        )
        db.session.add(doc)
        db.session.commit()

        # 2. Medewerker van Org 1 logt in en kan het document zien en downloaden
        self.login("MedewerkerJan", "password123")
        self.select_organisatie(self.org.id)

        res_org1 = self.client.get('/app-documentatie/')
        self.assertEqual(res_org1.status_code, 200)
        self.assertIn(b"Handleidingen", res_org1.data)
        self.assertNotIn(b"Document uploaden", res_org1.data)  # Geen beheerdersknop

        res_folder_org1 = self.client.get(f'/app-documentatie/?map_id={folder.id}')
        self.assertEqual(res_folder_org1.status_code, 200)
        self.assertIn(b"Gebruikersgids_v1.txt", res_folder_org1.data)

        # Download
        res_dl_org1 = self.client.get(f'/app-documentatie/{doc.id}/download')
        self.assertEqual(res_dl_org1.status_code, 200)
        self.assertEqual(res_dl_org1.data, b"Dit is de handleiding.")

        # 3. Gebruiker van Org 2 logt in en kan ditzelfde document ook zien en downloaden
        self.login("LidOrg2", "password123")
        self.select_organisatie(self.org2.id)

        res_org2 = self.client.get(f'/app-documentatie/?map_id={folder.id}')
        self.assertEqual(res_org2.status_code, 200)
        self.assertIn(b"Gebruikersgids_v1.txt", res_org2.data)

        res_dl_org2 = self.client.get(f'/app-documentatie/{doc.id}/download')
        self.assertEqual(res_dl_org2.status_code, 200)
        self.assertEqual(res_dl_org2.data, b"Dit is de handleiding.")

    def test_platform_admin_crud_workflow(self):
        self.login("SuperAdmin", "password123")

        # 1. Map aanmaken
        res_map = self.client.post('/app-documentatie/mappen/nieuw', data={'naam': 'GDPR Documenten'}, follow_redirects=True)
        self.assertEqual(res_map.status_code, 200)
        folder = AppFolder.query.filter_by(naam='GDPR Documenten').first()
        self.assertIsNotNone(folder)

        # 2. Map hernoemen
        res_rename = self.client.post(f'/app-documentatie/mappen/{folder.id}/hernoemen', data={'naam': 'GDPR & Security'}, follow_redirects=True)
        self.assertEqual(res_rename.status_code, 200)
        folder = db.session.get(AppFolder, folder.id)
        self.assertEqual(folder.naam, 'GDPR & Security')

        # 3. Document uploaden
        upload_data = {
            'map_id': str(folder.id),
            'omschrijving': 'Audit rapport privacy',
            'bestand': (io.BytesIO(b"Veiligheidscontrole geslaagd."), 'audit.txt')
        }
        res_upload = self.client.post('/app-documentatie/upload', data=upload_data, content_type='multipart/form-data', follow_redirects=True)
        self.assertEqual(res_upload.status_code, 200)
        doc = AppDocument.query.filter_by(bestandsnaam='audit.txt').first()
        self.assertIsNotNone(doc)
        self.assertEqual(doc.versie, 1)
        self.assertEqual(doc.map_id, folder.id)

        # 4. Document inline bekijken
        res_view = self.client.get(f'/app-documentatie/{doc.id}/bekijken')
        self.assertEqual(res_view.status_code, 200)
        self.assertEqual(res_view.data, b"Veiligheidscontrole geslaagd.")

        # 5. Document bewerken (naam en omschrijving)
        res_edit = self.client.post(f'/app-documentatie/{doc.id}/bewerken', data={
            'bestandsnaam': 'audit_2026.txt',
            'omschrijving': 'Geüpdatete omschrijving'
        }, follow_redirects=True)
        self.assertEqual(res_edit.status_code, 200)
        doc = db.session.get(AppDocument, doc.id)
        self.assertEqual(doc.bestandsnaam, 'audit_2026.txt')
        self.assertEqual(doc.omschrijving, 'Geüpdatete omschrijving')

        # 6. Document overschrijven (nieuwe versie)
        overwrite_data = {
            'bestand': (io.BytesIO(b"Nieuwe inhoud v2"), 'audit_2026.txt')
        }
        res_overwrite = self.client.post(f'/app-documentatie/{doc.id}/overschrijven', data=overwrite_data, content_type='multipart/form-data', follow_redirects=True)
        self.assertEqual(res_overwrite.status_code, 200)
        doc = db.session.get(AppDocument, doc.id)
        self.assertEqual(doc.versie, 2)
        self.assertEqual(doc.inhoud, b"Nieuwe inhoud v2")

        # 7. Zoeken
        res_search = self.client.get('/app-documentatie/?zoek=veiligheidscontrole')
        self.assertEqual(res_search.status_code, 200)

        # 8. Document verwijderen
        res_del_doc = self.client.post(f'/app-documentatie/{doc.id}/verwijderen', follow_redirects=True)
        self.assertEqual(res_del_doc.status_code, 200)
        self.assertIsNone(db.session.get(AppDocument, doc.id))

        # 9. Map verwijderen
        res_del_map = self.client.post(f'/app-documentatie/mappen/{folder.id}/verwijderen', follow_redirects=True)
        self.assertEqual(res_del_map.status_code, 200)
        self.assertIsNone(db.session.get(AppFolder, folder.id))

    def test_non_platform_admin_cannot_mutate(self):
        # Medewerker probeert map aan te maken
        self.login("MedewerkerJan", "password123")
        self.select_organisatie(self.org.id)

        res = self.client.post('/app-documentatie/mappen/nieuw', data={'naam': 'Verboden Map'}, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn("Enkel de platformbeheerder", res.get_data(as_text=True))
        self.assertIsNone(AppFolder.query.filter_by(naam='Verboden Map').first())
