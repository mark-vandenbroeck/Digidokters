from flask import session, has_request_context
from extensions import db
from models.organisatie import Organisatie


def get_huidige_organisatie_id():
    """Haal het actieve organisatie_id op uit de sessie (indien binnen request context)."""
    if has_request_context():
        return session.get('organisatie_id')
    return None


def get_huidige_organisatie():
    """Haal het actieve Organisatie model object op."""
    org_id = get_huidige_organisatie_id()
    if not org_id:
        return None
    return db.session.get(Organisatie, org_id)


def filter_op_organisatie(query, model):
    """Filter de query op de actieve organisatie_id."""
    org_id = get_huidige_organisatie_id()
    if org_id is not None:
        return query.filter(model.organisatie_id == org_id)
    return query


def set_organisatie_id_op_model(instance):
    """Stel het actieve organisatie_id in op de model instantie."""
    org_id = get_huidige_organisatie_id()
    if org_id is not None:
        instance.organisatie_id = org_id
