"""Tests voor mapping van historische/gedeactiveerde toesteltypes en leeftijdscategorieën."""
from datetime import date
from tests.base import BaseTestCase
from extensions import db
from models.device import Device
from models.age_category import AgeCategory
from models.registration import Registration


class TestStamgegevensMapping(BaseTestCase):

    def setUp(self):
        super().setUp()
        self.login("AdminMark", "password123")
        self.select_organisatie(self.org.id)

        # Actieve doelen
        self.actief_toestel = Device(naam="Laptop Modern", actief=True, organisatie_id=self.org.id, volgorde=1)
        self.actieve_leeftijd = AgeCategory(naam="Volwassenen (18-64)", actief=True, organisatie_id=self.org.id, volgorde=1)
        
        # Oude inactieve items
        self.oud_toestel = Device(naam="Oude Laptop 2010", actief=False, organisatie_id=self.org.id, volgorde=99)
        self.oude_leeftijd = AgeCategory(naam="Oude Categorie 25-50", actief=False, organisatie_id=self.org.id, volgorde=99)
        
        db.session.add_all([self.actief_toestel, self.actieve_leeftijd, self.oud_toestel, self.oude_leeftijd])
        db.session.commit()

    def test_model_effectieve_naam_en_koppeling(self):
        """Test dat effectieve_naam correct resolveert voor actieve en gemapte inactieve entries."""
        # Actief geeft eigen naam
        self.assertEqual(self.actief_toestel.effectieve_naam, "Laptop Modern")
        self.assertEqual(self.actieve_leeftijd.effectieve_naam, "Volwassenen (18-64)")

        # Inactief zonder mapping geeft eigen naam
        self.assertEqual(self.oud_toestel.effectieve_naam, "Oude Laptop 2010")
        self.assertEqual(self.oude_leeftijd.effectieve_naam, "Oude Categorie 25-50")

        # Inactief met mapping geeft naam van de gemapte actieve entry
        self.oud_toestel.mapped_to_id = self.actief_toestel.id
        self.oude_leeftijd.mapped_to_id = self.actieve_leeftijd.id
        db.session.commit()

        self.assertEqual(self.oud_toestel.effectieve_naam, "Laptop Modern")
        self.assertEqual(self.oude_leeftijd.effectieve_naam, "Volwassenen (18-64)")
        self.assertEqual(self.oud_toestel.effectief_toestel.id, self.actief_toestel.id)
        self.assertEqual(self.oude_leeftijd.effectieve_categorie.id, self.actieve_leeftijd.id)

    def test_admin_toestel_mapping_wijzigen_en_tonen(self):
        """Test beheerpagina voor instellen van mapping bij een inactief toestel."""
        # 1. Beheer overzicht toont tabel met Gemapt naar kolom
        res = self.client.get('/beheer/toestellen')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        self.assertIn("Gemapt naar", html)
        self.assertIn("Niet gemapt", html)

        # 2. Wijzigformulier bevat dropdown van actieve entries
        res = self.client.get(f'/beheer/toestellen/{self.oud_toestel.id}/wijzig')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        self.assertIn("Koppel / map naar actieve entry", html)
        self.assertIn("Laptop Modern", html)

        # 3. Opslaan van mapping
        res = self.client.post(f'/beheer/toestellen/{self.oud_toestel.id}/wijzig', data={
            'naam': 'Oude Laptop 2010',
            # 'actief' niet aangevinkt
            'mapped_to_id': self.actief_toestel.id
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        db.session.refresh(self.oud_toestel)
        self.assertFalse(self.oud_toestel.actief)
        self.assertEqual(self.oud_toestel.mapped_to_id, self.actief_toestel.id)

        # 4. Overzicht toont nu de badge met gemapte naam
        res = self.client.get('/beheer/toestellen')
        html = res.data.decode('utf-8')
        self.assertIn(f"Laptop Modern", html)

        # 5. Wanneer het toestel weer actief wordt gemaakt, wordt mapping gewist
        res = self.client.post(f'/beheer/toestellen/{self.oud_toestel.id}/wijzig', data={
            'naam': 'Oude Laptop 2010',
            'actief': 'on',
            'mapped_to_id': self.actief_toestel.id
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        db.session.refresh(self.oud_toestel)
        self.assertTrue(self.oud_toestel.actief)
        self.assertIsNone(self.oud_toestel.mapped_to_id)

    def test_admin_leeftijdscategorie_mapping_wijzigen(self):
        """Test beheerpagina voor instellen van mapping bij een inactieve leeftijdscategorie."""
        res = self.client.post(f'/beheer/leeftijdscategorieën/{self.oude_leeftijd.id}/wijzig', data={
            'naam': 'Oude Categorie 25-50',
            'mapped_to_id': self.actieve_leeftijd.id
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        db.session.refresh(self.oude_leeftijd)
        self.assertFalse(self.oude_leeftijd.actief)
        self.assertEqual(self.oude_leeftijd.mapped_to_id, self.actieve_leeftijd.id)

        # Toggle naar actief wist mapping
        self.client.get(f'/beheer/leeftijdscategorieën/{self.oude_leeftijd.id}/toggle', follow_redirects=True)
        db.session.refresh(self.oude_leeftijd)
        self.assertTrue(self.oude_leeftijd.actief)
        self.assertIsNone(self.oude_leeftijd.mapped_to_id)

    def test_registratielijst_weergave_en_filtering_met_gemapte_items(self):
        """Test dat in het registratieoverzicht gemapte namen worden getoond en gefilterd."""
        self.oud_toestel.mapped_to_id = self.actief_toestel.id
        self.oude_leeftijd.mapped_to_id = self.actieve_leeftijd.id
        db.session.commit()

        # Registratie 1 met actieve items
        r1 = Registration(
            registratienummer="2026-0201",
            datum=date.today(),
            client="Klant Nieuw",
            digidokter_id=self.digidokter.id,
            toestel_id=self.actief_toestel.id,
            leeftijdscategorie_id=self.actieve_leeftijd.id,
            onderwerp="Vraag nieuw",
            organisatie_id=self.org.id,
            aangemaakt_door_id=self.admin_user.id
        )
        # Registratie 2 met historische inactieve items
        r2 = Registration(
            registratienummer="2026-0202",
            datum=date.today(),
            client="Klant Oud",
            digidokter_id=self.digidokter.id,
            toestel_id=self.oud_toestel.id,
            leeftijdscategorie_id=self.oude_leeftijd.id,
            onderwerp="Vraag oud",
            organisatie_id=self.org.id,
            aangemaakt_door_id=self.admin_user.id
        )
        db.session.add_all([r1, r2])
        db.session.commit()

        # 1. Lijstweergave: toont voor beide de gemapte actieve namen
        res = self.client.get('/registraties')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        self.assertIn("Laptop Modern", html)
        self.assertIn("Volwassenen (18-64)", html)

        # 2. Filteren op het actieve toestel toont BEIDE registraties
        res = self.client.get(f'/registraties?toestel={self.actief_toestel.id}')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        self.assertIn("Klant Nieuw", html)
        self.assertIn("Klant Oud", html)

        # 3. Filteren op de actieve leeftijdscategorie toont BEIDE registraties
        res = self.client.get(f'/registraties?leeftijd={self.actieve_leeftijd.id}')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        self.assertIn("Klant Nieuw", html)
        self.assertIn("Klant Oud", html)

        # 4. Detailpagina van de oude registratie toont effectieve naam en historische indicatie
        res = self.client.get(f'/registraties/{r2.id}')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        self.assertIn("Laptop Modern", html)
        self.assertIn("historisch: Oude Laptop 2010", html)
        self.assertIn("Volwassenen (18-64)", html)
        self.assertIn("historisch: Oude Categorie 25-50", html)

        # 5. Bewerkpagina preselecteert de gemapte actieve optie
        res = self.client.get(f'/registraties/{r2.id}/wijzig')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        self.assertIn(f'value="{self.actief_toestel.id}" selected', html)
        self.assertIn(f'value="{self.actieve_leeftijd.id}" selected', html)

    def test_statistieken_aggregatie_met_gemapte_items(self):
        """Test dat statistieken historische registraties groeperen onder het gemapte actieve item."""
        self.oud_toestel.mapped_to_id = self.actief_toestel.id
        self.oude_leeftijd.mapped_to_id = self.actieve_leeftijd.id
        db.session.commit()

        r1 = Registration(
            registratienummer="2026-0301",
            datum=date(2026, 3, 1),
            client="Klant 1",
            digidokter_id=self.digidokter.id,
            toestel_id=self.actief_toestel.id,
            leeftijdscategorie_id=self.actieve_leeftijd.id,
            onderwerp="Onderwerp 1",
            organisatie_id=self.org.id,
            aangemaakt_door_id=self.admin_user.id
        )
        r2 = Registration(
            registratienummer="2026-0302",
            datum=date(2026, 3, 2),
            client="Klant 2",
            digidokter_id=self.digidokter.id,
            toestel_id=self.oud_toestel.id,
            leeftijdscategorie_id=self.oude_leeftijd.id,
            onderwerp="Onderwerp 2",
            organisatie_id=self.org.id,
            aangemaakt_door_id=self.admin_user.id
        )
        db.session.add_all([r1, r2])
        db.session.commit()

        res = self.client.get('/statistieken?jaar=2026')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')

        # Laptop Modern en Volwassenen moeten beide geteld zijn met telling 2
        self.assertIn("Laptop Modern", html)
        self.assertNotIn("Oude Laptop 2010", html)
        self.assertIn("Volwassenen (18-64)", html)
        self.assertNotIn("Oude Categorie 25-50", html)

    def test_export_gebruikt_gemapte_namen(self):
        """Test dat export de gemapte namen hanteert en gemapte items matcht bij filtering."""
        self.oud_toestel.mapped_to_id = self.actief_toestel.id
        self.oude_leeftijd.mapped_to_id = self.actieve_leeftijd.id
        db.session.commit()

        r = Registration(
            registratienummer="2026-0401",
            datum=date.today(),
            client="Export Klant",
            digidokter_id=self.digidokter.id,
            toestel_id=self.oud_toestel.id,
            leeftijdscategorie_id=self.oude_leeftijd.id,
            onderwerp="Export onderwerp",
            organisatie_id=self.org.id,
            aangemaakt_door_id=self.admin_user.id
        )
        db.session.add(r)
        db.session.commit()

        with self.app.test_request_context():
            from flask import session
            session['organisatie_id'] = self.org.id
            from utils.export_handler import _haal_registraties
            rijen = _haal_registraties(toestel_id=self.actief_toestel.id)
            self.assertEqual(len(rijen), 1)
            self.assertEqual(rijen[0]['Toestel'], "Laptop Modern")
            self.assertEqual(rijen[0]['Leeftijdscategorie'], "Volwassenen (18-64)")

        # Test ook via HTTP POST route
        res = self.client.post('/exporteer', data={
            'formaat': 'csv',
            'toestel_id': self.actief_toestel.id
        })
        self.assertEqual(res.status_code, 200)
        csv_text = res.data.decode('utf-8')
        self.assertIn("Laptop Modern", csv_text)
        self.assertIn("Volwassenen (18-64)", csv_text)
        self.assertNotIn("Oude Laptop 2010", csv_text)

    def test_statistieken_sortering_volgens_stamgegevens_volgorde(self):
        """Test dat statistiekenpagina entries toont in de volgorde van stamgegevens."""
        from models.digidokter import Digidokter
        from models.herkomst import Herkomst
        from models.agenda import AgendaItem
        from models.location import Location
        from models.activity_type import ActivityType

        # Digidokters: DD1 (volgorde 2, 5 bezoeken), DD2 (volgorde 1, 1 bezoek)
        dd1 = Digidokter(naam="Zoe", volgorde=2, organisatie_id=self.org.id)
        dd2 = Digidokter(naam="Albert", volgorde=1, organisatie_id=self.org.id)
        db.session.add_all([dd1, dd2])

        # Toestellen: T1 (volgorde 2, 5 bezoeken), T2 (volgorde 1, 1 bezoek)
        t1 = Device(naam="Tablet", volgorde=2, actief=True, organisatie_id=self.org.id)
        t2 = Device(naam="Smartphone", volgorde=1, actief=True, organisatie_id=self.org.id)
        db.session.add_all([t1, t2])

        # Leeftijden: L1 (volgorde 2, 5 bezoeken), L2 (volgorde 1, 1 bezoek)
        l1 = AgeCategory(naam="Senior", volgorde=2, actief=True, organisatie_id=self.org.id)
        l2 = AgeCategory(naam="Jeugd", volgorde=1, actief=True, organisatie_id=self.org.id)
        db.session.add_all([l1, l2])

        # Herkomst: H1 (volgorde 2, 5 bezoeken), H2 (volgorde 1, 1 bezoek)
        h1 = Herkomst(naam="Website", volgorde=2, actief=True, organisatie_id=self.org.id)
        h2 = Herkomst(naam="Mond-aan-mond", volgorde=1, actief=True, organisatie_id=self.org.id)
        db.session.add_all([h1, h2])

        # Locaties & Types
        loc1 = Location(naam="Zaal Zuid", volgorde=2, actief=True, organisatie_id=self.org.id)
        loc2 = Location(naam="Zaal Noord", volgorde=1, actief=True, organisatie_id=self.org.id)
        tp1 = ActivityType(naam="Workshop", volgorde=2, actief=True, organisatie_id=self.org.id)
        tp2 = ActivityType(naam="Inloop", volgorde=1, actief=True, organisatie_id=self.org.id)
        db.session.add_all([loc1, loc2, tp1, tp2])
        db.session.commit()

        # Registraties: meer bezoeken voor volgorde 2
        for i in range(5):
            r = Registration(
                registratienummer=f"2026-99{i}",
                datum=date(2026, 6, 1),
                client=f"Client {i}",
                digidokter_id=dd1.id,
                toestel_id=t1.id,
                leeftijdscategorie_id=l1.id,
                herkomst_id=h1.id,
                onderwerp="Test",
                organisatie_id=self.org.id,
                aangemaakt_door_id=self.admin_user.id
            )
            db.session.add(r)

        # 1 bezoek voor volgorde 1
        r_single = Registration(
            registratienummer="2026-9999",
            datum=date(2026, 6, 2),
            client="Client Single",
            digidokter_id=dd2.id,
            toestel_id=t2.id,
            leeftijdscategorie_id=l2.id,
            herkomst_id=h2.id,
            onderwerp="Test Single",
            organisatie_id=self.org.id,
            aangemaakt_door_id=self.admin_user.id
        )
        db.session.add(r_single)

        # Agenda items
        ag1 = AgendaItem(
            datum=date(2026, 6, 1),
            uur_van="10:00",
            uur_tot="12:00",
            locatie_id=loc1.id,
            type_id=tp1.id,
            organisatie_id=self.org.id
        )
        ag2 = AgendaItem(
            datum=date(2026, 6, 2),
            uur_van="14:00",
            uur_tot="16:00",
            locatie_id=loc2.id,
            type_id=tp2.id,
            organisatie_id=self.org.id
        )
        db.session.add_all([ag1, ag2])
        db.session.commit()

        # Request stats pagina
        res = self.client.get('/statistieken?jaar=2026')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')

        # Volgorde 1 moet vóór volgorde 2 staan in de HTML, ondanks dat volgorde 2 5x meer bezoeken heeft
        self.assertLess(html.index("Albert"), html.index("Zoe"))
        self.assertLess(html.index("Smartphone"), html.index("Tablet"))
        self.assertLess(html.index("Jeugd"), html.index("Senior"))
        self.assertLess(html.index("Mond-aan-mond"), html.index("Website"))
        self.assertLess(html.index("Zaal Noord"), html.index("Zaal Zuid"))
        self.assertLess(html.index("Inloop"), html.index("Workshop"))


