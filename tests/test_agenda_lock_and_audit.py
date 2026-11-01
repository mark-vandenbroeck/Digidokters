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


from unittest.mock import patch
from utils.agenda_lock import (
    clean_expired_locks,
    get_active_lock,
    acquire_or_check_lock,
    release_lock
)


class TestAgendaLockUnit(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.type_workshop = ActivityType(naam="Workshop AI", actief=True, organisatie_id=self.org.id)
        self.locatie1 = Location(naam="Bibliotheek Centrum", actief=True, organisatie_id=self.org.id)
        db.session.add_all([self.type_workshop, self.locatie1])
        db.session.commit()

        self.item = AgendaItem(
            datum=date.today(),
            uur_van='10:00',
            uur_tot='12:00',
            type_id=self.type_workshop.id,
            locatie_id=self.locatie1.id,
            omschrijving='Unit lock test item',
            organisatie_id=self.org.id
        )
        self.item2 = AgendaItem(
            datum=date.today(),
            uur_van='14:00',
            uur_tot='16:00',
            type_id=self.type_workshop.id,
            locatie_id=self.locatie1.id,
            omschrijving='Unit lock test item 2',
            organisatie_id=self.org.id
        )
        db.session.add_all([self.item, self.item2])
        db.session.commit()

    def test_clean_expired_locks_success_and_exception(self):
        now = datetime.now(timezone.utc)
        expired_lock = AgendaItemLock(
            agenda_item_id=self.item.id,
            user_id=self.admin_user.id,
            user_naam=self.admin_user.naam,
            locked_at=now - timedelta(minutes=10),
            expires_at=now - timedelta(minutes=1)
        )
        active_lock = AgendaItemLock(
            agenda_item_id=self.item2.id,
            user_id=self.medewerker_user.id,
            user_naam=self.medewerker_user.naam,
            locked_at=now,
            expires_at=now + timedelta(minutes=5)
        )
        db.session.add_all([expired_lock, active_lock])
        db.session.commit()

        clean_expired_locks()
        self.assertIsNone(AgendaItemLock.query.filter_by(agenda_item_id=self.item.id).first())
        self.assertIsNotNone(AgendaItemLock.query.filter_by(agenda_item_id=self.item2.id).first())

        # Test exception path (rollback)
        with patch.object(db.session, 'commit', side_effect=Exception('DB Error')):
            with patch.object(db.session, 'rollback') as mock_rollback:
                clean_expired_locks()
                mock_rollback.assert_called_once()

    def test_get_active_lock_all_paths(self):
        # 1. Geen lock
        self.assertIsNone(get_active_lock(self.item.id))

        # 2. Actieve lock
        now = datetime.now(timezone.utc)
        lock = AgendaItemLock(
            agenda_item_id=self.item.id,
            user_id=self.admin_user.id,
            user_naam=self.admin_user.naam,
            locked_at=now,
            expires_at=now + timedelta(minutes=5)
        )
        db.session.add(lock)
        db.session.commit()

        retrieved = get_active_lock(self.item.id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.id, lock.id)

        # 3. Verlopen lock (met clean_expired_locks gepatcht om regels 21-27 te testen)
        lock.expires_at = now - timedelta(minutes=2)
        db.session.commit()

        with patch('utils.agenda_lock.clean_expired_locks'):
            expired_retrieved = get_active_lock(self.item.id)
            self.assertIsNone(expired_retrieved)
            self.assertIsNone(AgendaItemLock.query.filter_by(agenda_item_id=self.item.id).first())

        # 4. Verlopen lock met rollback bij fout tijdens delete
        lock2 = AgendaItemLock(
            agenda_item_id=self.item.id,
            user_id=self.admin_user.id,
            user_naam=self.admin_user.naam,
            locked_at=now - timedelta(minutes=10),
            expires_at=now - timedelta(minutes=2)
        )
        db.session.add(lock2)
        db.session.commit()

        with patch('utils.agenda_lock.clean_expired_locks'):
            with patch.object(db.session, 'commit', side_effect=Exception("Delete error")):
                with patch.object(db.session, 'rollback') as mock_rollback:
                    res = get_active_lock(self.item.id)
                    self.assertIsNone(res)
                    self.assertTrue(mock_rollback.called)

    def test_acquire_or_check_lock_all_paths(self):
        now = datetime.now(timezone.utc)

        # 1. Geen lock -> claim nieuwe lock
        can_edit, lock = acquire_or_check_lock(self.item.id, self.admin_user, timeout_minutes=5)
        self.assertTrue(can_edit)
        self.assertEqual(lock.user_id, self.admin_user.id)
        self.assertEqual(lock.user_naam, self.admin_user.naam)

        # 2. Reeds in bezit van zelfde gebruiker -> verleng lock
        can_edit2, lock2 = acquire_or_check_lock(self.item.id, self.admin_user, timeout_minutes=15)
        self.assertTrue(can_edit2)
        self.assertEqual(lock2.id, lock.id)

        # 2b. Reeds in bezit van zelfde gebruiker met commit fout -> rollback en alsnog True
        with patch.object(db.session, 'commit', side_effect=Exception("Extend error")):
            with patch.object(db.session, 'rollback') as mock_rollback:
                can_edit_err, lock_err = acquire_or_check_lock(self.item.id, self.admin_user, timeout_minutes=15)
                self.assertTrue(can_edit_err)
                self.assertTrue(mock_rollback.called)

        # 3. Andere gebruiker probeert actieve lock te claimen -> geweigerd
        can_edit_other, lock_other = acquire_or_check_lock(self.item.id, self.medewerker_user)
        self.assertFalse(can_edit_other)
        self.assertEqual(lock_other.user_id, self.admin_user.id)

        # 4. Verlopen lock van andere gebruiker overnemen (clean_expired_locks gepatcht om regels 76-87 te triggeren)
        lock.expires_at = now - timedelta(minutes=1)
        db.session.commit()

        with patch('utils.agenda_lock.clean_expired_locks'):
            can_edit_takeover, lock_takeover = acquire_or_check_lock(self.item.id, self.medewerker_user, timeout_minutes=5)
            self.assertTrue(can_edit_takeover)
            self.assertEqual(lock_takeover.user_id, self.medewerker_user.id)
            self.assertEqual(lock_takeover.user_naam, self.medewerker_user.naam)

        # 4b. Verlopen lock overnemen met commit fout -> rollback
        lock_takeover.expires_at = now - timedelta(minutes=1)
        db.session.commit()
        with patch('utils.agenda_lock.clean_expired_locks'):
            with patch.object(db.session, 'commit', side_effect=Exception("Takeover error")):
                with patch.object(db.session, 'rollback') as mock_rollback:
                    can_edit_to_err, lock_to_err = acquire_or_check_lock(self.item.id, self.admin_user)
                    self.assertTrue(can_edit_to_err)
                    self.assertTrue(mock_rollback.called)

        # 5. Nieuwe lock claimen race condition: fout bij add/commit -> herprobeer ophalen en weiger
        AgendaItemLock.query.delete()
        db.session.commit()

        other_user_lock = AgendaItemLock(
            agenda_item_id=self.item.id,
            user_id=self.medewerker_user.id,
            user_naam=self.medewerker_user.naam,
            locked_at=now,
            expires_at=now + timedelta(minutes=5)
        )

        with patch('utils.agenda_lock.clean_expired_locks'):
            with patch.object(AgendaItemLock, 'query') as mock_query:
                mock_query.filter_by.return_value.first.side_effect = [None, other_user_lock]
                with patch.object(db.session, 'commit', side_effect=Exception("Simulated unique constraint error")):
                    can_edit_race, lock_race = acquire_or_check_lock(self.item.id, self.admin_user)
                    self.assertFalse(can_edit_race)
                    self.assertIsNotNone(lock_race)
                    self.assertEqual(lock_race.user_id, self.medewerker_user.id)

    def test_release_lock_all_paths(self):
        now = datetime.now(timezone.utc)
        lock = AgendaItemLock(
            agenda_item_id=self.item.id,
            user_id=self.admin_user.id,
            user_naam=self.admin_user.naam,
            locked_at=now,
            expires_at=now + timedelta(minutes=5)
        )
        db.session.add(lock)
        db.session.commit()

        # 1. Release met verkeerde user_id -> False, lock blijft bestaan
        released_wrong = release_lock(self.item.id, user_id=self.medewerker_user.id)
        self.assertFalse(released_wrong)
        self.assertIsNotNone(AgendaItemLock.query.filter_by(agenda_item_id=self.item.id).first())

        # 2. Release met juiste user_id -> True, lock verwijderd
        released_right = release_lock(self.item.id, user_id=self.admin_user.id)
        self.assertTrue(released_right)
        self.assertIsNone(AgendaItemLock.query.filter_by(agenda_item_id=self.item.id).first())

        # 3. Release zonder user_id (None)
        lock2 = AgendaItemLock(
            agenda_item_id=self.item.id,
            user_id=self.medewerker_user.id,
            user_naam=self.medewerker_user.naam,
            locked_at=now,
            expires_at=now + timedelta(minutes=5)
        )
        db.session.add(lock2)
        db.session.commit()

        released_any = release_lock(self.item.id, user_id=None)
        self.assertTrue(released_any)
        self.assertIsNone(AgendaItemLock.query.filter_by(agenda_item_id=self.item.id).first())

        # 4. Release foutafhandeling (rollback)
        with patch.object(db.session, 'commit', side_effect=Exception("Release error")):
            with patch.object(db.session, 'rollback') as mock_rollback:
                res = release_lock(self.item.id)
                self.assertFalse(res)
                mock_rollback.assert_called_once()

    def test_agenda_item_lock_model_methods(self):
        now = datetime.now(timezone.utc)
        # Timezone-aware
        lock_active = AgendaItemLock(
            agenda_item_id=self.item.id,
            user_id=self.admin_user.id,
            user_naam='Admin',
            locked_at=now,
            expires_at=now + timedelta(minutes=5)
        )
        self.assertFalse(lock_active.is_expired())

        # Timezone-naive
        lock_naive = AgendaItemLock(
            agenda_item_id=self.item.id,
            user_id=self.admin_user.id,
            user_naam='Admin',
            locked_at=now,
            expires_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=5)
        )
        self.assertTrue(lock_naive.is_expired())

        # __repr__
        repr_str = repr(lock_active)
        self.assertIn('AgendaItemLock', repr_str)
        self.assertIn('Admin', repr_str)
