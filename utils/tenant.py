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


def seed_organisatie_defaults(org_id):
    """Seed de standaard gegevens (leeftijdscategorieën, toestellen, activiteitstypes, locaties) voor een nieuwe organisatie."""
    from models.age_category import AgeCategory
    from models.device import Device
    from models.activity_type import ActivityType
    from models.location import Location
    from models.digidokter import Digidokter

    # Digidokters
    if not Digidokter.query.filter_by(organisatie_id=org_id).first():
        for i, name in enumerate(['Mark', 'Jan', 'Els']):
            db.session.add(Digidokter(naam=name, actief=True, volgorde=i, organisatie_id=org_id))

    # Leeftijdscategorieën
    if not AgeCategory.query.filter_by(organisatie_id=org_id).first():
        for i, name in enumerate(['Jonger dan 18', '18 - 30', '31 - 60', '60+']):
            db.session.add(AgeCategory(naam=name, actief=True, volgorde=i, organisatie_id=org_id))

    # Toestellen
    if not Device.query.filter_by(organisatie_id=org_id).first():
        for i, name in enumerate([
            'Smartphone Android', 'Smartphone iPhone', 'Tablet Android', 'iPad',
            'Laptop Windows', 'MacBook', 'Ander toestel'
        ]):
            db.session.add(Device(naam=name, actief=True, volgorde=i, organisatie_id=org_id))

    # Activiteitstypes
    if not ActivityType.query.filter_by(organisatie_id=org_id).first():
        for i, name in enumerate(['Digidokters', 'Digicafé', 'Lunchvergadering']):
            db.session.add(ActivityType(naam=name, actief=True, volgorde=i, organisatie_id=org_id))

    # Locaties
    if not Location.query.filter_by(organisatie_id=org_id).first():
        for i, name in enumerate(['Bib Londerzeel', 'Buurttafel', 'Brouwerij De Palm']):
            db.session.add(Location(naam=name, actief=True, volgorde=i, organisatie_id=org_id))

    # Herkomsten
    from models.herkomst import Herkomst
    if not Herkomst.query.filter_by(organisatie_id=org_id).first():
        for i, name in enumerate(['Mond-tot-mond', 'Website', 'Sociale media', 'Flyer/Affiche', 'Gemeenteblad', 'Andere']):
            db.session.add(Herkomst(naam=name, actief=True, volgorde=i, organisatie_id=org_id))

    db.session.commit()
