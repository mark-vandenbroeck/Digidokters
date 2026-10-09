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
    from models.organisatie import Organisatie
    from models.age_category import AgeCategory
    from models.device import Device
    from models.activity_type import ActivityType
    from models.location import Location
    from models.digidokter import Digidokter
    from models.herkomst import Herkomst

    # Bepaal de bron-organisatie (eerst 'Sjabloon', anders org 1)
    template_org = Organisatie.query.filter_by(slug='sjabloon', actief=True).first()
    source_org_id = template_org.id if (template_org and template_org.id != org_id) else (1 if org_id != 1 else None)

    # Digidokters (niet gekopieerd, want dit zijn specifieke vrijwilligers)
    if not Digidokter.query.filter_by(organisatie_id=org_id).first():
        for i, name in enumerate(['Mark', 'Jan', 'Els']):
            db.session.add(Digidokter(naam=name, actief=True, volgorde=i, organisatie_id=org_id))

    # Leeftijdscategorieën
    if not AgeCategory.query.filter_by(organisatie_id=org_id).first():
        active_cats = []
        if source_org_id:
            active_cats = AgeCategory.query.filter_by(organisatie_id=source_org_id, actief=True).order_by(AgeCategory.volgorde).all()
        
        if active_cats:
            for i, cat in enumerate(active_cats):
                db.session.add(AgeCategory(naam=cat.naam, actief=True, volgorde=i, organisatie_id=org_id))
        else:
            for i, name in enumerate(['Jonger dan 18', '18 - 30', '31 - 60', '60+']):
                db.session.add(AgeCategory(naam=name, actief=True, volgorde=i, organisatie_id=org_id))

    # Toestellen
    if not Device.query.filter_by(organisatie_id=org_id).first():
        active_devs = []
        if source_org_id:
            active_devs = Device.query.filter_by(organisatie_id=source_org_id, actief=True).order_by(Device.volgorde).all()
        
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
        if source_org_id:
            active_types = ActivityType.query.filter_by(organisatie_id=source_org_id, actief=True).order_by(ActivityType.volgorde).all()
        
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
        if source_org_id:
            active_locs = Location.query.filter_by(organisatie_id=source_org_id, actief=True).order_by(Location.volgorde).all()
        
        if active_locs:
            for i, loc in enumerate(active_locs):
                db.session.add(Location(naam=loc.naam, actief=True, volgorde=i, gebruikt_voor_consultaties=getattr(loc, 'gebruikt_voor_consultaties', False), organisatie_id=org_id))
        else:
            for i, name in enumerate(['Bib Londerzeel', 'Buurttafel', 'Brouwerij De Palm']):
                gebruikt = (i == 0)
                db.session.add(Location(naam=name, actief=True, volgorde=i, gebruikt_voor_consultaties=gebruikt, organisatie_id=org_id))

    # Herkomsten
    if not Herkomst.query.filter_by(organisatie_id=org_id).first():
        active_herkomsten = []
        if source_org_id:
            active_herkomsten = Herkomst.query.filter_by(organisatie_id=source_org_id, actief=True).order_by(Herkomst.volgorde).all()
        
        if active_herkomsten:
            for i, hk in enumerate(active_herkomsten):
                db.session.add(Herkomst(naam=hk.naam, actief=True, volgorde=i, organisatie_id=org_id))
        else:
            for i, name in enumerate(['Mond-tot-mond', 'Website', 'Sociale media', 'Flyer/Affiche', 'Gemeenteblad', 'Andere']):
                db.session.add(Herkomst(naam=name, actief=True, volgorde=i, organisatie_id=org_id))

    # Genderidentiteit (Man, Vrouw)
    from models.gender_identity import GenderIdentity
    if not GenderIdentity.query.filter_by(organisatie_id=org_id).first():
        active_genders = []
        if source_org_id:
            active_genders = GenderIdentity.query.filter_by(organisatie_id=source_org_id, actief=True).order_by(GenderIdentity.volgorde).all()
        
        if active_genders:
            for i, g in enumerate(active_genders):
                db.session.add(GenderIdentity(naam=g.naam, actief=True, volgorde=i, organisatie_id=org_id))
        else:
            for i, name in enumerate(['Man', 'Vrouw']):
                db.session.add(GenderIdentity(naam=name, actief=True, volgorde=i, organisatie_id=org_id))

    # Functies (Digidokter, Digihelper, Lesgever)
    from models.functie import Functie
    if not Functie.query.filter_by(organisatie_id=org_id).first():
        active_functies = []
        if source_org_id:
            active_functies = Functie.query.filter_by(organisatie_id=source_org_id, actief=True).order_by(Functie.volgorde).all()
        
        if active_functies:
            for i, fn in enumerate(active_functies):
                db.session.add(Functie(naam=fn.naam, actief=True, volgorde=i, organisatie_id=org_id))
        else:
            for i, name in enumerate(['Digidokter', 'Digihelper', 'Lesgever']):
                db.session.add(Functie(naam=name, actief=True, volgorde=i, organisatie_id=org_id))

    # Resultaten van het bezoek
    from models.resultaat import Resultaat
    if not Resultaat.query.filter_by(organisatie_id=org_id).first():
        active_resultaten = []
        if source_org_id:
            active_resultaten = Resultaat.query.filter_by(organisatie_id=source_org_id, actief=True).order_by(Resultaat.volgorde).all()

        if active_resultaten:
            for i, res in enumerate(active_resultaten):
                db.session.add(Resultaat(omschrijving=res.omschrijving, actief=True, volgorde=i, organisatie_id=org_id))
        else:
            standaard_resultaten = [
                'Vraag beantwoord',
                'Bezoeker komt later terug',
                'Bezoeker doorverwezen',
                'Vraag onmogelijk te beantwoorden',
                'Andere'
            ]
            for i, omschrijving in enumerate(standaard_resultaten):
                db.session.add(Resultaat(omschrijving=omschrijving, actief=True, volgorde=i, organisatie_id=org_id))

    db.session.commit()

    # Groepen & Permissies seeden
    from models.group import Group, GroupPermission
    from utils.permissions import seed_standaard_groepen_voor_organisatie
    if not Group.query.filter_by(organisatie_id=org_id).first():
        source_groups = []
        if source_org_id:
            source_groups = Group.query.filter_by(organisatie_id=source_org_id, actief=True).all()
        
        if source_groups:
            for s_grp in source_groups:
                new_grp = Group(
                    organisatie_id=org_id,
                    naam=s_grp.naam,
                    beschrijving=s_grp.beschrijving,
                    is_standaard=s_grp.is_standaard,
                    alleen_eigen_registraties=getattr(s_grp, 'alleen_eigen_registraties', False),
                    actief=True
                )
                db.session.add(new_grp)
                db.session.flush()
                for perm in s_grp.permissies:
                    db.session.add(GroupPermission(
                        groep_id=new_grp.id,
                        functionaliteit=perm.functionaliteit,
                        toegangsniveau=perm.toegangsniveau
                    ))
            db.session.commit()
        else:
            seed_standaard_groepen_voor_organisatie(org_id)

    # Evaluatieformulieren seeden voor activiteitstypes met evaluatieplicht
    from models.evaluation import EvaluationForm, EvaluationQuestion
    eval_types = ActivityType.query.filter_by(organisatie_id=org_id, heeft_evaluatie=True).all()
    for at in eval_types:
        if not EvaluationForm.query.filter_by(activity_type_id=at.id, organisatie_id=org_id).first():
            # Kopieer van org 1 of gebruik standaard Digicafé configuratie
            from routes.evaluations import get_or_create_evaluation_form
            get_or_create_evaluation_form(at.id, org_id)

    # E-mailsjablonen seeden
    from models.email_template import EmailTemplate
    if not EmailTemplate.query.filter_by(organisatie_id=org_id).first():
        source_templates = []
        if source_org_id:
            source_templates = EmailTemplate.query.filter_by(organisatie_id=source_org_id).all()

        if source_templates:
            for s_tpl in source_templates:
                db.session.add(EmailTemplate(
                    organisatie_id=org_id,
                    sleutel=s_tpl.sleutel,
                    naam=s_tpl.naam,
                    onderwerp=s_tpl.onderwerp,
                    inhoud=s_tpl.inhoud,
                    beschrijving=s_tpl.beschrijving,
                    beschikbare_variabelen=s_tpl.beschikbare_variabelen
                ))
            db.session.commit()
        else:
            defaults = EmailTemplate.get_default_templates()
            for sleutel, data in defaults.items():
                db.session.add(EmailTemplate(
                    organisatie_id=org_id,
                    sleutel=sleutel,
                    naam=data['naam'],
                    onderwerp=data['onderwerp'],
                    inhoud=data['inhoud'],
                    beschrijving=data['beschrijving'],
                    beschikbare_variabelen=data['beschikbare_variabelen']
                ))
            db.session.commit()

