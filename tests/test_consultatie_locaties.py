from tests.base import BaseTestCase
from extensions import db
from models.location import Location
from models.registration import Registration
from datetime import date

class ConsultatieLocatiesTestCase(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.login('admin@test.com', 'password123')

    def test_admin_location_consultaties_flag(self):
        """Test dat de vlag 'Gebruikt voor consultaties' ingesteld en gewijzigd kan worden."""
        # 1. Voeg een nieuwe locatie toe met de vlag aangevinkt
        resp = self.client.post('/beheer/locaties/nieuw', data={
            'naam': 'Bibliotheek Centrum',
            'gebruikt_voor_consultaties': 'on'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Bibliotheek Centrum', resp.data)
        self.assertIn(b'Voor consultaties', resp.data)

        loc = Location.query.filter_by(naam='Bibliotheek Centrum').first()
        self.assertIsNotNone(loc)
        self.assertTrue(loc.gebruikt_voor_consultaties)

        # 2. Wijzig de locatie en vink de vlag uit
        resp = self.client.post(f'/beheer/locaties/{loc.id}/wijzig', data={
            'naam': 'Bibliotheek Centrum',
            'actief': 'on'
            # gebruikt_voor_consultaties niet meegestuurd -> False
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        db.session.refresh(loc)
        self.assertFalse(loc.gebruikt_voor_consultaties)

    def test_registration_without_consultatie_locaties(self):
        """Indien er 0 consultatielocaties zijn, wordt het veld niet getoond en is locatie_id None."""
        # Zorg dat er geen locaties zijn met gebruikt_voor_consultaties=True
        Location.query.filter_by(organisatie_id=self.org.id).delete()
        db.session.commit()

        # GET op registratie toevoegen
        resp = self.client.get('/registraties/nieuw')
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(b'name="locatie_id"', resp.data)

        # POST registratie
        resp = self.client.post('/registraties/nieuw', data={
            'datum': str(date.today()),
            'digidokter_id': self.digidokter.id,
            'client': 'Jan',
            'nieuwe_klant': 'ja',
            'onderwerp': 'Vraag over e-mail',
            'leeftijdscategorie_id': self.age_category.id,
            'toestel_id': self.device.id
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        reg = Registration.query.filter_by(client='Jan').first()
        self.assertIsNotNone(reg)
        self.assertIsNone(reg.locatie_id)

    def test_registration_with_single_consultatie_locatie_auto_assigned(self):
        """Indien er exact 1 consultatielocatie is, wordt het veld niet getoond en automatisch toegekend."""
        loc1 = Location(naam='Bib Londerzeel', actief=True, volgorde=1, gebruikt_voor_consultaties=True, organisatie_id=self.org.id)
        db.session.add(loc1)
        db.session.commit()

        # GET op registratie toevoegen
        resp = self.client.get('/registraties/nieuw')
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(b'name="locatie_id"', resp.data)

        # POST registratie zonder expliciete locatie_id
        resp = self.client.post('/registraties/nieuw', data={
            'datum': str(date.today()),
            'digidokter_id': self.digidokter.id,
            'client': 'Piet',
            'nieuwe_klant': 'nee',
            'onderwerp': 'Hulp bij updates',
            'leeftijdscategorie_id': self.age_category.id,
            'toestel_id': self.device.id
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        reg = Registration.query.filter_by(client='Piet').first()
        self.assertIsNotNone(reg)
        self.assertEqual(reg.locatie_id, loc1.id)
        self.assertEqual(reg.locatie.naam, 'Bib Londerzeel')

    def test_registration_with_multiple_consultatie_locaties(self):
        """Indien er meer dan 1 consultatielocatie is, is het veld zichtbaar en verplicht."""
        loc1 = Location(naam='Bib Centrum', actief=True, volgorde=1, gebruikt_voor_consultaties=True, organisatie_id=self.org.id)
        loc2 = Location(naam='Buurthuis Noord', actief=True, volgorde=2, gebruikt_voor_consultaties=True, organisatie_id=self.org.id)
        db.session.add_all([loc1, loc2])
        db.session.commit()

        # GET toevoegen toont dropdown met beide locaties
        resp = self.client.get('/registraties/nieuw')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'name="locatie_id"', resp.data)
        self.assertIn(b'Bib Centrum', resp.data)
        self.assertIn(b'Buurthuis Noord', resp.data)

        # POST zonder locatie_id levert validatiefout op
        resp = self.client.post('/registraties/nieuw', data={
            'datum': str(date.today()),
            'digidokter_id': self.digidokter.id,
            'client': 'Anna',
            'nieuwe_klant': 'ja',
            'onderwerp': 'Smartphone cursus',
            'leeftijdscategorie_id': self.age_category.id,
            'toestel_id': self.device.id,
            'locatie_id': ''
        }, follow_redirects=True)
        self.assertIn(b'Locatie is verplicht.', resp.data)

        # POST met geldige locatie_id slaagt
        resp = self.client.post('/registraties/nieuw', data={
            'datum': str(date.today()),
            'digidokter_id': self.digidokter.id,
            'client': 'Anna',
            'nieuwe_klant': 'ja',
            'onderwerp': 'Smartphone cursus',
            'leeftijdscategorie_id': self.age_category.id,
            'toestel_id': self.device.id,
            'locatie_id': str(loc2.id)
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        reg = Registration.query.filter_by(client='Anna').first()
        self.assertIsNotNone(reg)
        self.assertEqual(reg.locatie_id, loc2.id)

        # Bekijken toont locatie
        view_resp = self.client.get(f'/registraties/{reg.id}')
        self.assertEqual(view_resp.status_code, 200)
        self.assertIn(b'Buurthuis Noord', view_resp.data)

        # Wijzigen naar loc1
        resp = self.client.post(f'/registraties/{reg.id}/wijzig', data={
            'datum': str(reg.datum),
            'digidokter_id': self.digidokter.id,
            'client': 'Anna',
            'nieuwe_klant': 'ja',
            'onderwerp': 'Smartphone cursus',
            'leeftijdscategorie_id': self.age_category.id,
            'toestel_id': self.device.id,
            'locatie_id': str(loc1.id)
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        db.session.refresh(reg)
        self.assertEqual(reg.locatie_id, loc1.id)

    def test_location_deletion_prevented_when_used_in_registrations(self):
        """Locatie kan niet verwijderd worden als er registraties aan gekoppeld zijn."""
        loc = Location(naam='Wijkcentrum Zuid', actief=True, volgorde=1, gebruikt_voor_consultaties=True, organisatie_id=self.org.id)
        db.session.add(loc)
        db.session.commit()

        reg = Registration(
            registratienummer='2026-0001',
            datum=date.today(),
            client='Karel',
            digidokter_id=self.digidokter.id,
            nieuwe_klant=True,
            onderwerp='Printer installeren',
            leeftijdscategorie_id=self.age_category.id,
            toestel_id=self.device.id,
            locatie_id=loc.id,
            organisatie_id=self.org.id
        )
        db.session.add(reg)
        db.session.commit()

        resp = self.client.post(f'/beheer/locaties/{loc.id}/verwijderen', follow_redirects=True)
        self.assertIn(b'kan niet worden verwijderd omdat er nog 1 consultatie-registratie(s) aan gekoppeld zijn', resp.data)

        # Locatie bestaat nog steeds
        loc_db = db.session.get(Location, loc.id)
        self.assertIsNotNone(loc_db)

    def test_stats_verdeling_over_locaties(self):
        """Statistiekenpagina tab 'Bezoekers & Consultaties' toont de verdeling over locaties."""
        loc_a = Location(naam='Locatie Alpha', actief=True, volgorde=1, gebruikt_voor_consultaties=True, organisatie_id=self.org.id)
        loc_b = Location(naam='Locatie Beta', actief=True, volgorde=2, gebruikt_voor_consultaties=True, organisatie_id=self.org.id)
        db.session.add_all([loc_a, loc_b])
        db.session.commit()

        # Maak 2 registraties op loc_a en 1 op loc_b
        for i in range(2):
            db.session.add(Registration(
                registratienummer=f'2026-000{i+1}',
                datum=date(2026, 3, 10),
                client=f'Bezoeker A{i}',
                digidokter_id=self.digidokter.id,
                nieuwe_klant=False,
                onderwerp='Test A',
                leeftijdscategorie_id=self.age_category.id,
                toestel_id=self.device.id,
                locatie_id=loc_a.id,
                organisatie_id=self.org.id
            ))
        db.session.add(Registration(
            registratienummer='2026-0003',
            datum=date(2026, 3, 12),
            client='Bezoeker B',
            digidokter_id=self.digidokter.id,
            nieuwe_klant=False,
            onderwerp='Test B',
            leeftijdscategorie_id=self.age_category.id,
            toestel_id=self.device.id,
            locatie_id=loc_b.id,
            organisatie_id=self.org.id
        ))
        db.session.commit()

        resp = self.client.get('/statistieken?jaar=2026')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Verdeling over locaties', resp.data)
        self.assertIn(b'Locatie Alpha', resp.data)
        self.assertIn(b'Locatie Beta', resp.data)
