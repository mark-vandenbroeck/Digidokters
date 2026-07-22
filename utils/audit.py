import json
from datetime import datetime, date, timezone
from flask import has_request_context, session as session_flask
from flask_login import current_user
from sqlalchemy import event, inspect
from models.audit import AuditLog

def serialize_val(val):
    """Formatteert speciale typen zoals datums naar JSON-compatibele strings."""
    if val is None:
        return None
    if isinstance(val, (datetime, date)):
        return val.isoformat()
    if isinstance(val, (int, float, bool, str)):
        return val
    return str(val)

def should_audit(obj):
    """Bepaalt of we de wijzigingen op dit model moeten loggen."""
    # Sla AuditLog zelf en eventuele systeemtabellen over
    if obj.__class__.__name__ == 'AuditLog':
        return False
    if obj.__tablename__.startswith('limiter_') or obj.__tablename__ == 'audit_logs':
        return False
    return True

def get_audit_context():
    """Haalt de actuele gebruiker en organisatie_id op uit de web- of systeemcontext."""
    gebruiker = 'Systeem'
    org_id = None
    if has_request_context():
        if current_user and current_user.is_authenticated:
            gebruiker = current_user.naam
        org_id = session_flask.get('organisatie_id')
    return gebruiker, org_id

def register_audit_listeners(db):
    """Registreert de SQLAlchemy mapper events voor automatische auditing."""
    
    @event.listens_for(db.Model, 'after_insert', propagate=True)
    def after_insert(mapper, connection, target):
        if not should_audit(target):
            return
            
        gebruiker, org_id = get_audit_context()
        obj_org_id = getattr(target, 'organisatie_id', org_id)
        
        nieuwe_waarden = {}
        for attr in mapper.column_attrs:
            val = getattr(target, attr.key)
            if attr.key == 'inhoud' and target.__class__.__name__ == 'Document':
                nieuwe_waarden[attr.key] = '<binaire inhoud>'
            else:
                nieuwe_waarden[attr.key] = serialize_val(val)
                
        connection.execute(
            AuditLog.__table__.insert().values(
                tabel=target.__tablename__,
                operatie='CREATE',
                record_id=target.id,
                gebruiker=gebruiker,
                timestamp=datetime.now(timezone.utc),
                details=json.dumps({'nieuwe_waarden': nieuwe_waarden}, ensure_ascii=False),
                organisatie_id=obj_org_id
            )
        )

    @event.listens_for(db.Model, 'after_update', propagate=True)
    def after_update(mapper, connection, target):
        if not should_audit(target):
            return
            
        state = inspect(target)
        oude_waarden = {}
        nieuwe_waarden = {}
        has_changes = False
        
        for attr in mapper.column_attrs:
            field = attr.key
            history = state.attrs[field].history
            if history.has_changes():
                old_val = history.deleted[0] if history.deleted else None
                new_val = history.added[0] if history.added else None
                
                if field == 'inhoud' and target.__class__.__name__ == 'Document':
                    oude_waarden[field] = '<binaire inhoud>'
                    nieuwe_waarden[field] = '<binaire inhoud>'
                else:
                    oude_waarden[field] = serialize_val(old_val)
                    nieuwe_waarden[field] = serialize_val(new_val)
                has_changes = True
                
        if has_changes:
            gebruiker, org_id = get_audit_context()
            obj_org_id = getattr(target, 'organisatie_id', org_id)
            
            connection.execute(
                AuditLog.__table__.insert().values(
                    tabel=target.__tablename__,
                    operatie='UPDATE',
                    record_id=target.id,
                    gebruiker=gebruiker,
                    timestamp=datetime.now(timezone.utc),
                    details=json.dumps({
                        'oude_waarden': oude_waarden,
                        'nieuwe_waarden': nieuwe_waarden
                    }, ensure_ascii=False),
                    organisatie_id=obj_org_id
                )
            )

    @event.listens_for(db.Model, 'after_delete', propagate=True)
    def after_delete(mapper, connection, target):
        if not should_audit(target):
            return
            
        gebruiker, org_id = get_audit_context()
        obj_org_id = getattr(target, 'organisatie_id', org_id)
        
        oude_waarden = {}
        for attr in mapper.column_attrs:
            val = getattr(target, attr.key)
            if attr.key == 'inhoud' and target.__class__.__name__ == 'Document':
                oude_waarden[attr.key] = '<binaire inhoud>'
            else:
                oude_waarden[attr.key] = serialize_val(val)
                
        connection.execute(
            AuditLog.__table__.insert().values(
                tabel=target.__tablename__,
                operatie='DELETE',
                record_id=target.id,
                gebruiker=gebruiker,
                timestamp=datetime.now(timezone.utc),
                details=json.dumps({'oude_waarden': oude_waarden}, ensure_ascii=False),
                organisatie_id=obj_org_id
            )
        )
