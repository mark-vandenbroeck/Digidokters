"""
utils/permissions.py

Dynamische autorisatie- en permissie-engine voor het Digidokters platform.
Berekent en handhaaft fijnmazige permissies per organisatie en groep.
"""

from functools import wraps
from flask import session, request, flash, redirect, url_for, g, has_request_context, abort
from flask_login import current_user
from extensions import db
from models.constants import (
    ACCESS_NONE, ACCESS_READ, ACCESS_WRITE, ACCESS_LEVELS, ACCESS_LEVEL_ORDER,
    ALL_FEATURES, FEATURE_REGISTRATIES, FEATURE_AGENDA, FEATURE_STATISTIEKEN,
    FEATURE_DOCUMENTEN, FEATURE_EVALUATIES, FEATURE_FEEDBACK, FEATURE_STAMGEGEVENS,
    FEATURE_GEBRUIKERS, FEATURE_IMPORT_EXPORT,
    ROLE_PLATFORMBEHEERDER, ROLE_BEHEERDER, ROLE_MEDEWERKER, ROLE_LEZER,
    DEFAULT_GROUP_LEZERS, DEFAULT_GROUP_MEDEWERKERS, DEFAULT_GROUP_BEHEERDERS, DEFAULT_GROUP_PLATFORMBEHEERDERS
)


def get_default_matrix_voor_groep(groep_naam: str) -> dict:
    """Retourneert de standaard permissiematrix voor een systeemgroep of rol."""
    naam = (groep_naam or '').lower().strip()
    
    if naam in (DEFAULT_GROUP_PLATFORMBEHEERDERS, DEFAULT_GROUP_BEHEERDERS, ROLE_PLATFORMBEHEERDER, ROLE_BEHEERDER):
        # Beheerders & Platformbeheerders: Volledige schrijfrechten op alles
        return {f: ACCESS_WRITE for f in ALL_FEATURES}
    
    elif naam in (DEFAULT_GROUP_MEDEWERKERS, ROLE_MEDEWERKER):
        # Medewerkers: Schrijven op dagelijkse operaties, lezen op stats/stam/export, geen toegang tot gebruikersbeheer
        return {
            FEATURE_REGISTRATIES: ACCESS_WRITE,
            FEATURE_AGENDA: ACCESS_WRITE,
            FEATURE_STATISTIEKEN: ACCESS_READ,
            FEATURE_DOCUMENTEN: ACCESS_WRITE,
            FEATURE_EVALUATIES: ACCESS_WRITE,
            FEATURE_FEEDBACK: ACCESS_WRITE,
            FEATURE_STAMGEGEVENS: ACCESS_READ,
            FEATURE_GEBRUIKERS: ACCESS_NONE,
            FEATURE_IMPORT_EXPORT: ACCESS_READ,
        }
    
    elif naam in (DEFAULT_GROUP_LEZERS, ROLE_LEZER):
        # Lezers: Alleen-lezen op alle inhoudelijke modules, geen toegang tot gebruikersbeheer
        return {
            FEATURE_REGISTRATIES: ACCESS_READ,
            FEATURE_AGENDA: ACCESS_READ,
            FEATURE_STATISTIEKEN: ACCESS_READ,
            FEATURE_DOCUMENTEN: ACCESS_READ,
            FEATURE_EVALUATIES: ACCESS_READ,
            FEATURE_FEEDBACK: ACCESS_READ,
            FEATURE_STAMGEGEVENS: ACCESS_READ,
            FEATURE_GEBRUIKERS: ACCESS_NONE,
            FEATURE_IMPORT_EXPORT: ACCESS_READ,
        }
    
    # Standaard voor nieuwe maatwerkgroepen: Lezen op kernmodules
    return {f: ACCESS_READ for f in ALL_FEATURES}


