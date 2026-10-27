"""Beheer van vergrendelingen (locks) voor gelijktijdige bewerking van agenda-aanwezigheden."""
from datetime import datetime, timezone, timedelta
from extensions import db
from models.agenda import AgendaItemLock


def clean_expired_locks():
    """Verwijdert alle verlopen vergrendelingen uit de database."""
    try:
        now = datetime.now(timezone.utc)
        AgendaItemLock.query.filter(AgendaItemLock.expires_at < now).delete(synchronize_session='fetch')
        db.session.commit()
    except Exception:
        db.session.rollback()


def get_active_lock(agenda_item_id: int) -> AgendaItemLock | None:
    """Haalt de actieve (niet-verlopen) vergrendeling op voor een agenda-item."""
    clean_expired_locks()
    lock = AgendaItemLock.query.filter_by(agenda_item_id=agenda_item_id).first()
    if lock and lock.is_expired():
        try:
            db.session.delete(lock)
            db.session.commit()
        except Exception:
            db.session.rollback()
        return None
    return lock


def acquire_or_check_lock(agenda_item_id: int, user, timeout_minutes: int = 5) -> tuple[bool, AgendaItemLock | None]:
    """
    Controleert of de huidige gebruiker de aanwezigheden mag bewerken en claimt/verlengt de vergrendeling.

    Retourneert:
      (True, lock)  -> Gebruiker mag bewerken (lock is geclaimd of reeds in bezit)
      (False, lock) -> Gebruiker mag NIET bewerken (actief vergrendeld door een andere gebruiker)
    """
    clean_expired_locks()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=timeout_minutes)

    lock = AgendaItemLock.query.filter_by(agenda_item_id=agenda_item_id).first()

    # 1. Geen bestaande lock -> Claim nieuwe lock
    if not lock:
        try:
            new_lock = AgendaItemLock(
                agenda_item_id=agenda_item_id,
                user_id=user.id,
                user_naam=user.naam,
                locked_at=now,
                expires_at=expires_at
            )
            db.session.add(new_lock)
            db.session.commit()
            return True, new_lock
        except Exception:
            db.session.rollback()
            # Race condition: herprobeer ophalen
            lock = AgendaItemLock.query.filter_by(agenda_item_id=agenda_item_id).first()
            if lock and lock.user_id != user.id and not lock.is_expired():
                return False, lock

    # 2. Lock is van huidige gebruiker -> Verleng de lock
    if lock and lock.user_id == user.id:
        try:
            lock.expires_at = expires_at
            lock.user_naam = user.naam
            db.session.commit()
            return True, lock
        except Exception:
            db.session.rollback()
            return True, lock

    # 3. Lock is verlopen -> Neem lock over
    if lock and lock.is_expired():
        try:
            lock.user_id = user.id
            lock.user_naam = user.naam
            lock.locked_at = now
            lock.expires_at = expires_at
            db.session.commit()
            return True, lock
        except Exception:
            db.session.rollback()
            return True, lock

    # 4. Lock is actief van een ANDERE gebruiker -> Weiger bewerken van aanwezigheid
    return False, lock


def release_lock(agenda_item_id: int, user_id: int | None = None) -> bool:
    """
    Geeft de vergrendeling op een agenda-item vrij indien deze in bezit is van user_id
    (of ongeacht gebruiker indien user_id None is).
    """
    try:
        query = AgendaItemLock.query.filter_by(agenda_item_id=agenda_item_id)
        if user_id is not None:
            query = query.filter_by(user_id=user_id)
        deleted = query.delete(synchronize_session='fetch')
        db.session.commit()
        return deleted > 0
    except Exception:
        db.session.rollback()
        return False
