import uuid
from datetime import date, timedelta
from tests.base import BaseTestCase
from extensions import db
from models.agenda import AgendaItem
from models.activity_type import ActivityType
from models.location import Location
from models.digidokter import Digidokter
from models.organisatie import Organisatie, UserOrganisatie
from models.user import User
from werkzeug.security import generate_password_hash


class TestAgendaRoutes(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.type_workshop = ActivityType(naam="Workshop AI", actief=True, organisatie_id=self.org.id)
        self.type_digicafe = ActivityType(naam="Digicafé Vragen", actief=True, organisatie_id=self.org.id)
        self.locatie1 = Location(naam="Bibliotheek Centrum", actief=True, organisatie_id=self.org.id)
        self.locatie2 = Location(naam="Dienstencentrum Zuid", actief=True, organisatie_id=self.org.id)

        db.session.add_all([self.type_workshop, self.type_digicafe, self.locatie1, self.locatie2])
        db.session.commit()

        self.digidokter.user_id = self.medewerker_user.id
        db.session.commit()

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

    def test_agenda_list_filters_and_sorting(self):
        """Test filters (verleden, type, locatie, digidokter, datumreeks) en kolomsorteringen."""
        self.login_admin()

        vandaag = date.today()
        gisteren = vandaag - timedelta(days=1)
        morgen = vandaag + timedelta(days=1)
        volgende_week = vandaag + timedelta(days=7)

        item_past = AgendaItem(
            datum=gisteren,
            uur_van="10:00",
            uur_tot="12:00",
            type_id=self.type_digicafe.id,
            locatie_id=self.locatie1.id,
            omschrijving="Sessie gisteren",
            organisatie_id=self.org.id
        )
        item_morgen = AgendaItem(
            datum=morgen,
            uur_van="14:00",
            uur_tot="16:00",
            type_id=self.type_workshop.id,
            locatie_id=self.locatie2.id,
            omschrijving="Workshop morgen",
            organisatie_id=self.org.id
        )
        item_next_week = AgendaItem(
            datum=volgende_week,
            uur_van="09:00",
            uur_tot="11:00",
            type_id=self.type_digicafe.id,
            locatie_id=self.locatie1.id,
            omschrijving="Sessie volgende week",
            organisatie_id=self.org.id
        )
        db.session.add_all([item_past, item_morgen, item_next_week])
        item_past.digidokters.append(self.digidokter)
        db.session.commit()

        # A. Default lijst: toont enkel vandaag en toekomst (item_past niet zichtbaar)
        res_default = self.client.get('/agenda')
        self.assertEqual(res_default.status_code, 200)
        self.assertNotIn("Sessie gisteren", res_default.get_data(as_text=True))
        self.assertIn("Workshop morgen", res_default.get_data(as_text=True))
        self.assertIn("Sessie volgende week", res_default.get_data(as_text=True))

        # B. Lijst met toon_verleden=on (toont ook verleden)
        res_all = self.client.get('/agenda?toon_verleden=on')
        self.assertEqual(res_all.status_code, 200)
        self.assertIn("Sessie gisteren", res_all.get_data(as_text=True))

        # C. Filter op type_id
        res_type = self.client.get(f'/agenda?toon_verleden=on&type_id={self.type_workshop.id}')
        self.assertIn("Workshop morgen", res_type.get_data(as_text=True))
        self.assertNotIn("Sessie gisteren", res_type.get_data(as_text=True))

        # D. Filter op locatie_id
        res_loc = self.client.get(f'/agenda?toon_verleden=on&locatie_id={self.locatie2.id}')
        self.assertIn("Workshop morgen", res_loc.get_data(as_text=True))
        self.assertNotIn("Sessie gisteren", res_loc.get_data(as_text=True))

        # E. Filter op digidokter_id
        res_dd = self.client.get(f'/agenda?toon_verleden=on&digidokter_id={self.digidokter.id}')
        self.assertIn("Sessie gisteren", res_dd.get_data(as_text=True))
        self.assertNotIn("Workshop morgen", res_dd.get_data(as_text=True))

        # F. Sorteringen
        for sort_key in ['datum', 'tijd', 'type', 'locatie', 'omschrijving']:
            for dir_key in ['asc', 'desc']:
                res_sort = self.client.get(f'/agenda?toon_verleden=on&sort_by={sort_key}&direction={dir_key}')
                self.assertEqual(res_sort.status_code, 200)

    def test_agenda_nieuw_validation_failures(self):
        """Test alle validatiefouten bij het aanmaken van een agenda-item."""
        self.login_admin()
        vandaag_str = date.today().isoformat()

        # 1. Lege datum
        res1 = self.client.post('/agenda/nieuw', data={
            'datum': '',
            'uur_van': '10:00',
            'uur_tot': '12:00',
            'type_id': self.type_digicafe.id,
            'locatie_id': self.locatie1.id
        }, follow_redirects=True)
        self.assertIn("datum is verplicht", res1.get_data(as_text=True).lower())

        # 2. Ongeldig tijdformaat
        res2 = self.client.post('/agenda/nieuw', data={
            'datum': vandaag_str,
            'uur_van': '10:99',
            'uur_tot': '12:00',
            'type_id': self.type_digicafe.id,
            'locatie_id': self.locatie1.id
        }, follow_redirects=True)
        self.assertIn("tijdstip moet in hh:mm formaat zijn", res2.get_data(as_text=True).lower())

        # 3. Begintijd na eindtijd
        res3 = self.client.post('/agenda/nieuw', data={
            'datum': vandaag_str,
            'uur_van': '15:00',
            'uur_tot': '13:00',
            'type_id': self.type_digicafe.id,
            'locatie_id': self.locatie1.id
        }, follow_redirects=True)
        self.assertIn("begintijd mag niet na eindtijd liggen", res3.get_data(as_text=True).lower())

        # 4. Ontbrekend type of locatie
        res4 = self.client.post('/agenda/nieuw', data={
            'datum': vandaag_str,
            'uur_van': '10:00',
            'uur_tot': '12:00',
            'type_id': 0,
            'locatie_id': 0
        }, follow_redirects=True)
        self.assertIn("type activiteit is verplicht", res4.get_data(as_text=True).lower())
        self.assertIn("locatie is verplicht", res4.get_data(as_text=True).lower())

    def test_agenda_nieuw_single_item_success(self):
        """Test succesvol aanmaken van een enkel agenda-item met digidokters."""
        self.login_admin()
        vandaag = date.today()

        res = self.client.post('/agenda/nieuw', data={
            'datum': vandaag.isoformat(),
            'uur_van': '13:30',
            'uur_tot': '15:30',
            'type_id': self.type_workshop.id,
            'locatie_id': self.locatie1.id,
            'omschrijving': 'Kennismaking met tablets',
            'digidokter_ids': [str(self.digidokter.id)]
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn("agenda-item succesvol toegevoegd", res.get_data(as_text=True).lower())

        item = AgendaItem.query.filter_by(omschrijving='Kennismaking met tablets', organisatie_id=self.org.id).first()
        self.assertIsNotNone(item)
        self.assertEqual(item.datum, vandaag)
        self.assertEqual(item.uur_van, '13:30')
        self.assertEqual(item.uur_tot, '15:30')
        self.assertEqual(len(item.digidokters), 1)
        self.assertEqual(item.digidokters[0].id, self.digidokter.id)

    def test_agenda_nieuw_recurring_series_validation_and_generation(self):
        """Test validatie en automatische reeksen-generatie (dagelijks, wekelijks, maandelijks)."""
        self.login_admin()
        start_datum = date.today()

        # 1. Terugkerend aangevinkt maar geen interval of einddatum
        res_inv = self.client.post('/agenda/nieuw', data={
            'datum': start_datum.isoformat(),
            'uur_van': '10:00',
            'uur_tot': '12:00',
            'type_id': self.type_digicafe.id,
            'locatie_id': self.locatie1.id,
            'is_terugkerend': 'on',
            'interval': '',
            'einddatum': ''
        }, follow_redirects=True)
        self.assertIn("selecteer een geldig herhalingsinterval", res_inv.get_data(as_text=True).lower())
        self.assertIn("einddatum is verplicht", res_inv.get_data(as_text=True).lower())

        # 2. Einddatum vóór begindatum
        res_before = self.client.post('/agenda/nieuw', data={
            'datum': start_datum.isoformat(),
            'uur_van': '10:00',
            'uur_tot': '12:00',
            'type_id': self.type_digicafe.id,
            'locatie_id': self.locatie1.id,
            'is_terugkerend': 'on',
            'interval': 'wekelijks',
            'einddatum': (start_datum - timedelta(days=5)).isoformat()
        }, follow_redirects=True)
        self.assertIn("einddatum mag niet vóór de begindatum liggen", res_before.get_data(as_text=True).lower())

        # 3. Wekelijkse reeks voor 4 weken aanmaken (startdatum + 3 weken = 4 sessies)
        eind_datum = start_datum + timedelta(weeks=3)
        res_weekly = self.client.post('/agenda/nieuw', data={
            'datum': start_datum.isoformat(),
            'uur_van': '10:00',
            'uur_tot': '12:00',
            'type_id': self.type_digicafe.id,
            'locatie_id': self.locatie1.id,
            'omschrijving': 'Wekelijks Digicafé',
            'is_terugkerend': 'on',
            'interval': 'wekelijks',
            'einddatum': eind_datum.isoformat()
        }, follow_redirects=True)
        self.assertEqual(res_weekly.status_code, 200)
        self.assertIn("succesvol toegevoegd aan de reeks", res_weekly.get_data(as_text=True).lower())

        items = AgendaItem.query.filter_by(omschrijving='Wekelijks Digicafé', organisatie_id=self.org.id).all()
        self.assertEqual(len(items), 4)
        self.assertTrue(all(it.reeks_id is not None for it in items))
        self.assertEqual(len({it.reeks_id for it in items}), 1)

    def test_agenda_wijzigen_and_validation(self):
        """Test wijzigen van een bestaand agenda-item en validatiefouten."""
        self.login_admin()
        vandaag = date.today()

        item = AgendaItem(
            datum=vandaag,
            uur_van="09:00",
            uur_tot="11:00",
            type_id=self.type_digicafe.id,
            locatie_id=self.locatie1.id,
            omschrijving="Originele sessie",
            organisatie_id=self.org.id
        )
        db.session.add(item)
        db.session.commit()

        # 1. Validatiefout bij wijzigen (begintijd na eindtijd)
        res_fail = self.client.post(f'/agenda/{item.id}/wijzig', data={
            'datum': vandaag.isoformat(),
            'uur_van': '16:00',
            'uur_tot': '14:00',
            'type_id': self.type_digicafe.id,
            'locatie_id': self.locatie1.id
        }, follow_redirects=True)
        self.assertIn("begintijd mag niet na eindtijd liggen", res_fail.get_data(as_text=True).lower())

        # 2. Succesvol wijzigen
        nieuwe_datum = vandaag + timedelta(days=2)
        res_ok = self.client.post(f'/agenda/{item.id}/wijzig', data={
            'datum': nieuwe_datum.isoformat(),
            'uur_van': '14:00',
            'uur_tot': '16:30',
            'type_id': self.type_workshop.id,
            'locatie_id': self.locatie2.id,
            'omschrijving': 'Gewijzigde sessie titel',
            'digidokter_ids': [str(self.digidokter.id)]
        }, follow_redirects=True)
        self.assertEqual(res_ok.status_code, 200)
        self.assertIn("succesvol bijgewerkt", res_ok.get_data(as_text=True).lower())

        db.session.refresh(item)
        self.assertEqual(item.datum, nieuwe_datum)
        self.assertEqual(item.uur_van, '14:00')
        self.assertEqual(item.uur_tot, '16:30')
        self.assertEqual(item.type_id, self.type_workshop.id)
        self.assertEqual(item.locatie_id, self.locatie2.id)
        self.assertEqual(item.omschrijving, 'Gewijzigde sessie titel')
        self.assertEqual(len(item.digidokters), 1)

    def test_agenda_verwijderen_single_vs_entire_series(self):
        """Test verwijderen van één los agenda-item versus een complete reeks."""
        self.login_admin()
        reeks_uuid = str(uuid.uuid4())

        item1 = AgendaItem(
            datum=date.today(),
            uur_van="10:00",
            uur_tot="12:00",
            type_id=self.type_digicafe.id,
            locatie_id=self.locatie1.id,
            reeks_id=reeks_uuid,
            organisatie_id=self.org.id
        )
        item2 = AgendaItem(
            datum=date.today() + timedelta(weeks=1),
            uur_van="10:00",
            uur_tot="12:00",
            type_id=self.type_digicafe.id,
            locatie_id=self.locatie1.id,
            reeks_id=reeks_uuid,
            organisatie_id=self.org.id
        )
        standalone = AgendaItem(
            datum=date.today() + timedelta(days=3),
            uur_van="13:00",
            uur_tot="15:00",
            type_id=self.type_workshop.id,
            locatie_id=self.locatie2.id,
            organisatie_id=self.org.id
        )
        db.session.add_all([item1, item2, standalone])
        db.session.commit()

        # 1. Enkel los item verwijderen (zonder verwijder_reeks flag)
        res_single = self.client.post(f'/agenda/{standalone.id}/verwijder', follow_redirects=True)
        self.assertEqual(res_single.status_code, 200)
        self.assertIn("agenda-item succesvol verwijderd", res_single.get_data(as_text=True).lower())
        self.assertIsNone(db.session.get(AgendaItem, standalone.id))

        # 2. Complete reeks verwijderen (met verwijder_reeks=true)
        res_series = self.client.post(f'/agenda/{item1.id}/verwijder', data={'verwijder_reeks': 'true'}, follow_redirects=True)
        self.assertEqual(res_series.status_code, 200)
        self.assertIn("gehele reeks van activiteiten is succesvol verwijderd", res_series.get_data(as_text=True).lower())

        self.assertIsNone(db.session.get(AgendaItem, item1.id))
        self.assertIsNone(db.session.get(AgendaItem, item2.id))

    def test_agenda_cross_tenant_isolation_and_lezer_permissions(self):
        """Test dat agenda-items van andere organisaties niet gemuteerd kunnen worden en lezers geen schrijfrechten hebben."""
        org2 = Organisatie(naam="Org 2", slug="org2", actief=True)
        db.session.add(org2)
        db.session.commit()

        loc_org2 = Location(naam="Bib Org 2", actief=True, organisatie_id=org2.id)
        type_org2 = ActivityType(naam="Type Org 2", actief=True, organisatie_id=org2.id)
        db.session.add_all([loc_org2, type_org2])
        db.session.commit()

        item_org2 = AgendaItem(
            datum=date.today(),
            uur_van="10:00",
            uur_tot="12:00",
            type_id=type_org2.id,
            locatie_id=loc_org2.id,
            organisatie_id=org2.id
        )
        db.session.add(item_org2)
        db.session.commit()

        self.login_admin()

        # 1. Beheerder van org1 probeert agenda-item van org2 te wijzigen -> 403
        res_edit = self.client.post(f'/agenda/{item_org2.id}/wijzig', data={'omschrijving': 'Hack'})
        self.assertEqual(res_edit.status_code, 403)

        # 2. Beheerder van org1 probeert agenda-item van org2 te verwijderen -> 403
        res_del = self.client.post(f'/agenda/{item_org2.id}/verwijder')
        self.assertEqual(res_del.status_code, 403)

        # 3. Lezer rol mag geen items toevoegen of bewerken
        self.logout()
        lezer = User(
            naam="UserLezerAgenda",
            email="lezeragenda@test.com",
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
        self.client.post('/login', data={'email': 'lezeragenda@test.com', 'wachtwoord': 'pass'}, follow_redirects=True)

        res_lezer_post = self.client.post('/agenda/nieuw', data={}, follow_redirects=True)
        self.assertIn("geen schrijfrechten", res_lezer_post.get_data(as_text=True).lower())