def get_user_permissions_voor_organisatie(user, org_id: int | None) -> dict[str, str]:
    """
    Berekent de geaggregeerde effectieve permissies van een gebruiker binnen een specifieke organisatie.
    Als een gebruiker in meerdere groepen zit, geldt het hoogste niveau per functionaliteit.
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return {f: ACCESS_NONE for f in ALL_FEATURES}

    # Globale platformbeheerders hebben altijd overal volledige schrijfrechten
    if getattr(user, 'rol', None) == ROLE_PLATFORMBEHEERDER:
        return {f: ACCESS_WRITE for f in ALL_FEATURES}

    if not org_id:
        return {f: ACCESS_NONE for f in ALL_FEATURES}

    # Caching binnen de levensduur van het huidige request
    if has_request_context():
        if not hasattr(g, '_user_permissions_cache'):
            g._user_permissions_cache = {}
        cache_key = (user.id, org_id)
        if cache_key in g._user_permissions_cache:
            return g._user_permissions_cache[cache_key]

    from models.group import Group, GroupPermission, UserGroup

    # 1. Zoek actieve groepen van de gebruiker binnen deze organisatie
    user_groups = Group.query.join(UserGroup, Group.id == UserGroup.groep_id)\
        .filter(UserGroup.user_id == user.id, Group.organisatie_id == org_id, Group.actief == True)\
        .all()

    effective_perms = {f: ACCESS_NONE for f in ALL_FEATURES}

    if user_groups:
        for grp in user_groups:
            for p in grp.permissies:
                feature = p.functionaliteit
                level = p.toegangsniveau
                if feature in effective_perms:
                    current_rank = ACCESS_LEVEL_ORDER.get(effective_perms[feature], 0)
                    new_rank = ACCESS_LEVEL_ORDER.get(level, 0)
                    if new_rank > current_rank:
                        effective_perms[feature] = level
    else:
        # Fallback voor backwards compatibility als een gebruiker nog geen groepen heeft toegekend gekregen
        from models.organisatie import UserOrganisatie
        uo = next((x for x in user.user_organisaties if x.organisatie_id == org_id and x.actief), None)
        if uo:
            effective_perms = get_default_matrix_voor_groep(uo.rol)
        else:
            effective_perms = get_default_matrix_voor_groep(user.rol)

    if has_request_context():
        g._user_permissions_cache[cache_key] = effective_perms

    return effective_perms


def has_permission(feature: str, required_level: str = 'read', user=None, org_id=None) -> bool:
    """
    Controleert of de (huidige) gebruiker minimaal over 'required_level' beschikt voor 'feature'.
    required_level: 'read'/'lezen' of 'write'/'schrijven' of 'none'/'geen'.
    """
    if user is None:
        user = current_user

    if not user or not getattr(user, 'is_authenticated', False):
        return False

    if getattr(user, 'rol', None) == ROLE_PLATFORMBEHEERDER:
        return True

    if org_id is None and has_request_context():
        org_id = session.get('organisatie_id')

    # Normaliseer required_level
    req = required_level.lower().strip()
    if req in ('read', 'lezen'):
        normalized_req = ACCESS_READ
    elif req in ('write', 'schrijven'):
        normalized_req = ACCESS_WRITE
    elif req in ('none', 'geen'):
        normalized_req = ACCESS_NONE
    else:
        normalized_req = ACCESS_READ

    req_rank = ACCESS_LEVEL_ORDER.get(normalized_req, 1)

    perms = get_user_permissions_voor_organisatie(user, org_id)
    user_level = perms.get(feature, ACCESS_NONE)
    user_rank = ACCESS_LEVEL_ORDER.get(user_level, 0)

    return user_rank >= req_rank


def can_read(feature: str, user=None, org_id=None) -> bool:
    """Helper: mag de gebruiker deze module inzien?"""
    return has_permission(feature, ACCESS_READ, user=user, org_id=org_id)


def can_write(feature: str, user=None, org_id=None) -> bool:
    """Helper: mag de gebruiker gegevens in deze module toevoegen/wijzigen/verwijderen?"""
    return has_permission(feature, ACCESS_WRITE, user=user, org_id=org_id)


def is_alleen_eigen_registraties(user=None, org_id=None) -> bool:
    """
    Bepaalt of de gebruiker binnen de organisatie beperkt is tot uitsluitend zijn eigen registraties.
    Platformbeheerders en organisatiebeheerders hebben altijd globaal overzicht.
    Als de gebruiker lid is van meerdere groepen, geldt de beperking enkel als ALLE actieve groepen
    met toegang tot registraties de beperking hebben ingeschakeld (toegang tot alles wint).
    """
    if user is None:
        user = current_user
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if getattr(user, 'rol', None) == ROLE_PLATFORMBEHEERDER:
        return False
    if user.is_beheerder():
        return False

    if org_id is None and has_request_context():
        org_id = session.get('organisatie_id')
    if not org_id:
        return False

    from models.group import Group, UserGroup
    user_groups = Group.query.join(UserGroup, Group.id == UserGroup.groep_id)\
        .filter(UserGroup.user_id == user.id, Group.organisatie_id == org_id, Group.actief == True)\
        .all()

    if not user_groups:
        return False

    # Filter op actieve groepen die toegang geven tot registraties (lezen of schrijven)
    reg_groups = [g for g in user_groups if g.get_permission(FEATURE_REGISTRATIES) in (ACCESS_READ, ACCESS_WRITE)]
    if not reg_groups:
        return False

    return all(g.alleen_eigen_registraties for g in reg_groups)


def require_permission(feature: str, required_level: str = 'read'):
    """
    Decorator voor view routes: handhaaft dat de ingelogde gebruiker over de vereiste
    permissie beschikt voor de aangegeven functionele module binnen de actieve organisatie.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login'))

            if current_user.rol == ROLE_PLATFORMBEHEERDER:
                return f(*args, **kwargs)

            org_id = session.get('organisatie_id')
            if not org_id:
                return redirect(url_for('auth.select_org'))

            if not has_permission(feature, required_level, user=current_user, org_id=org_id):
                if request.is_json or request.path.endswith('.json'):
                    return {'error': 'Onvoldoende rechten voor deze actie.'}, 403
                flash('U heeft onvoldoende rechten om deze pagina te bezoeken of deze actie uit te voeren.', 'danger')
                return redirect(request.referrer or url_for('reg.lijst'))

            return f(*args, **kwargs)
        return decorated_function
    return decorator


