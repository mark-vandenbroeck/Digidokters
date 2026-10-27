import json
import unittest
from datetime import date, datetime, timedelta, timezone
from flask import g
from tests.base import BaseTestCase
from extensions import db
from models.agenda import AgendaItem, AgendaItemLock
from models.activity_type import ActivityType
from models.location import Location
from models.digidokter import Digidokter
from models.audit import AuditLog


class TestAgendaLockAndAudit(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.type_workshop = ActivityType(naam="Workshop AI", actief=True, organisatie_id=self.org.id)
        self.locatie1 = Location(naam="Bibliotheek Centrum", actief=True, organisatie_id=self.org.id)
        self.digidokter2 = Digidokter(naam="Tweede Digidokter", actief=True, organisatie_id=self.org.id)

        db.session.add_all([self.type_workshop, self.locatie1, self.digidokter2])
        db.session.commit()

    def _reset_request_user(self):
        """Wist g._login_user zodat een nieuwe testclient zijn eigen sessie en gebruiker laadt."""
        if hasattr(g, '_login_user'):
            delattr(g, '_login_user')

    def login_admin(self, client=None):
        self._reset_request_user()
        c = client or self.client
        with c.session_transaction() as sess:
            sess['organisatie_id'] = self.org.id
        return c.post('/login', data={
            'email': 'admin@test.com',
            'wachtwoord': 'password123'
        }, follow_redirects=True)

    def login_medewerker(self, client=None):
        self._reset_request_user()
        c = client or self.client
        with c.session_transaction() as sess:
            sess['organisatie_id'] = self.org.id
        return c.post('/login', data={
            'email': 'tim@test.com',
            'wachtwoord': 'password123'
        }, follow_redirects=True)

    def test_audit_log_tracks_digidokters_on_agenda_creation(self):
        """Test dat bij het toevoegen van een agenda-item gekoppelde digidokters in het AuditLog komen."""
        self.login_admin()

        post_data = {
            'datum': date.today().isoformat(),
            'uur_van': '10:00',
            'uur_tot': '12:00',
            'type_id': self.type_workshop.id,
            'locatie_id': self.locatie1.id,
            'omschrijving': 'Audit test activiteit',
            'digidokter_ids': [self.digidokter.id, self.digidokter2.id]
        }

        res = self.client.post('/agenda/nieuw', data=post_data, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        item = AgendaItem.query.filter_by(omschrijving='Audit test activiteit').first()
        self.assertIsNotNone(item)
        self.assertEqual(len(item.digidokters), 2)

        # Controleer AuditLog entry
        log_entry = AuditLog.query.filter_by(
            tabel='agenda_items',
            record_id=item.id,
            operatie='CREATE'
        ).first()
        self.assertIsNotNone(log_entry, "Er moet een CREATE AuditLog zijn voor het nieuwe agenda-item.")
        details = json.loads(log_entry.details)
        self.assertIn('nieuwe_waarden', details)
        self.assertIn('digidokters', details['nieuwe_waarden'])
        self.assertIn(self.digidokter.naam, details['nieuwe_waarden']['digidokters'])
        self.assertIn(self.digidokter2.naam, details['nieuwe_waarden']['digidokters'])

    def test_audit_log_tracks_digidokters_on_agenda_update(self):
        """Test dat bij het wijzigen van digidokters op een agenda-item een UPDATE AuditLog ontstaat."""
        self.login_admin()

        # Maak item aan met 1 digidokter
        item = AgendaItem(
            datum=date.today(),
            uur_van='10:00',
            uur_tot='12:00',
            type_id=self.type_workshop.id,
            locatie_id=self.locatie1.id,
            omschrijving='Oorspronkelijke omschrijving',
            organisatie_id=self.org.id,
            gewijzigd_op=datetime.now(timezone.utc)
        )
        item.digidokters = [self.digidokter]
        db.session.add(item)
        db.session.commit()
        item_id = item.id

        # Update via POST naar /agenda/<item_id>/wijzig: vervang digidokter door digidokter2
        post_data = {
            'datum': date.today().isoformat(),
            'uur_van': '10:00',
            'uur_tot': '12:00',
            'type_id': self.type_workshop.id,
            'locatie_id': self.locatie1.id,
            'omschrijving': 'Oorspronkelijke omschrijving',  # Geen wijziging in scalar velden
            'digidokter_ids': [self.digidokter2.id]
        }
        res = self.client.post(f'/agenda/{item_id}/wijzig', data=post_data, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        # Controleer update log
        update_log = AuditLog.query.filter_by(
            tabel='agenda_items',
            record_id=item_id,
            operatie='UPDATE'
        ).order_by(AuditLog.id.desc()).first()

        self.assertIsNotNone(update_log, "Er moet een UPDATE AuditLog zijn na het wijzigen van aanwezigheden.")
        details = json.loads(update_log.details)
        self.assertIn('oude_waarden', details)
        self.assertIn('nieuwe_waarden', details)
        self.assertIn('digidokters', details['oude_waarden'])
        self.assertIn('digidokters', details['nieuwe_waarden'])
        self.assertIn(self.digidokter.naam, details['oude_waarden']['digidokters'])
        self.assertIn(self.digidokter2.naam, details['nieuwe_waarden']['digidokters'])

    def test_concurrent_editing_lock_and_warning(self):
        """Test dat als Gebruiker 1 een item opent, Gebruiker 2 een waarschuwing krijgt en checkboxes disabled zijn."""
        item = AgendaItem(
            datum=date.today(),
            uur_van='10:00',
            uur_tot='12:00',
            type_id=self.type_workshop.id,
            locatie_id=self.locatie1.id,
            omschrijving='Item voor lock test',
            organisatie_id=self.org.id
        )
        item.digidokters = [self.digidokter]
        db.session.add(item)
        db.session.commit()
        item_id = item.id

        # Twee afzonderlijke clients simuleren twee verschillende browsersessies
        client_admin = self.app.test_client()
        client_medewerker = self.app.test_client()

        self.login_admin(client=client_admin)
        self.login_medewerker(client=client_medewerker)

        # Stap 1: Admin opent het item om te bewerken
        self._reset_request_user()
        res1 = client_admin.get(f'/agenda/{item_id}/wijzig')
        self.assertEqual(res1.status_code, 200)
        self.assertNotIn('Aanwezigheden voor deze activiteit kunnen momenteel niet gewijzigd worden', res1.get_data(as_text=True))

        # Controleer dat de lock in de DB staat voor Admin
        lock = AgendaItemLock.query.filter_by(agenda_item_id=item_id).first()
        self.assertIsNotNone(lock)
        self.assertEqual(lock.user_id, self.admin_user.id)

        # Stap 2: Medewerker opent tegelijkertijd hetzelfde item
        self._reset_request_user()
        res2 = client_medewerker.get(f'/agenda/{item_id}/wijzig')
        self.assertEqual(res2.status_code, 200)
        content2 = res2.get_data(as_text=True)

        # Medewerker MOET de waarschuwing zien met de naam van Admin
        expected_warning = f"Aanwezigheden voor deze activiteit kunnen momenteel niet gewijzigd worden want gebruiker {self.admin_user.naam} is ze aan het wijzigen. Probeer later opnieuw."
        self.assertIn(expected_warning, content2)
        # En de checkboxes moeten 'disabled' bevatten
        self.assertIn('disabled', content2)

    def test_concurrent_editing_prevents_overwriting_attendance(self):
        """Test dat als Gebruiker 2 het formulier indient terwijl Gebruiker 1 de lock heeft, aanwezigheden bewaard blijven."""
        item = AgendaItem(
            datum=date.today(),
            uur_van='10:00',
            uur_tot='12:00',
            type_id=self.type_workshop.id,
            locatie_id=self.locatie1.id,
            omschrijving='Item beschermd tegen overschrijving',
            organisatie_id=self.org.id
        )
        item.digidokters = [self.digidokter]
        db.session.add(item)
        db.session.commit()
        item_id = item.id

        client_admin = self.app.test_client()
        client_medewerker = self.app.test_client()

        self.login_admin(client=client_admin)
        self.login_medewerker(client=client_medewerker)

        # Admin claimt de lock
        self._reset_request_user()
        client_admin.get(f'/agenda/{item_id}/wijzig')

        # Medewerker probeert POST met andere omschrijving en zónder digidokters
        self._reset_request_user()
        post_data = {
            'datum': date.today().isoformat(),
            'uur_van': '11:00',
            'uur_tot': '13:00',
            'type_id': self.type_workshop.id,
            'locatie_id': self.locatie1.id,
            'omschrijving': 'Aangepast door medewerker',
            'digidokter_ids': []  # Leeg, zou normaal de digidokter verwijderen
        }
        res = client_medewerker.post(f'/agenda/{item_id}/wijzig', data=post_data, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn('Aanwezigheden zijn ongewijzigd gebleven', res.get_data(as_text=True))

        # Controleer dat de digidokter van Admin NIET is overschreven!
        db.session.expire_all()
        item_check = db.session.get(AgendaItem, item_id)
        self.assertEqual(item_check.omschrijving, 'Aangepast door medewerker')
        self.assertEqual([d.id for d in item_check.digidokters], [self.digidokter.id])

    def test_lock_release_on_save_and_cancel(self):
        """Test dat de lock correct wordt vrijgegeven bij annuleren en bij opslaan."""
        item = AgendaItem(
            datum=date.today(),
            uur_van='10:00',
            uur_tot='12:00',
            type_id=self.type_workshop.id,
            locatie_id=self.locatie1.id,
            omschrijving='Lock release test',
            organisatie_id=self.org.id
        )
        db.session.add(item)
        db.session.commit()
        item_id = item.id

        client_admin = self.app.test_client()
        client_medewerker = self.app.test_client()

        self.login_admin(client=client_admin)
        self.login_medewerker(client=client_medewerker)

        # 1. Admin claims lock
        self._reset_request_user()
        client_admin.get(f'/agenda/{item_id}/wijzig')
        self.assertIsNotNone(AgendaItemLock.query.filter_by(agenda_item_id=item_id).first())

        # Admin annuleert
        self._reset_request_user()
        res_cancel = client_admin.get(f'/agenda/{item_id}/annuleren', follow_redirects=True)
        self.assertEqual(res_cancel.status_code, 200)
        self.assertIsNone(AgendaItemLock.query.filter_by(agenda_item_id=item_id).first())

        # Nu kan Medewerker bewerken zonder waarschuwing en verkrijgt Medewerker de lock
        self._reset_request_user()
        res_med = client_medewerker.get(f'/agenda/{item_id}/wijzig')
        self.assertNotIn('Aanwezigheden voor deze activiteit kunnen momenteel niet gewijzigd worden', res_med.get_data(as_text=True))
        lock_med = AgendaItemLock.query.filter_by(agenda_item_id=item_id).first()
        self.assertIsNotNone(lock_med)
        self.assertEqual(lock_med.user_id, self.medewerker_user.id)

        # Medewerker slaat op -> lock vrijgegeven
        self._reset_request_user()
        post_data = {
            'datum': date.today().isoformat(),
            'uur_van': '10:00',
            'uur_tot': '12:00',
            'type_id': self.type_workshop.id,
            'locatie_id': self.locatie1.id,
            'omschrijving': 'Opgeslagen door medewerker',
            'digidokter_ids': [self.digidokter.id]
        }
        res_save = client_medewerker.post(f'/agenda/{item_id}/wijzig', data=post_data, follow_redirects=True)
        self.assertEqual(res_save.status_code, 200)
        self.assertIsNone(AgendaItemLock.query.filter_by(agenda_item_id=item_id).first())

    def test_expired_lock_is_automatically_cleaned_up(self):
        """Test dat een verlopen lock (ouder dan 5 minuten) automatisch overgenomen kan worden."""
        item = AgendaItem(
            datum=date.today(),
            uur_van='10:00',
            uur_tot='12:00',
            type_id=self.type_workshop.id,
            locatie_id=self.locatie1.id,
            omschrijving='Verlopen lock test',
            organisatie_id=self.org.id
        )
        db.session.add(item)
        db.session.commit()
        item_id = item.id

        # Maak handmatig een verlopen lock aan
        old_lock = AgendaItemLock(
            agenda_item_id=item_id,
            user_id=self.admin_user.id,
            user_naam=self.admin_user.naam,
            locked_at=datetime.now(timezone.utc) - timedelta(minutes=10),
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=5)
        )
        db.session.add(old_lock)
        db.session.commit()

        client_medewerker = self.app.test_client()
        self.login_medewerker(client=client_medewerker)

        # Medewerker bezoekt de pagina
        self._reset_request_user()
        res = client_medewerker.get(f'/agenda/{item_id}/wijzig')
        self.assertEqual(res.status_code, 200)
        # Geen waarschuwing want de lock was verlopen
        self.assertNotIn('Aanwezigheden voor deze activiteit kunnen momenteel niet gewijzigd worden', res.get_data(as_text=True))

        # De actieve lock is nu van Medewerker
        new_lock = AgendaItemLock.query.filter_by(agenda_item_id=item_id).first()
        self.assertIsNotNone(new_lock)
        self.assertEqual(new_lock.user_id, self.medewerker_user.id)
