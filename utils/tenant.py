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
    """Seed de standaard gegevens (leeftijdscategorieën, toestellen, activiteitstypes, locaties, herkomsten) voor een nieuwe organisatie."""
    from models.age_category import AgeCategory
    from models.device import Device
    from models.activity_type import ActivityType
    from models.location import Location
    from models.digidokter import Digidokter
    from models.herkomst import Herkomst

    # Digidokters (niet gekopieerd, want dit zijn specifieke vrijwilligers)
    if not Digidokter.query.filter_by(organisatie_id=org_id).first():
        for i, name in enumerate(['Mark', 'Jan', 'Els']):
            db.session.add(Digidokter(naam=name, actief=True, volgorde=i, organisatie_id=org_id))

    # Leeftijdscategorieën
    if not AgeCategory.query.filter_by(organisatie_id=org_id).first():
        active_cats = []
        if org_id != 1:
            active_cats = AgeCategory.query.filter_by(organisatie_id=1, actief=True).order_by(AgeCategory.volgorde).all()
        
        if active_cats:
            for i, cat in enumerate(active_cats):
                db.session.add(AgeCategory(naam=cat.naam, actief=True, volgorde=i, organisatie_id=org_id))
        else:
            for i, name in enumerate(['Jonger dan 18', '18 - 30', '31 - 60', '60+']):
                db.session.add(AgeCategory(naam=name, actief=True, volgorde=i, organisatie_id=org_id))

    # Toestellen
    if not Device.query.filter_by(organisatie_id=org_id).first():
        active_devs = []
        if org_id != 1:
            active_devs = Device.query.filter_by(organisatie_id=1, actief=True).order_by(Device.volgorde).all()
        
        if active_devs:
            for i, dev in enumerate(active_devs):
                db.session.add(Device(naam=dev.naam, actief=True, volgorde=i, organisatie_id=org_id))
        else:
            for i, name in enumerate([
                'Smartphone Android', 'Smartphone iPhone', 'Tablet Android', 'iPad',
                'Laptop Windows', 'MacBook', 'Ander toestel'
            ]):
                db.session.add(Device(naam=name, actief=True, volgorde=i, organisatie_id=org_id))

    # Activiteitstypes
    if not ActivityType.query.filter_by(organisatie_id=org_id).first():
        active_types = []
        if org_id != 1:
            active_types = ActivityType.query.filter_by(organisatie_id=1, actief=True).order_by(ActivityType.volgorde).all()
        
        if active_types:
            for i, at in enumerate(active_types):
                db.session.add(ActivityType(naam=at.naam, actief=True, heeft_evaluatie=getattr(at, 'heeft_evaluatie', False), kleur=at.kleur, volgorde=i, organisatie_id=org_id))
        else:
            for i, name in enumerate(['Digidokters', 'Digicafé', 'Lunchvergadering']):
                heeft_eval = (name.lower() == 'digicafé')
                db.session.add(ActivityType(naam=name, actief=True, heeft_evaluatie=heeft_eval, volgorde=i, organisatie_id=org_id))

    # Locaties
    if not Location.query.filter_by(organisatie_id=org_id).first():
        active_locs = []
        if org_id != 1:
            active_locs = Location.query.filter_by(organisatie_id=1, actief=True).order_by(Location.volgorde).all()
        
        if active_locs:
            for i, loc in enumerate(active_locs):
                db.session.add(Location(naam=loc.naam, actief=True, volgorde=i, organisatie_id=org_id))
        else:
            for i, name in enumerate(['Bib Londerzeel', 'Buurttafel', 'Brouwerij De Palm']):
                db.session.add(Location(naam=name, actief=True, volgorde=i, organisatie_id=org_id))

    # Herkomsten
    if not Herkomst.query.filter_by(organisatie_id=org_id).first():
        active_herkomsten = []
        if org_id != 1:
            active_herkomsten = Herkomst.query.filter_by(organisatie_id=1, actief=True).order_by(Herkomst.volgorde).all()
        
        if active_herkomsten:
            for i, hk in enumerate(active_herkomsten):
                db.session.add(Herkomst(naam=hk.naam, actief=True, volgorde=i, organisatie_id=org_id))
        else:
            for i, name in enumerate(['Mond-tot-mond', 'Website', 'Sociale media', 'Flyer/Affiche', 'Gemeenteblad', 'Andere']):
                db.session.add(Herkomst(naam=name, actief=True, volgorde=i, organisatie_id=org_id))

    db.session.commit()

    # Evaluatieformulieren seeden voor activiteitstypes met evaluatieplicht
    from models.evaluation import EvaluationForm, EvaluationQuestion
    eval_types = ActivityType.query.filter_by(organisatie_id=org_id, heeft_evaluatie=True).all()
    for at in eval_types:
        if not EvaluationForm.query.filter_by(activity_type_id=at.id, organisatie_id=org_id).first():
            # Kopieer van org 1 of gebruik standaard Digicafé configuratie
            from routes.evaluations import get_or_create_evaluation_form
            get_or_create_evaluation_form(at.id, org_id)