# Alias
permission_required = require_permission


def seed_standaard_groepen_voor_organisatie(org_id: int):
    """
    Maakt de 4 standaardgroepen (Lezers, Medewerkers, Beheerders, Platformbeheerders) aan
    voor een organisatie met hun bijbehorende permissieset, en koppelt bestaande gebruikers
    aan de overeenkomstige groep.
    """
    from models.group import Group, GroupPermission, UserGroup
    from models.organisatie import UserOrganisatie

    standaard_config = [
        (DEFAULT_GROUP_LEZERS, 'Lezers', 'Gebruikers met uitsluitend lees- en raadpleegrechten.'),
        (DEFAULT_GROUP_MEDEWERKERS, 'Medewerkers', 'Standaard medewerkers met registratie- en bewerkrechten.'),
        (DEFAULT_GROUP_BEHEERDERS, 'Beheerders', 'Lokale organisatiebeheerders met volledige beheerrechten.'),
        (DEFAULT_GROUP_PLATFORMBEHEERDERS, 'Platformbeheerders', 'Globale platformbeheerders.'),
    ]

    groepen_map = {}

    for slug, naam, beschrijving in standaard_config:
        grp = Group.query.filter_by(organisatie_id=org_id, naam=naam).first()
        if not grp:
            grp = Group(
                organisatie_id=org_id,
                naam=naam,
                beschrijving=beschrijving,
                is_standaard=True,
                actief=True
            )
            db.session.add(grp)
            db.session.flush()

        # Permissies instellen
        matrix = get_default_matrix_voor_groep(slug)
        for feature, level in matrix.items():
            perm = GroupPermission.query.filter_by(groep_id=grp.id, functionaliteit=feature).first()
            if not perm:
                perm = GroupPermission(groep_id=grp.id, functionaliteit=feature, toegangsniveau=level)
                db.session.add(perm)
            else:
                perm.toegangsniveau = level

        groepen_map[slug] = grp

    # Bestaande gebruikers koppelen aan hun corresponderende standaardgroep
    user_orgs = UserOrganisatie.query.filter_by(organisatie_id=org_id).all()
    for uo in user_orgs:
        target_group = None
        if uo.user.rol == ROLE_PLATFORMBEHEERDER:
            target_group = groepen_map.get(DEFAULT_GROUP_PLATFORMBEHEERDERS)
        elif uo.rol == ROLE_BEHEERDER:
            target_group = groepen_map.get(DEFAULT_GROUP_BEHEERDERS)
        elif uo.rol == ROLE_LEZER:
            target_group = groepen_map.get(DEFAULT_GROUP_LEZERS)
        else:
            target_group = groepen_map.get(DEFAULT_GROUP_MEDEWERKERS)

        if target_group:
            existing = UserGroup.query.filter_by(user_id=uo.user_id, groep_id=target_group.id).first()
            if not existing:
                db.session.add(UserGroup(user_id=uo.user_id, groep_id=target_group.id))

    db.session.commit()
    return groepen_map
