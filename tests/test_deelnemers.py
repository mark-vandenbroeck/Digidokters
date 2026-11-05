from datetime import date, timedelta
from tests.base import BaseTestCase
from extensions import db
from models.agenda import AgendaItem
from models.activity_type import ActivityType
from models.location import Location
from models.deelnemer import Deelnemer
from models.organisatie import Organisatie, UserOrganisatie
from models.user import User
from utils.stamgegevens import get_usage_counts
from utils.backup_handler import maak_backup, herstel_backup
import io
import json


class TestDeelnemers(BaseTestCase):
    def setUp(self):
        super().setUp()
        # Activity types: 1 met vlag, 1 zonder
        self.type_met_deelnemers = ActivityType(
            naam="Workshop Digitaal",
            actief=True,
            registreer_deelnemers=True,
            organisatie_id=self.org.id
        )
        self.type_zonder_deelnemers = ActivityType(
            naam="Spreekuur",
            actief=True,
            registreer_deelnemers=False,
            organisatie_id=self.org.id
        )
        self.locatie = Location(naam="Bib Hoofddorp", actief=True, organisatie_id=self.org.id)

        # Deelnemers
        self.deelnemer1 = Deelnemer(naam="Anna Peeters", actief=True, organisatie_id=self.org.id)
        self.deelnemer2 = Deelnemer(naam="Bert Janssens", actief=True, organisatie_id=self.org.id)
        self.deelnemer_inactief = Deelnemer(naam="Karel Inactief", actief=False, organisatie_id=self.org.id)

        # Tweede organisatie voor multi-tenant isolatietests
        self.org2 = Organisatie(naam="Tweede Org", slug="tweede-org")
        db.session.add(self.org2)
        db.session.flush()
        self.deelnemer_org2 = Deelnemer(naam="Dirk OrgTwee", actief=True, organisatie_id=self.org2.id)

        db.session.add_all([
            self.type_met_deelnemers, self.type_zonder_deelnemers,
            self.locatie, self.deelnemer1, self.deelnemer2,
            self.deelnemer_inactief, self.deelnemer_org2
        ])
        db.session.commit()

    def login_admin(self, org_id=None):
        target_org = org_id or self.org.id
        with self.client.session_transaction() as sess:
            sess['organisatie_id'] = target_org
        return self.client.post('/login', data={
            'email': 'admin@test.com',
            'wachtwoord': 'password123'
        }, follow_redirects=True)

    def test_model_deelnemer_repr_en_uniek(self):
        """Test Deelnemer model representatie en unieke naam per organisatie."""
        self.assertEqual(repr(self.deelnemer1), "<Deelnemer Anna Peeters>")
        self.assertTrue(self.deelnemer1.actief)

        # Dubbele naam binnen dezelfde org mag niet
        dubbel = Deelnemer(naam="Anna Peeters", organisatie_id=self.org.id)
        db.session.add(dubbel)
        with self.assertRaises(Exception):
            db.session.commit()
        db.session.rollback()

        # Zelfde naam in andere org mag wel
        in_org2 = Deelnemer(naam="Anna Peeters", organisatie_id=self.org2.id)
        db.session.add(in_org2)
        db.session.commit()
        self.assertIsNotNone(in_org2.id)

    def test_activity_type_registreer_deelnemers_flag_crud(self):
        """Test de extra vlag 'registreer_deelnemers' in de CRUD voor activiteitstypes."""
        self.login_admin()

        # 1. Nieuw activiteitstype met vlag aan
        res = self.client.post('/beheer/activiteitstypes/nieuw', data={
            'naam': 'Cursus Smartphone',
            'actief': 'on',
            'registreer_deelnemers': 'on',
            'kleur': 'teal'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        created = ActivityType.query.filter_by(organisatie_id=self.org.id, naam='Cursus Smartphone').first()
        self.assertIsNotNone(created)
        self.assertTrue(created.registreer_deelnemers)

        # 2. Nieuw activiteitstype zonder vlag
        res = self.client.post('/beheer/activiteitstypes/nieuw', data={
            'naam': 'Koffie Klets',
            'actief': 'on',
            'kleur': 'blue'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        created_no = ActivityType.query.filter_by(organisatie_id=self.org.id, naam='Koffie Klets').first()
        self.assertIsNotNone(created_no)
        self.assertFalse(created_no.registreer_deelnemers)

        # 3. Wijzigen: vlag aanzetten
        res = self.client.post(f'/beheer/activiteitstypes/{created_no.id}/wijzig', data={
            'naam': 'Koffie Klets',
            'actief': 'on',
            'registreer_deelnemers': 'on',
            'kleur': 'orange'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        db.session.refresh(created_no)
        self.assertTrue(created_no.registreer_deelnemers)

        # 4. Wijzigen: vlag uitzetten
        res = self.client.post(f'/beheer/activiteitstypes/{created.id}/wijzig', data={
            'naam': 'Cursus Smartphone',
            'actief': 'on',
            'kleur': 'teal'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        db.session.refresh(created)
        self.assertFalse(created.registreer_deelnemers)

        # 5. Overzicht toont badge/status
        res_list = self.client.get('/beheer/activiteitstypes')
        self.assertIn('Deelnemers', res_list.data.decode('utf-8'))

    def test_deelnemers_overzicht_filters_en_zoeken(self):
        """Test overzichtspagina van deelnemers met statusfilters en zoekopdracht."""
        self.login_admin()

        # Alle deelnemers
        res = self.client.get('/beheer/deelnemers')
        self.assertEqual(res.status_code, 200)
        data = res.data.decode('utf-8')
        self.assertIn("Anna Peeters", data)
        self.assertIn("Bert Janssens", data)
        self.assertNotIn("Dirk OrgTwee", data)  # Multi-tenant isolatie

        # Enkel actieve
        res_actief = self.client.get('/beheer/deelnemers?status=actief')
        self.assertEqual(res_actief.status_code, 200)
        data_actief = res_actief.data.decode('utf-8')
        self.assertIn("Anna Peeters", data_actief)
        self.assertNotIn("Karel Inactief", data_actief)

        # Enkel inactieve
        res_inactief = self.client.get('/beheer/deelnemers?status=inactief')
        self.assertEqual(res_inactief.status_code, 200)
        data_inactief = res_inactief.data.decode('utf-8')
        self.assertNotIn("Anna Peeters", data_inactief)
        self.assertIn("Karel Inactief", data_inactief)

        # Zoekterm
        res_zoek = self.client.get('/beheer/deelnemers?q=Anna')
        self.assertEqual(res_zoek.status_code, 200)
        data_zoek = res_zoek.data.decode('utf-8')
        self.assertIn("Anna Peeters", data_zoek)
        self.assertNotIn("Bert Janssens", data_zoek)

        # Ongeldige status filter valt terug op 'alle'
        res_invalid_status = self.client.get('/beheer/deelnemers?status=ongeldig')
        self.assertEqual(res_invalid_status.status_code, 200)

    def test_deelnemer_nieuw_en_validatie(self):
        """Test toevoegen van een nieuwe deelnemer via formulier met validaties."""
        self.login_admin()

        # 1. Lege naam faalt
        res_empty = self.client.post('/beheer/deelnemers/nieuw', data={
            'naam': '   ',
            'actief': 'on'
        }, follow_redirects=True)
        self.assertIn("Naam is verplicht.", res_empty.data.decode('utf-8'))

        # 2. Dubbele naam faalt
        res_dup = self.client.post('/beheer/deelnemers/nieuw', data={
            'naam': 'Anna Peeters',
            'actief': 'on'
        }, follow_redirects=True)
        self.assertIn("Er bestaat al een deelnemer met de naam", res_dup.data.decode('utf-8'))

        # 3. Succesvol aanmaken
        res_ok = self.client.post('/beheer/deelnemers/nieuw', data={
            'naam': 'Els Claes',
            'actief': 'on'
        }, follow_redirects=True)
        self.assertEqual(res_ok.status_code, 200)
        self.assertIn("Deelnemer Els Claes succesvol toegevoegd.", res_ok.data.decode('utf-8'))

        created = Deelnemer.query.filter_by(organisatie_id=self.org.id, naam='Els Claes').first()
        self.assertIsNotNone(created)
        self.assertTrue(created.actief)

        # GET formulier
        res_get = self.client.get('/beheer/deelnemers/nieuw')
        self.assertEqual(res_get.status_code, 200)

    def test_deelnemer_wijzigen_en_cross_tenant(self):
        """Test wijzigen van een deelnemer en cross-tenant beveiliging."""
        self.login_admin()

        # 1. GET wijzig form
        res_get = self.client.get(f'/beheer/deelnemers/{self.deelnemer1.id}/wijzig')
        self.assertEqual(res_get.status_code, 200)
        self.assertIn("Anna Peeters", res_get.data.decode('utf-8'))

        # 2. Lege naam faalt
        res_empty = self.client.post(f'/beheer/deelnemers/{self.deelnemer1.id}/wijzig', data={
            'naam': '',
            'actief': 'on'
        }, follow_redirects=True)
        self.assertIn("Naam is verplicht.", res_empty.data.decode('utf-8'))

        # 3. Conflict met bestaande naam faalt
        res_dup = self.client.post(f'/beheer/deelnemers/{self.deelnemer1.id}/wijzig', data={
            'naam': 'Bert Janssens',
            'actief': 'on'
        }, follow_redirects=True)
        self.assertIn("Er bestaat al een andere deelnemer met de naam", res_dup.data.decode('utf-8'))

        # 4. Succesvol wijzigen
        res_ok = self.client.post(f'/beheer/deelnemers/{self.deelnemer1.id}/wijzig', data={
            'naam': 'Anna Peeters-Wouters',
            'actief': 'on'
        }, follow_redirects=True)
        self.assertEqual(res_ok.status_code, 200)
        db.session.refresh(self.deelnemer1)
        self.assertEqual(self.deelnemer1.naam, "Anna Peeters-Wouters")

        # 5. Cross-tenant abort 403
        res_cross = self.client.get(f'/beheer/deelnemers/{self.deelnemer_org2.id}/wijzig')
        self.assertEqual(res_cross.status_code, 403)
        res_cross_post = self.client.post(f'/beheer/deelnemers/{self.deelnemer_org2.id}/wijzig', data={'naam': 'Hacker'})
        self.assertEqual(res_cross_post.status_code, 403)

    def test_deelnemer_toggle_en_verwijderen(self):
        """Test toggle actief/inactief en verwijderen met beveiliging tegen verwijderen bij koppelingen."""
        self.login_admin()

        # Toggle naar inactief
        res_toggle = self.client.get(f'/beheer/deelnemers/{self.deelnemer1.id}/toggle', follow_redirects=True)
        self.assertEqual(res_toggle.status_code, 200)
        db.session.refresh(self.deelnemer1)
        self.assertFalse(self.deelnemer1.actief)

        # Toggle terug naar actief
        res_toggle2 = self.client.get(f'/beheer/deelnemers/{self.deelnemer1.id}/toggle', follow_redirects=True)
        self.assertEqual(res_toggle2.status_code, 200)
        db.session.refresh(self.deelnemer1)
        self.assertTrue(self.deelnemer1.actief)

        # Verwijderen zonder koppelingen lukt
        dn_temp = Deelnemer(naam="Tijdelijke Deelnemer", actief=True, organisatie_id=self.org.id)
        db.session.add(dn_temp)
        db.session.commit()

        res_del = self.client.post(f'/beheer/deelnemers/{dn_temp.id}/verwijderen', follow_redirects=True)
        self.assertEqual(res_del.status_code, 200)
        self.assertIsNone(db.session.get(Deelnemer, dn_temp.id))

        # Koppelen aan een agenda-item
        item = AgendaItem(
            datum=date.today(),
            uur_van="10:00",
            uur_tot="12:00",
            type_id=self.type_met_deelnemers.id,
            locatie_id=self.locatie.id,
            organisatie_id=self.org.id
        )
        item.deelnemers.append(self.deelnemer1)
        db.session.add(item)
        db.session.commit()

        # Verwijderen gekoppelde deelnemer faalt
        res_del_linked = self.client.post(f'/beheer/deelnemers/{self.deelnemer1.id}/verwijderen', follow_redirects=True)
        self.assertIn("Kan deelnemer Anna Peeters niet verwijderen omdat deze gekoppeld is aan", res_del_linked.data.decode('utf-8'))
        self.assertIsNotNone(db.session.get(Deelnemer, self.deelnemer1.id))

        # Cross-tenant delete 403
        res_cross_del = self.client.post(f'/beheer/deelnemers/{self.deelnemer_org2.id}/verwijderen')
        self.assertEqual(res_cross_del.status_code, 403)

    def test_deelnemers_ajax_api_endpoints(self):
        """Test snelle AJAX endpoints voor LOV autocomplete en inline bewerken."""
        self.login_admin()

        # 1. Snel toevoegen: lege naam faalt
        res_empty = self.client.post('/beheer/deelnemers/api/snel-toevoegen', json={'naam': ''})
        self.assertEqual(res_empty.status_code, 400)

        # 2. Snel toevoegen: nieuwe deelnemer aanmaken
        res_new = self.client.post('/beheer/deelnemers/api/snel-toevoegen', json={'naam': 'Nieuwe Deelnemer'})
        self.assertEqual(res_new.status_code, 201)
        data = res_new.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['naam'], 'Nieuwe Deelnemer')
        self.assertFalse(data['bestaand'])
        nieuw_id = data['id']

        # 3. Snel toevoegen: reeds bestaande naam hergebruiken
        res_exist = self.client.post('/beheer/deelnemers/api/snel-toevoegen', json={'naam': 'Nieuwe Deelnemer'})
        self.assertEqual(res_exist.status_code, 200)
        data_exist = res_exist.get_json()
        self.assertTrue(data_exist['success'])
        self.assertEqual(data_exist['id'], nieuw_id)
        self.assertTrue(data_exist['bestaand'])

        # 4. Snel toevoegen: inactieve deelnemer heractiveren
        res_reactivate = self.client.post('/beheer/deelnemers/api/snel-toevoegen', json={'naam': 'Karel Inactief'})
        self.assertEqual(res_reactivate.status_code, 200)
        db.session.refresh(self.deelnemer_inactief)
        self.assertTrue(self.deelnemer_inactief.actief)

        # 5. Wijzig via AJAX
        res_edit = self.client.post(f'/beheer/deelnemers/api/{nieuw_id}/wijzig_ajax', json={'naam': 'Hernoemde Deelnemer'})
        self.assertEqual(res_edit.status_code, 200)
        data_edit = res_edit.get_json()
        self.assertTrue(data_edit['success'])
        self.assertEqual(data_edit['naam'], 'Hernoemde Deelnemer')

        # 5b. Wijzig via AJAX met lege naam faalt
        res_edit_empty = self.client.post(f'/beheer/deelnemers/api/{nieuw_id}/wijzig_ajax', json={'naam': '  '})
        self.assertEqual(res_edit_empty.status_code, 400)

        # 6. Wijzig via AJAX: conflict met bestaande naam
        res_edit_conflict = self.client.post(f'/beheer/deelnemers/api/{nieuw_id}/wijzig_ajax', json={'naam': 'Anna Peeters'})
        self.assertEqual(res_edit_conflict.status_code, 400)

        # 7. Wijzig via AJAX: cross-tenant 403
        res_edit_cross = self.client.post(f'/beheer/deelnemers/api/{self.deelnemer_org2.id}/wijzig_ajax', json={'naam': 'Hack'})
        self.assertEqual(res_edit_cross.status_code, 403)

        # 8. Realtime LOV zoek-API
        res_search = self.client.get('/beheer/deelnemers/api/zoeken?q=Anna')
        self.assertEqual(res_search.status_code, 200)
        search_data = res_search.get_json()
        self.assertTrue(any(d['naam'] == 'Anna Peeters' for d in search_data))
        self.assertFalse(any(d['naam'] == 'Dirk OrgTwee' for d in search_data))

    def test_agenda_crud_met_deelnemers_en_vlag(self):
        """Test toevoegen, wijzigen en wissen van deelnemers aan een agenda-item als de vlag gezet is."""
        self.login_admin()

        vandaag = date.today()

        # 1. Agenda item aanmaken met activiteitstype MET vlag -> deelnemers worden gekoppeld
        res = self.client.post('/agenda/nieuw', data={
            'datum': vandaag.isoformat(),
            'uur_van': '14:00',
            'uur_tot': '16:00',
            'type_id': self.type_met_deelnemers.id,
            'locatie_id': self.locatie.id,
            'omschrijving': 'Test activiteit met deelnemers',
            'digidokter_ids': [self.digidokter.id],
            'deelnemer_ids': [self.deelnemer1.id, self.deelnemer2.id]
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        item = AgendaItem.query.filter_by(omschrijving='Test activiteit met deelnemers').first()
        self.assertIsNotNone(item)
        self.assertEqual(len(item.deelnemers), 2)
        deelnemer_namen = {d.naam for d in item.deelnemers}
        self.assertEqual(deelnemer_namen, {"Anna Peeters", "Bert Janssens"})

        # Agenda lijst toont aantal deelnemers
        res_lijst = self.client.get('/agenda')
        self.assertIn("2 deelnemers", res_lijst.data.decode('utf-8'))

        # 2. Agenda item wijzigen: 1 deelnemer wissen/verwijderen en andere toevoegen
        dn_extra = Deelnemer(naam="Chantal Vervoort", actief=True, organisatie_id=self.org.id)
        db.session.add(dn_extra)
        db.session.commit()

        res_wijzig = self.client.post(f'/agenda/{item.id}/wijzig', data={
            'datum': vandaag.isoformat(),
            'uur_van': '14:00',
            'uur_tot': '16:00',
            'type_id': self.type_met_deelnemers.id,
            'locatie_id': self.locatie.id,
            'omschrijving': 'Aangepaste sessie',
            'digidokter_ids': [self.digidokter.id],
            'deelnemer_ids': [self.deelnemer1.id, dn_extra.id]  # Bert weggelaten, Chantal toegevoegd
        }, follow_redirects=True)
        self.assertEqual(res_wijzig.status_code, 200)

        db.session.refresh(item)
        self.assertEqual(len(item.deelnemers), 2)
        namen_na_wijzig = {d.naam for d in item.deelnemers}
        self.assertEqual(namen_na_wijzig, {"Anna Peeters", "Chantal Vervoort"})

        # 3. Type wijzigen naar type ZONDER deelnemersvlag -> deelnemers worden gewist
        res_wissel_type = self.client.post(f'/agenda/{item.id}/wijzig', data={
            'datum': vandaag.isoformat(),
            'uur_van': '14:00',
            'uur_tot': '16:00',
            'type_id': self.type_zonder_deelnemers.id,
            'locatie_id': self.locatie.id,
            'omschrijving': 'Gewijzigd naar spreekuur',
            'digidokter_ids': [self.digidokter.id],
            'deelnemer_ids': [self.deelnemer1.id]  # Mag niet opgeslagen worden
        }, follow_redirects=True)
        self.assertEqual(res_wissel_type.status_code, 200)

        db.session.refresh(item)
        self.assertEqual(len(item.deelnemers), 0)

        # 4. Nieuw agenda item aanmaken met type ZONDER vlag -> deelnemer_ids genegeerd
        res_zonder = self.client.post('/agenda/nieuw', data={
            'datum': vandaag.isoformat(),
            'uur_van': '10:00',
            'uur_tot': '11:00',
            'type_id': self.type_zonder_deelnemers.id,
            'locatie_id': self.locatie.id,
            'omschrijving': 'Sessie zonder vlag',
            'digidokter_ids': [self.digidokter.id],
            'deelnemer_ids': [self.deelnemer1.id]
        }, follow_redirects=True)
        self.assertEqual(res_zonder.status_code, 200)

        item_zonder = AgendaItem.query.filter_by(omschrijving='Sessie zonder vlag').first()
        self.assertIsNotNone(item_zonder)
        self.assertEqual(len(item_zonder.deelnemers), 0)

    def test_agenda_terugkerende_reeks_met_deelnemers(self):
        """Test dat bij een terugkerende reeks de deelnemers aan elk agenda-item in de reeks gekoppeld worden."""
        self.login_admin()

        vandaag = date.today()
        einddatum = vandaag + timedelta(days=14)

        res = self.client.post('/agenda/nieuw', data={
            'datum': vandaag.isoformat(),
            'uur_van': '09:00',
            'uur_tot': '11:00',
            'type_id': self.type_met_deelnemers.id,
            'locatie_id': self.locatie.id,
            'omschrijving': 'Reeks met deelnemers',
            'digidokter_ids': [self.digidokter.id],
            'is_terugkerend': 'on',
            'interval': 'wekelijks',
            'einddatum': einddatum.isoformat(),
            'deelnemer_ids': [self.deelnemer1.id]
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        reeks_items = AgendaItem.query.filter_by(omschrijving='Reeks met deelnemers').all()
        self.assertEqual(len(reeks_items), 3)  # vandaag, dag+7, dag+14
        for r_item in reeks_items:
            self.assertEqual(len(r_item.deelnemers), 1)
            self.assertEqual(r_item.deelnemers[0].naam, "Anna Peeters")

    def test_stamgegevens_usage_counts_deelnemers(self):
        """Test dat get_usage_counts correct het aantal gekoppelde activiteiten telt voor Deelnemer."""
        # Koppel Anna aan 2 activiteiten
        item1 = AgendaItem(datum=date.today(), uur_van="09:00", uur_tot="10:00", type_id=self.type_met_deelnemers.id, locatie_id=self.locatie.id, organisatie_id=self.org.id)
        item2 = AgendaItem(datum=date.today(), uur_van="11:00", uur_tot="12:00", type_id=self.type_met_deelnemers.id, locatie_id=self.locatie.id, organisatie_id=self.org.id)
        item1.deelnemers.append(self.deelnemer1)
        item2.deelnemers.append(self.deelnemer1)
        item2.deelnemers.append(self.deelnemer2)
        db.session.add_all([item1, item2])
        db.session.commit()

        counts = get_usage_counts(Deelnemer, self.org.id)
        self.assertEqual(counts.get(self.deelnemer1.id), 2)
        self.assertEqual(counts.get(self.deelnemer2.id), 1)

    def test_backup_en_restore_inclusief_deelnemers(self):
        """Test dat backup export en restore de deelnemers en koppelingen netjes meeneemt."""
        item = AgendaItem(
            datum=date.today(),
            uur_van="14:00",
            uur_tot="16:00",
            type_id=self.type_met_deelnemers.id,
            locatie_id=self.locatie.id,
            omschrijving="Backup test sessie",
            organisatie_id=self.org.id
        )
        item.deelnemers.append(self.deelnemer1)
        db.session.add(item)
        db.session.commit()

        backup_dict = maak_backup(self.org.id)
        self.assertIn('deelnemers', backup_dict)
        self.assertTrue(any(d['naam'] == 'Anna Peeters' for d in backup_dict['deelnemers']))

        # Check vlag in activity_types
        act_types = backup_dict['activity_types']
        workshop_at = next(at for at in act_types if at['naam'] == 'Workshop Digitaal')
        self.assertTrue(workshop_at['registreer_deelnemers'])

        # Check deelnemers in agenda_items
        agenda_data = backup_dict['agenda_items']
        test_session = next(s for s in agenda_data if s['omschrijving'] == 'Backup test sessie')
        self.assertIn('Anna Peeters', test_session['deelnemer_namen'])

        # Restore test
        json_data = json.dumps(backup_dict).encode('utf-8')
        success, msg = herstel_backup(self.org.id, io.BytesIO(json_data), self.admin_user.id)
        self.assertTrue(success, msg)

        # Controleer herstelde data
        restored_item = AgendaItem.query.filter_by(omschrijving="Backup test sessie", organisatie_id=self.org.id).first()
        self.assertIsNotNone(restored_item)
        self.assertEqual(len(restored_item.deelnemers), 1)
        self.assertEqual(restored_item.deelnemers[0].naam, "Anna Peeters")

    def test_agenda_max_deelnemers_creatie_en_validatie(self):
        """Test aanmaken van een agenda-item met max_deelnemers en validaties."""
        self.login_admin()
        vandaag = date.today()

        # 1. Geldig maximum aantal deelnemers (bijv. 5) met 1 deelnemer
        res = self.client.post('/agenda/nieuw', data={
            'datum': vandaag.isoformat(),
            'uur_van': '10:00',
            'uur_tot': '12:00',
            'type_id': self.type_met_deelnemers.id,
            'locatie_id': self.locatie.id,
            'omschrijving': 'Workshop met max',
            'digidokter_ids': [self.digidokter.id],
            'max_deelnemers': '5',
            'deelnemer_ids': [self.deelnemer1.id]
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        item = AgendaItem.query.filter_by(omschrijving='Workshop met max').first()
        self.assertIsNotNone(item)
        self.assertEqual(item.max_deelnemers, 5)
        self.assertEqual(len(item.deelnemers), 1)

        # 2. Validatiefout: max_deelnemers <= 0
        res_neg = self.client.post('/agenda/nieuw', data={
            'datum': vandaag.isoformat(),
            'uur_van': '13:00',
            'uur_tot': '14:00',
            'type_id': self.type_met_deelnemers.id,
            'locatie_id': self.locatie.id,
            'omschrijving': 'Workshop negatief',
            'digidokter_ids': [self.digidokter.id],
            'max_deelnemers': '0',
            'deelnemer_ids': [self.deelnemer1.id]
        }, follow_redirects=True)
        self.assertEqual(res_neg.status_code, 200)
        self.assertIn('Het maximaal aantal deelnemers moet minimaal 1 zijn.', res_neg.data.decode('utf-8'))
        self.assertIsNone(AgendaItem.query.filter_by(omschrijving='Workshop negatief').first())

        # 3. Validatiefout: ongeldig getal
        res_ongeldig = self.client.post('/agenda/nieuw', data={
            'datum': vandaag.isoformat(),
            'uur_van': '13:00',
            'uur_tot': '14:00',
            'type_id': self.type_met_deelnemers.id,
            'locatie_id': self.locatie.id,
            'omschrijving': 'Workshop ongeldig',
            'digidokter_ids': [self.digidokter.id],
            'max_deelnemers': 'abc',
            'deelnemer_ids': [self.deelnemer1.id]
        }, follow_redirects=True)
        self.assertEqual(res_ongeldig.status_code, 200)
        self.assertIn('Ongeldig getal voor het maximaal aantal deelnemers.', res_ongeldig.data.decode('utf-8'))

        # 4. Validatiefout: aantal deelnemers (2) overschrijdt max_deelnemers (1)
        res_teveel = self.client.post('/agenda/nieuw', data={
            'datum': vandaag.isoformat(),
            'uur_van': '13:00',
            'uur_tot': '14:00',
            'type_id': self.type_met_deelnemers.id,
            'locatie_id': self.locatie.id,
            'omschrijving': 'Workshop te vol',
            'digidokter_ids': [self.digidokter.id],
            'max_deelnemers': '1',
            'deelnemer_ids': [self.deelnemer1.id, self.deelnemer2.id]
        }, follow_redirects=True)
        self.assertEqual(res_teveel.status_code, 200)
        self.assertIn('mag het maximum aantal (1) niet overschrijden', res_teveel.data.decode('utf-8'))
        self.assertIsNone(AgendaItem.query.filter_by(omschrijving='Workshop te vol').first())

        # 5. Geen max_deelnemers opgegeven -> None
        res_leeg = self.client.post('/agenda/nieuw', data={
            'datum': vandaag.isoformat(),
            'uur_van': '15:00',
            'uur_tot': '16:00',
            'type_id': self.type_met_deelnemers.id,
            'locatie_id': self.locatie.id,
            'omschrijving': 'Workshop zonder limiet',
            'digidokter_ids': [self.digidokter.id],
            'max_deelnemers': '',
            'deelnemer_ids': [self.deelnemer1.id]
        }, follow_redirects=True)
        self.assertEqual(res_leeg.status_code, 200)
        item_leeg = AgendaItem.query.filter_by(omschrijving='Workshop zonder limiet').first()
        self.assertIsNotNone(item_leeg)
        self.assertIsNone(item_leeg.max_deelnemers)

    def test_agenda_max_deelnemers_wijzigen_en_reeds_ingeschreven_beperking(self):
        """Test dat max_deelnemers gewijzigd mag worden, maar niet minder mag worden dan reeds ingeschreven deelnemers."""
        self.login_admin()
        vandaag = date.today()

        # Maak item aan met 2 deelnemers en max_deelnemers = 2
        item = AgendaItem(
            datum=vandaag,
            uur_van="10:00",
            uur_tot="12:00",
            type_id=self.type_met_deelnemers.id,
            locatie_id=self.locatie.id,
            omschrijving="Capaciteitstest item",
            max_deelnemers=2,
            organisatie_id=self.org.id
        )
        item.digidokters.append(self.digidokter)
        item.deelnemers.extend([self.deelnemer1, self.deelnemer2])
        db.session.add(item)
        db.session.commit()

        # 1. Probeer max_deelnemers te verlagen naar 1 (minder dan de 2 reeds ingeschreven deelnemers)
        res_verlaag = self.client.post(f'/agenda/{item.id}/wijzig', data={
            'datum': vandaag.isoformat(),
            'uur_van': '10:00',
            'uur_tot': '12:00',
            'type_id': self.type_met_deelnemers.id,
            'locatie_id': self.locatie.id,
            'omschrijving': 'Capaciteitstest item',
            'digidokter_ids': [self.digidokter.id],
            'max_deelnemers': '1',
            'deelnemer_ids': [self.deelnemer1.id, self.deelnemer2.id]
        }, follow_redirects=True)
        self.assertEqual(res_verlaag.status_code, 200)
        self.assertIn('mag niet minder worden dan het aantal deelnemers dat al ingeschreven is (2)', res_verlaag.data.decode('utf-8'))

        # Verifieer dat max_deelnemers niet verlaagd is
        db.session.refresh(item)
        self.assertEqual(item.max_deelnemers, 2)

        # 2. Verhoog max_deelnemers naar 3
        res_verhoog = self.client.post(f'/agenda/{item.id}/wijzig', data={
            'datum': vandaag.isoformat(),
            'uur_van': '10:00',
            'uur_tot': '12:00',
            'type_id': self.type_met_deelnemers.id,
            'locatie_id': self.locatie.id,
            'omschrijving': 'Capaciteitstest item',
            'digidokter_ids': [self.digidokter.id],
            'max_deelnemers': '3',
            'deelnemer_ids': [self.deelnemer1.id, self.deelnemer2.id]
        }, follow_redirects=True)
        self.assertEqual(res_verhoog.status_code, 200)
        db.session.refresh(item)
        self.assertEqual(item.max_deelnemers, 3)

        # 3. Voeg 3e deelnemer toe (mag want max = 3)
        deelnemer3 = Deelnemer(naam="Chantal Derde", actief=True, organisatie_id=self.org.id)
        db.session.add(deelnemer3)
        db.session.commit()

        res_derde = self.client.post(f'/agenda/{item.id}/wijzig', data={
            'datum': vandaag.isoformat(),
            'uur_van': '10:00',
            'uur_tot': '12:00',
            'type_id': self.type_met_deelnemers.id,
            'locatie_id': self.locatie.id,
            'omschrijving': 'Capaciteitstest item',
            'digidokter_ids': [self.digidokter.id],
            'max_deelnemers': '3',
            'deelnemer_ids': [self.deelnemer1.id, self.deelnemer2.id, deelnemer3.id]
        }, follow_redirects=True)
        self.assertEqual(res_derde.status_code, 200)
        db.session.refresh(item)
        self.assertEqual(len(item.deelnemers), 3)

        # 4. Probeer 4e deelnemer toe te voegen terwijl max = 3
        deelnemer4 = Deelnemer(naam="David Vierde", actief=True, organisatie_id=self.org.id)
        db.session.add(deelnemer4)
        db.session.commit()

        res_vierde = self.client.post(f'/agenda/{item.id}/wijzig', data={
            'datum': vandaag.isoformat(),
            'uur_van': '10:00',
            'uur_tot': '12:00',
            'type_id': self.type_met_deelnemers.id,
            'locatie_id': self.locatie.id,
            'omschrijving': 'Capaciteitstest item',
            'digidokter_ids': [self.digidokter.id],
            'max_deelnemers': '3',
            'deelnemer_ids': [self.deelnemer1.id, self.deelnemer2.id, deelnemer3.id, deelnemer4.id]
        }, follow_redirects=True)
        self.assertEqual(res_vierde.status_code, 200)
        self.assertIn('mag het maximum aantal (3) niet overschrijden', res_vierde.data.decode('utf-8'))

        # 5. Verwijder de limiet (leegmaken)
        res_geen_limiet = self.client.post(f'/agenda/{item.id}/wijzig', data={
            'datum': vandaag.isoformat(),
            'uur_van': '10:00',
            'uur_tot': '12:00',
            'type_id': self.type_met_deelnemers.id,
            'locatie_id': self.locatie.id,
            'omschrijving': 'Capaciteitstest item',
            'digidokter_ids': [self.digidokter.id],
            'max_deelnemers': '',
            'deelnemer_ids': [self.deelnemer1.id, self.deelnemer2.id, deelnemer3.id]
        }, follow_redirects=True)
        self.assertEqual(res_geen_limiet.status_code, 200)
        db.session.refresh(item)
        self.assertIsNone(item.max_deelnemers)

    def test_agenda_lijst_en_volzet_indicator(self):
        """Test dat in de agendalijst de teller X/Y en eventuele (volzet) badge correct gerenderd worden."""
        self.login_admin()
        vandaag = date.today()

        # Item 1: volzet (2/2)
        item_vol = AgendaItem(
            datum=vandaag,
            uur_van="09:00",
            uur_tot="10:00",
            type_id=self.type_met_deelnemers.id,
            locatie_id=self.locatie.id,
            omschrijving="Volzette workshop",
            max_deelnemers=2,
            organisatie_id=self.org.id
        )
        item_vol.deelnemers.extend([self.deelnemer1, self.deelnemer2])

        # Item 2: niet volzet (1/3)
        item_vrij = AgendaItem(
            datum=vandaag,
            uur_van="11:00",
            uur_tot="12:00",
            type_id=self.type_met_deelnemers.id,
            locatie_id=self.locatie.id,
            omschrijving="Vrije workshop",
            max_deelnemers=3,
            organisatie_id=self.org.id
        )
        item_vrij.deelnemers.append(self.deelnemer1)

        db.session.add_all([item_vol, item_vrij])
        db.session.commit()

        res = self.client.get('/agenda')
        self.assertEqual(res.status_code, 200)
        data = res.data.decode('utf-8')

        self.assertIn('2 / 2 deelnemers', data)
        self.assertIn('(volzet)', data)
        self.assertIn('1 / 3 deelnemers', data)

    def test_backup_en_restore_inclusief_max_deelnemers(self):
        """Test dat backup export en restore ook max_deelnemers correct bewaart."""
        item = AgendaItem(
            datum=date.today(),
            uur_van="14:00",
            uur_tot="16:00",
            type_id=self.type_met_deelnemers.id,
            locatie_id=self.locatie.id,
            omschrijving="Backup max sessie",
            max_deelnemers=8,
            organisatie_id=self.org.id
        )
        item.deelnemers.append(self.deelnemer1)
        db.session.add(item)
        db.session.commit()

        backup_dict = maak_backup(self.org.id)
        agenda_data = backup_dict['agenda_items']
        test_session = next(s for s in agenda_data if s['omschrijving'] == 'Backup max sessie')
        self.assertEqual(test_session['max_deelnemers'], 8)

        # Restore test
        json_data = json.dumps(backup_dict).encode('utf-8')
        success, msg = herstel_backup(self.org.id, io.BytesIO(json_data), self.admin_user.id)
        self.assertTrue(success, msg)

        restored = AgendaItem.query.filter_by(omschrijving="Backup max sessie", organisatie_id=self.org.id).first()
        self.assertIsNotNone(restored)
        self.assertEqual(restored.max_deelnemers, 8)
        self.assertEqual(len(restored.deelnemers), 1)

