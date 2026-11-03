"""
Unit tests voor utils.backup_handler:
- maak_backup: Eager loading, volledige export van organisatiedata, fallback voor onbekende organisatie.
- herstel_backup:
  - Validatie van JSON structuur en foutafhandeling
  - Herstel van alle entiteiten en foreign key relaties (inclusief mappings)
  - Fallbacks wanneer optionele blokken ontbreken (herkomsten, gender_identities, functies, activity_types, locations)
  - Aanmaken van nieuwe gebruikers en toekennen van functies/telefoonnummer
  - Beheerder-borging voor de hersteller
  - Rollback bij onverwachte databasefouten
"""
import io
import json
from datetime import date, datetime, timezone
from unittest.mock import patch

from tests.base import BaseTestCase
from extensions import db
from models.organisatie import Organisatie, UserOrganisatie
from models.user import User
from models.digidokter import Digidokter
from models.age_category import AgeCategory
from models.device import Device
from models.herkomst import Herkomst
from models.gender_identity import GenderIdentity
from models.functie import Functie
from models.resultaat import Resultaat
from models.activity_type import ActivityType
from models.location import Location
from models.agenda import AgendaItem
from models.registration import Registration
from utils.backup_handler import maak_backup, herstel_backup


class TestBackupHandler(BaseTestCase):

    def test_maak_backup_complete_and_unknown_org(self):
        """Test dat maak_backup alle entiteiten en mappings correct serialiseert."""
        # 1. Maak mappings aan voor leeftijdscategorie en toestel
        parent_cat = AgeCategory(naam="65+", actief=True, volgorde=1, organisatie_id=self.org.id)
        db.session.add(parent_cat)
        db.session.flush()
        self.age_category.mapped_to_id = parent_cat.id

        parent_dev = Device(naam="Tablet", actief=True, volgorde=1, organisatie_id=self.org.id)
        db.session.add(parent_dev)
        db.session.flush()
        self.device.mapped_to_id = parent_dev.id

        # 2. Activiteitstype en Locatie
        act_type = ActivityType(naam="Digidokters Consult", actief=True, volgorde=0, organisatie_id=self.org.id)
        loc = Location(naam="Hoofdbib", actief=True, volgorde=0, gebruikt_voor_consultaties=True, organisatie_id=self.org.id)
        db.session.add_all([act_type, loc])
        db.session.flush()

        # 3. AgendaItem met gekoppelde digidokter
        agenda_item = AgendaItem(
            datum=date(2026, 11, 10),
            uur_van="10:00",
            uur_tot="12:00",
            type_id=act_type.id,
            locatie_id=loc.id,
            omschrijving="Wekelijkse consultatie",
            organisatie_id=self.org.id
        )
        agenda_item.digidokters = [self.digidokter]
        db.session.add(agenda_item)

        # 4. Registratie met alle relaties
        reg = Registration(
            registratienummer=101,
            datum=date(2026, 11, 10),
            client="Jan Janssen",
            nieuwe_klant=True,
            herkomst_id=self.herkomst.id,
            gender_identity_id=self.gender_man.id,
            onderwerp="Hulp met e-mail instellen",
            resultaat_id=self.resultaat_beantwoord.id,
            digidokter_id=self.digidokter.id,
            leeftijdscategorie_id=self.age_category.id,
            toestel_id=self.device.id,
            locatie_id=loc.id,
            aangemaakt_door_id=self.admin_user.id,
            organisatie_id=self.org.id
        )
        db.session.add(reg)

        # 5. Gebruiker met telefoonnummer en functie
        self.admin_user.telefoonnummer = "0470123456"
        self.admin_user.functies.append(self.functie_digidokter)
        db.session.commit()

        # Test export
        backup_data = maak_backup(self.org.id)
        self.assertEqual(backup_data['organisatie']['naam'], "Digidokters Test")
        self.assertIn('metadata', backup_data)
        self.assertGreaterEqual(len(backup_data['users']), 1)
        self.assertIn("0470123456", [u.get('telefoonnummer') for u in backup_data['users']])
        self.assertGreaterEqual(len(backup_data['registrations']), 1)
        self.assertEqual(backup_data['registrations'][0]['client'], "Jan Janssen")
        self.assertEqual(backup_data['registrations'][0]['locatie_naam'], "Hoofdbib")
        self.assertGreaterEqual(len(backup_data['agenda_items']), 1)
        self.assertEqual(backup_data['agenda_items'][0]['digidokter_namen'], [self.digidokter.naam])

        # Test onbekende organisatie fallback
        unknown_data = maak_backup(999999)
        self.assertEqual(unknown_data['organisatie']['naam'], 'Onbekend')
        self.assertEqual(unknown_data['organisatie']['slug'], 'onbekend')

    def test_herstel_backup_invalid_json(self):
        """Test dat ongeldige JSON fatsoenlijk wordt afgehandeld met een foutmelding."""
        bad_stream = io.BytesIO(b"DIT_IS_GEEN_JSON{")
        succes, msg = herstel_backup(self.org.id, bad_stream, self.admin_user.id)
        self.assertFalse(succes)
        self.assertIn("Fout bij het lezen van het JSON-bestand", msg)

    def test_herstel_backup_missing_required_keys(self):
        """Test dat een backupbestand zonder vereiste keys wordt geweigerd."""
        incomplete_json = io.BytesIO(json.dumps({'organisatie': {'naam': 'Test'}}).encode('utf-8'))
        succes, msg = herstel_backup(self.org.id, incomplete_json, self.admin_user.id)
        self.assertFalse(succes)
        self.assertIn("Ongeldig backup-bestand", msg)

    def test_herstel_backup_full_flow(self):
        """Test het herstellen van een complete backup inclusief mappings, nieuwe users en agenda-items."""
        # Creëer een losstaande gebruiker zonder UserOrganisatie om de hersteller-logica te testen
        hersteller = User(
            naam="NieuweHersteller",
            email="hersteller@test.com",
            wachtwoord_hash="hash123",
            rol="medewerker",
            actief=True
        )
        db.session.add(hersteller)
        db.session.commit()

        backup_payload = {
            'organisatie': {'naam': 'Test Restore Org', 'slug': 'test-restore-org'},
            'users': [
                {
                    'naam': 'AdminMark',
                    'email': 'admin@test.com',
                    'telefoonnummer': '0471999888',
                    'wachtwoord_hash': 'existinghash',
                    'rol': 'beheerder',
                    'actief': True,
                    'membership_rol': 'beheerder',
                    'membership_actief': True,
                    'functies': ['Digidokter', 'Digihelper']
                },
                {
                    'naam': 'NieuweVrijwilliger',
                    'email': 'vrijwilliger@test.com',
                    'telefoonnummer': '0472111222',
                    'wachtwoord_hash': 'newhash123',
                    'rol': 'medewerker',
                    'actief': True,
                    'membership_rol': 'medewerker',
                    'membership_actief': True,
                    'functies': ['Digidokter']
                }
            ],
            'digidokters': [
                {'naam': 'Dokter Bob', 'actief': True, 'volgorde': 0},
                {'naam': 'Dokter Alice', 'actief': True, 'volgorde': 1}
            ],
            'age_categories': [
                {'naam': 'Volwassenen', 'actief': True, 'volgorde': 0, 'mapped_to_naam': None},
                {'naam': 'Senioren', 'actief': True, 'volgorde': 1, 'mapped_to_naam': 'Volwassenen'}
            ],
            'devices': [
                {'naam': 'Smartphone', 'actief': True, 'volgorde': 0, 'mapped_to_naam': None},
                {'naam': 'iPhone', 'actief': True, 'volgorde': 1, 'mapped_to_naam': 'Smartphone'}
            ],
            'herkomsten': [
                {'naam': 'Buurthuis', 'actief': True, 'volgorde': 0}
            ],
            'gender_identities': [
                {'naam': 'Man', 'actief': True, 'volgorde': 0},
                {'naam': 'Vrouw', 'actief': True, 'volgorde': 1}
            ],
            'functies': [
                {'naam': 'Digidokter', 'actief': True, 'volgorde': 0},
                {'naam': 'Digihelper', 'actief': True, 'volgorde': 1}
            ],
            'resultaten': [
                {'omschrijving': 'Vraag beantwoord', 'actief': True, 'volgorde': 0}
            ],
            'activity_types': [
                {'naam': 'Digipunt Sessie', 'actief': True, 'volgorde': 0}
            ],
            'locations': [
                {'naam': 'Gemeentehuis', 'actief': True, 'volgorde': 0, 'gebruikt_voor_consultaties': True}
            ],
            'agenda_items': [
                {
                    'datum': '2026-12-01',
                    'uur_van': '14:00',
                    'uur_tot': '16:00',
                    'type_name': 'Digipunt Sessie',
                    'locatie_name': 'Gemeentehuis',
                    'omschrijving': 'Open inloopmoment',
                    'digidokter_namen': ['Dokter Bob', 'Dokter Alice']
                }
            ],
            'registrations': [
                {
                    'registratienummer': 201,
                    'datum': '2026-12-01',
                    'client': 'Klant 1',
                    'nieuwe_klant': True,
                    'herkomst': 'Buurthuis',
                    'geslacht': 'Man',
                    'onderwerp': 'Whatsappen',
                    'resultaat_omschrijving': 'Vraag beantwoord',
                    'digidokter_naam': 'Dokter Bob',
                    'leeftijdscategorie_naam': 'Senioren',
                    'toestel_naam': 'iPhone',
                    'aangemaakt_door_naam': 'NieuweVrijwilliger',
                    'aangemaakt_op': '2026-12-01T14:30:00',
                    'gewijzigd_op': '2026-12-01T14:35:00'
                }
            ]
        }

        stream = io.BytesIO(json.dumps(backup_payload).encode('utf-8'))
        # 1. Herstel waarbij hersteller (self.admin_user) al een UserOrganisatie heeft -> covert regels 433-434
        succes, msg = herstel_backup(self.org.id, stream, self.admin_user.id)
        self.assertTrue(succes)
        self.assertIn("succesvol hersteld", msg)

        # 2. Herstel waarbij hersteller nog GEEN UserOrganisatie heeft -> covert regels 439-445
        stream_nieuw = io.BytesIO(json.dumps(backup_payload).encode('utf-8'))
        succes_nieuw, msg_nieuw = herstel_backup(self.org.id, stream_nieuw, hersteller.id)
        self.assertTrue(succes_nieuw)
        self.assertIn("succesvol hersteld", msg_nieuw)

        # Verifieer mappings
        senioren = AgeCategory.query.filter_by(organisatie_id=self.org.id, naam='Senioren').first()
        volwassenen = AgeCategory.query.filter_by(organisatie_id=self.org.id, naam='Volwassenen').first()
        self.assertIsNotNone(senioren)
        self.assertEqual(senioren.mapped_to_id, volwassenen.id)

        iphone = Device.query.filter_by(organisatie_id=self.org.id, naam='iPhone').first()
        smartphone = Device.query.filter_by(organisatie_id=self.org.id, naam='Smartphone').first()
        self.assertIsNotNone(iphone)
        self.assertEqual(iphone.mapped_to_id, smartphone.id)

        # Verifieer nieuwe gebruiker en functies
        nieuwe_user = User.query.filter_by(email='vrijwilliger@test.com').first()
        self.assertIsNotNone(nieuwe_user)
        self.assertEqual(nieuwe_user.telefoonnummer, '0472111222')
        self.assertIn('Digidokter', [f.naam for f in nieuwe_user.functies])

        # Verifieer hersteller lidmaatschap als beheerder
        uo_h = UserOrganisatie.query.filter_by(user_id=hersteller.id, organisatie_id=self.org.id).first()
        self.assertIsNotNone(uo_h)
        self.assertEqual(uo_h.rol, 'beheerder')

        # Verifieer agenda items en gekoppelde digidokters
        agenda = AgendaItem.query.filter_by(organisatie_id=self.org.id).first()
        self.assertIsNotNone(agenda)
        self.assertEqual(len(agenda.digidokters), 2)

        # Verifieer registratie
        reg = Registration.query.filter_by(organisatie_id=self.org.id, registratienummer=201).first()
        self.assertIsNotNone(reg)
        self.assertEqual(reg.client, 'Klant 1')
        self.assertEqual(reg.digidokter.naam, 'Dokter Bob')
        self.assertEqual(reg.leeftijdscategorie.naam, 'Senioren')

    def test_herstel_backup_fallbacks_when_optional_blocks_missing(self):
        """Test dat fallbacks correct ingevuld worden als optionele secties ontbreken."""
        minimal_payload = {
            'organisatie': {'naam': 'Fallback Org', 'slug': 'fallback-org'},
            'users': [],
            'digidokters': [{'naam': 'Alleen Dokter', 'actief': True, 'volgorde': 0}],
            'age_categories': [{'naam': 'Alle Leeftijden', 'actief': True, 'volgorde': 0}],
            'devices': [{'naam': 'Alle Toestellen', 'actief': True, 'volgorde': 0}],
            # herkomsten, gender_identities, functies, activity_types, locations ontbreken expres!
            'registrations': [
                {
                    'registratienummer': 301,
                    'datum': '2026-11-05',
                    'client': 'Piet',
                    'nieuwe_klant': False,
                    'herkomst': 'Mondeling advies',
                    'geslacht': 'Vrouw',
                    'onderwerp': 'Test',
                    'digidokter_naam': 'Onbekende Dokter',  # triggert fallback naar eerste digidokter
                    'leeftijdscategorie_naam': 'Onbekend',   # triggert fallback naar eerste age category
                    'toestel_naam': 'Onbekend'              # triggert fallback naar eerste toestel
                },
                {
                    'registratienummer': 302,
                    'datum': '2026-11-05',
                    'client': 'Klaas',
                    'nieuwe_klant': False,
                    'herkomst': 'nan',                      # moet genegeerd worden door herkomst set
                    'geslacht': None,
                    'onderwerp': 'Test 2'
                }
            ]
        }

        stream = io.BytesIO(json.dumps(minimal_payload).encode('utf-8'))
        succes, msg = herstel_backup(self.org.id, stream, self.admin_user.id)
        self.assertTrue(succes)

        # 1. Fallback herkomsten: 'Mondeling advies' moet aangemaakt zijn, 'nan' niet
        herkomst_mondeling = Herkomst.query.filter_by(organisatie_id=self.org.id, naam='Mondeling advies').first()
        self.assertIsNotNone(herkomst_mondeling)
        herkomst_nan = Herkomst.query.filter_by(organisatie_id=self.org.id, naam='nan').first()
        self.assertIsNone(herkomst_nan)

        # 2. Fallback gender identities: ['Man', 'Vrouw']
        genders = [g.naam for g in GenderIdentity.query.filter_by(organisatie_id=self.org.id).all()]
        self.assertIn('Man', genders)
        self.assertIn('Vrouw', genders)

        # 3. Fallback functies: ['Digidokter', 'Digihelper', 'Lesgever']
        functies = [f.naam for f in Functie.query.filter_by(organisatie_id=self.org.id).all()]
        self.assertIn('Digidokter', functies)
        self.assertIn('Digihelper', functies)
        self.assertIn('Lesgever', functies)

        # 4. Fallback activity types
        types = [t.naam for t in ActivityType.query.filter_by(organisatie_id=self.org.id).all()]
        self.assertIn('Digidokters', types)
        self.assertIn('Digicafé', types)

        # 5. Fallback locations
        locs = [l.naam for l in Location.query.filter_by(organisatie_id=self.org.id).all()]
        self.assertIn('Bib Londerzeel', locs)

        # 6. Registratie 301 heeft fallback ID's gekregen
        reg = Registration.query.filter_by(organisatie_id=self.org.id, registratienummer=301).first()
        self.assertIsNotNone(reg)
        self.assertEqual(reg.digidokter.naam, 'Alleen Dokter')
        self.assertEqual(reg.leeftijdscategorie.naam, 'Alle Leeftijden')
        self.assertEqual(reg.toestel.naam, 'Alle Toestellen')

    def test_herstel_backup_exception_rollback(self):
        """Test dat bij een database-exceptie tijdens herstel een rollback plaatsvindt en False geretourneerd wordt."""
        valid_payload = {
            'organisatie': {'naam': 'Org', 'slug': 'org'},
            'users': [],
            'digidokters': [],
            'age_categories': [],
            'devices': [],
            'registrations': []
        }
        stream = io.BytesIO(json.dumps(valid_payload).encode('utf-8'))

        with patch('utils.backup_handler.Digidokter') as mock_digidokter:
            mock_digidokter.side_effect = Exception("Gesimuleerde database fout")
            # We trigger the exception by having an item in digidokters
            payload_with_item = dict(valid_payload)
            payload_with_item['digidokters'] = [{'naam': 'Test'}]
            stream_err = io.BytesIO(json.dumps(payload_with_item).encode('utf-8'))

            succes, msg = herstel_backup(self.org.id, stream_err, self.admin_user.id)
            self.assertFalse(succes)
            self.assertIn("Fout tijdens het herstellen van de data: Gesimuleerde database fout", msg)
