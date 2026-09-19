"""Backup en restore handler voor organisatiedata."""
import json
from datetime import datetime, timezone
from sqlalchemy.orm import joinedload, selectinload
from extensions import db
from models.organisatie import Organisatie, UserOrganisatie
from models.user import User
from models.digidokter import Digidokter
from models.age_category import AgeCategory
from models.device import Device
from models.herkomst import Herkomst
from models.gender_identity import GenderIdentity
from models.functie import Functie, user_functies
from models.registration import Registration
from models.activity_type import ActivityType
from models.location import Location
from models.agenda import AgendaItem


def maak_backup(org_id: int) -> dict:
    """Genereer een complete backup data dictionary voor de gegeven organisatie met eager loading."""
    org = db.session.get(Organisatie, org_id)

    # 1. Users & Memberships
    memberships = (
        UserOrganisatie.query
        .options(joinedload(UserOrganisatie.user))
        .filter_by(organisatie_id=org_id)
        .all()
    )
    users_data = [
        {
            'naam': m.user.naam,
            'email': m.user.email,
            'telefoonnummer': getattr(m.user, 'telefoonnummer', None),
            'wachtwoord_hash': m.user.wachtwoord_hash,
            'rol': m.user.rol,
            'actief': m.user.actief,
            'membership_rol': m.rol,
            'membership_actief': m.actief,
            'functies': [f.naam for f in m.user.get_functies_voor_organisatie(org_id)]
        }
        for m in memberships if m.user
    ]

    # 2. Digidokters
    digidokters = Digidokter.query.filter_by(organisatie_id=org_id).order_by(Digidokter.volgorde).all()
    digidokters_data = [
        {'naam': d.naam, 'actief': d.actief, 'volgorde': d.volgorde}
        for d in digidokters
    ]

    # 3. Age categories
    age_cats = (
        AgeCategory.query
        .options(joinedload(AgeCategory.mapped_to))
        .filter_by(organisatie_id=org_id)
        .order_by(AgeCategory.volgorde)
        .all()
    )
    age_cats_data = [
        {
            'naam': c.naam,
            'actief': c.actief,
            'volgorde': c.volgorde,
            'mapped_to_naam': c.mapped_to.naam if c.mapped_to else None,
        }
        for c in age_cats
    ]

    # 4. Devices
    devices = (
        Device.query
        .options(joinedload(Device.mapped_to))
        .filter_by(organisatie_id=org_id)
        .order_by(Device.volgorde)
        .all()
    )
    devices_data = [
        {
            'naam': t.naam,
            'actief': t.actief,
            'volgorde': t.volgorde,
            'mapped_to_naam': t.mapped_to.naam if t.mapped_to else None,
        }
        for t in devices
    ]

    # 5. Herkomsten
    herkomsten = Herkomst.query.filter_by(organisatie_id=org_id).order_by(Herkomst.volgorde).all()
    herkomsten_data = [
        {'naam': h.naam, 'actief': h.actief, 'volgorde': h.volgorde}
        for h in herkomsten
    ]

    # 5b. Genderidentiteiten
    gender_identities = GenderIdentity.query.filter_by(organisatie_id=org_id).order_by(GenderIdentity.volgorde).all()
    gender_identities_data = [
        {'naam': g.naam, 'actief': g.actief, 'volgorde': g.volgorde}
        for g in gender_identities
    ]

    # 5c. Functies
    functies = Functie.query.filter_by(organisatie_id=org_id).order_by(Functie.volgorde).all()
    functies_data = [
        {'naam': fn.naam, 'actief': fn.actief, 'volgorde': fn.volgorde}
        for fn in functies
    ]

    # 6. Registrations (eager load foreign key relations)
    registrations = (
        Registration.query
        .options(
            joinedload(Registration.digidokter),
            joinedload(Registration.leeftijdscategorie),
            joinedload(Registration.toestel),
            joinedload(Registration.herkomst),
            joinedload(Registration.gender_identity),
            joinedload(Registration.locatie),
            joinedload(Registration.aangemaakt_door_user),
        )
        .filter_by(organisatie_id=org_id)
        .order_by(Registration.datum.desc(), Registration.registratienummer.desc())
        .all()
    )
    registrations_data = [
        {
            'registratienummer': r.registratienummer,
            'datum': r.datum.isoformat() if r.datum else None,
            'client': r.client,
            'nieuwe_klant': r.nieuwe_klant,
            'herkomst': r.herkomst.naam if r.herkomst else '',
            'geslacht': r.geslacht,
            'onderwerp': r.onderwerp,
            'digidokter_naam': r.digidokter.naam if r.digidokter else '',
            'leeftijdscategorie_naam': r.leeftijdscategorie.naam if r.leeftijdscategorie else '',
            'toestel_naam': r.toestel.naam if r.toestel else '',
            'locatie_naam': r.locatie.naam if r.locatie else '',
            'aangemaakt_door_naam': r.aangemaakt_door_user.naam if r.aangemaakt_door_user else '',
            'aangemaakt_op': r.aangemaakt_op.isoformat() if r.aangemaakt_op else None,
            'gewijzigd_op': r.gewijzigd_op.isoformat() if r.gewijzigd_op else None
        }
        for r in registrations
    ]

    # 7. Activity types
    activity_types = ActivityType.query.filter_by(organisatie_id=org_id).order_by(ActivityType.volgorde).all()
    activity_types_data = [
        {'naam': at.naam, 'actief': at.actief, 'volgorde': at.volgorde}
        for at in activity_types
    ]

    # 8. Locations
    locations = Location.query.filter_by(organisatie_id=org_id).order_by(Location.volgorde).all()
    locations_data = [
        {
            'naam': l.naam,
            'actief': l.actief,
            'volgorde': l.volgorde,
            'gebruikt_voor_consultaties': l.gebruikt_voor_consultaties
        }
        for l in locations
    ]

    # 9. Agenda items
    agenda_items = (
        AgendaItem.query
        .options(
            joinedload(AgendaItem.type),
            joinedload(AgendaItem.locatie),
            selectinload(AgendaItem.digidokters)
        )
        .filter_by(organisatie_id=org_id)
        .order_by(AgendaItem.datum.desc())
        .all()
    )
    agenda_items_data = [
        {
            'datum': a.datum.isoformat() if a.datum else None,
            'uur_van': a.uur_van,
            'uur_tot': a.uur_tot,
            'type_name': a.type.naam if a.type else '',
            'locatie_name': a.locatie.naam if a.locatie else '',
            'omschrijving': a.omschrijving,
            'digidokter_namen': [d.naam for d in a.digidokters]
        }
        for a in agenda_items
    ]

    return {
        'metadata': {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'versie': '2.1'
        },
        'organisatie': {
            'naam': org.naam if org else 'Onbekend',
            'slug': org.slug if org else 'onbekend'
        },
        'users': users_data,
        'digidokters': digidokters_data,
        'age_categories': age_cats_data,
        'devices': devices_data,
        'herkomsten': herkomsten_data,
        'gender_identities': gender_identities_data,
        'functies': functies_data,
        'activity_types': activity_types_data,
        'locations': locations_data,
        'agenda_items': agenda_items_data,
        'registrations': registrations_data
    }


def herstel_backup(org_id: int, file_stream, huidige_user_id: int) -> tuple[bool, str]:
    """Herstel een backup bestand in de database binnen een veilige transactie. Retourneert (succes, bericht)."""
    try:
        data = json.load(file_stream)
    except Exception as e:
        return False, f'Fout bij het lezen van het JSON-bestand: {str(e)}'

    required_keys = ['organisatie', 'users', 'digidokters', 'age_categories', 'devices', 'registrations']
    if not all(k in data for k in required_keys):
        return False, 'Ongeldig backup-bestand. Het bestand mist vereiste datablokken.'

    try:
        with db.session.begin_nested():
            # 1. Verwijder bestaande data van deze organisatie
            Registration.query.filter_by(organisatie_id=org_id).delete()
            AgendaItem.query.filter_by(organisatie_id=org_id).delete()
            Digidokter.query.filter_by(organisatie_id=org_id).delete()
            AgeCategory.query.filter_by(organisatie_id=org_id).delete()
            Device.query.filter_by(organisatie_id=org_id).delete()
            Herkomst.query.filter_by(organisatie_id=org_id).delete()
            GenderIdentity.query.filter_by(organisatie_id=org_id).delete()
            Functie.query.filter_by(organisatie_id=org_id).delete()
            ActivityType.query.filter_by(organisatie_id=org_id).delete()
            Location.query.filter_by(organisatie_id=org_id).delete()

            # Verwijder lidmaatschappen behalve huidige hersteller
            UserOrganisatie.query.filter(
                UserOrganisatie.organisatie_id == org_id,
                UserOrganisatie.user_id != huidige_user_id
            ).delete()

            # 2. Herstel digidokters
            digidokters_map = {}
            for d_data in data.get('digidokters', []):
                d = Digidokter(
                    naam=d_data['naam'],
                    actief=d_data.get('actief', True),
                    volgorde=d_data.get('volgorde', 0),
                    organisatie_id=org_id
                )
                db.session.add(d)
                db.session.flush()
                digidokters_map[d.naam] = d.id

            # 3. Herstel leeftijdscategorieën
            age_cats_map = {}
            for c_data in data.get('age_categories', []):
                c = AgeCategory(
                    naam=c_data['naam'],
                    actief=c_data.get('actief', True),
                    volgorde=c_data.get('volgorde', 0),
                    organisatie_id=org_id
                )
                db.session.add(c)
                db.session.flush()
                age_cats_map[c.naam] = c.id

            # 4. Herstel toestellen
            devices_map = {}
            for t_data in data.get('devices', []):
                t = Device(
                    naam=t_data['naam'],
                    actief=t_data.get('actief', True),
                    volgorde=t_data.get('volgorde', 0),
                    organisatie_id=org_id
                )
                db.session.add(t)
                db.session.flush()
                devices_map[t.naam] = t.id

            # Herstel mappings voor categorieën en toestellen
            for c_data in data.get('age_categories', []):
                mapped_name = c_data.get('mapped_to_naam')
                if mapped_name and mapped_name in age_cats_map:
                    c_id = age_cats_map.get(c_data['naam'])
                    if c_id:
                        c_obj = db.session.get(AgeCategory, c_id)
                        if c_obj:
                            c_obj.mapped_to_id = age_cats_map[mapped_name]

            for t_data in data.get('devices', []):
                mapped_name = t_data.get('mapped_to_naam')
                if mapped_name and mapped_name in devices_map:
                    t_id = devices_map.get(t_data['naam'])
                    if t_id:
                        t_obj = db.session.get(Device, t_id)
                        if t_obj:
                            t_obj.mapped_to_id = devices_map[mapped_name]

            # 5. Herstel herkomsten
            herkomsten_map = {}
            if 'herkomsten' in data:
                for h_data in data['herkomsten']:
                    h = Herkomst(
                        naam=h_data['naam'],
                        actief=h_data.get('actief', True),
                        volgorde=h_data.get('volgorde', 0),
                        organisatie_id=org_id
                    )
                    db.session.add(h)
                    db.session.flush()
                    herkomsten_map[h.naam] = h.id
            else:
                unique_origins = set()
                for r_data in data.get('registrations', []):
                    h_val = r_data.get('herkomst')
                    if h_val and str(h_val).strip() and str(h_val).strip().lower() != 'nan':
                        unique_origins.add(str(h_val).strip())
                for idx, name in enumerate(sorted(unique_origins)):
                    h = Herkomst(naam=name, actief=True, volgorde=idx, organisatie_id=org_id)
                    db.session.add(h)
                    db.session.flush()
                    herkomsten_map[name] = h.id

            # 5b. Herstel genderidentiteiten
            gender_identities_map = {}
            if 'gender_identities' in data:
                for g_data in data.get('gender_identities', []):
                    g = GenderIdentity(
                        naam=g_data['naam'],
                        actief=g_data.get('actief', True),
                        volgorde=g_data.get('volgorde', 0),
                        organisatie_id=org_id
                    )
                    db.session.add(g)
                    db.session.flush()
                    gender_identities_map[g.naam.lower()] = g.id
            else:
                # Fallback defaults
                for idx, name in enumerate(['Man', 'Vrouw']):
                    g = GenderIdentity(naam=name, actief=True, volgorde=idx, organisatie_id=org_id)
                    db.session.add(g)
                    db.session.flush()
                    gender_identities_map[name.lower()] = g.id

            # 5c. Herstel functies
            functies_map = {}
            if 'functies' in data:
                for fn_data in data.get('functies', []):
                    fn = Functie(
                        naam=fn_data['naam'],
                        actief=fn_data.get('actief', True),
                        volgorde=fn_data.get('volgorde', 0),
                        organisatie_id=org_id
                    )
                    db.session.add(fn)
                    db.session.flush()
                    functies_map[fn.naam] = fn
            else:
                # Fallback defaults
                for idx, name in enumerate(['Digidokter', 'Digihelper', 'Lesgever']):
                    fn = Functie(naam=name, actief=True, volgorde=idx, organisatie_id=org_id)
                    db.session.add(fn)
                    db.session.flush()
                    functies_map[name] = fn

            # 6. Herstel gebruikers & lidmaatschappen
            users_map = {}
            for u_data in data.get('users', []):
                u = User.query.filter(db.func.lower(User.naam) == u_data['naam'].lower()).first()
                if not u:
                    u = User(
                        naam=u_data['naam'],
                        email=u_data.get('email'),
                        telefoonnummer=u_data.get('telefoonnummer'),
                        wachtwoord_hash=u_data['wachtwoord_hash'],
                        rol=u_data.get('rol', 'medewerker'),
                        actief=u_data.get('actief', True),
                        moet_wachtwoord_wijzigen=False
                    )
                    db.session.add(u)
                    db.session.flush()
                elif u_data.get('telefoonnummer') and not u.telefoonnummer:
                    u.telefoonnummer = u_data.get('telefoonnummer')

                # Herstel gekoppelde functies
                if 'functies' in u_data and isinstance(u_data['functies'], list):
                    for fn_naam in u_data['functies']:
                        fn_obj = functies_map.get(fn_naam)
                        if fn_obj and fn_obj not in u.functies:
                            u.functies.append(fn_obj)

                users_map[u.naam] = u.id

                uo = UserOrganisatie.query.filter_by(user_id=u.id, organisatie_id=org_id).first()
                if not uo:
                    uo = UserOrganisatie(
                        user_id=u.id,
                        organisatie_id=org_id,
                        rol=u_data.get('membership_rol', 'medewerker'),
                        actief=u_data.get('membership_actief', True)
                    )
                    db.session.add(uo)
                else:
                    uo.rol = u_data.get('membership_rol', uo.rol)
                    uo.actief = u_data.get('membership_actief', uo.actief)

            # Behoud actieve hersteller als beheerder
            uo_hersteller = UserOrganisatie.query.filter_by(user_id=huidige_user_id, organisatie_id=org_id).first()
            if not uo_hersteller:
                uo_hersteller = UserOrganisatie(
                    user_id=huidige_user_id,
                    organisatie_id=org_id,
                    rol='beheerder',
                    actief=True
                )
                db.session.add(uo_hersteller)
            else:
                uo_hersteller.rol = 'beheerder'
                uo_hersteller.actief = True

            # 7. Herstel registraties
            for r_data in data.get('registrations', []):
                d_id = digidokters_map.get(r_data.get('digidokter_naam')) or (list(digidokters_map.values())[0] if digidokters_map else None)
                c_id = age_cats_map.get(r_data.get('leeftijdscategorie_naam')) or (list(age_cats_map.values())[0] if age_cats_map else None)
                t_id = devices_map.get(r_data.get('toestel_naam')) or (list(devices_map.values())[0] if devices_map else None)
                creator_id = users_map.get(r_data.get('aangemaakt_door_naam'), huidige_user_id)

                herkomst_naam = r_data.get('herkomst')
                h_id = herkomsten_map.get(herkomst_naam) if herkomst_naam else None

                geslacht_val = r_data.get('geslacht')
                g_id = gender_identities_map.get(geslacht_val.lower()) if (geslacht_val and isinstance(geslacht_val, str)) else None

                reg_datum = datetime.fromisoformat(r_data['datum']).date() if r_data.get('datum') else None
                created_at = datetime.fromisoformat(r_data['aangemaakt_op']) if r_data.get('aangemaakt_op') else datetime.now(timezone.utc)
                modified_at = datetime.fromisoformat(r_data['gewijzigd_op']) if r_data.get('gewijzigd_op') else datetime.now(timezone.utc)

                r = Registration(
                    registratienummer=r_data['registratienummer'],
                    datum=reg_datum,
                    client=r_data['client'],
                    nieuwe_klant=r_data.get('nieuwe_klant', False),
                    herkomst_id=h_id,
                    gender_identity_id=g_id,
                    onderwerp=r_data['onderwerp'],
                    digidokter_id=d_id,
                    leeftijdscategorie_id=c_id,
                    toestel_id=t_id,
                    aangemaakt_door_id=creator_id,
                    aangemaakt_op=created_at,
                    gewijzigd_op=modified_at,
                    organisatie_id=org_id
                )
                db.session.add(r)

            # 8. Herstel activiteitstypes
            activity_types_map = {}
            if 'activity_types' in data:
                for at_data in data['activity_types']:
                    at = ActivityType(
                        naam=at_data['naam'],
                        actief=at_data.get('actief', True),
                        volgorde=at_data.get('volgorde', 0),
                        organisatie_id=org_id
                    )
                    db.session.add(at)
                    db.session.flush()
                    activity_types_map[at.naam] = at.id
            else:
                for i, name in enumerate(['Digidokters', 'Digicafé', 'Lunchvergadering']):
                    at = ActivityType(naam=name, actief=True, volgorde=i, organisatie_id=org_id)
                    db.session.add(at)
                    db.session.flush()
                    activity_types_map[name] = at.id

            # 9. Herstel locaties
            locations_map = {}
            if 'locations' in data:
                for l_data in data['locations']:
                    l = Location(
                        naam=l_data['naam'],
                        actief=l_data.get('actief', True),
                        volgorde=l_data.get('volgorde', 0),
                        gebruikt_voor_consultaties=l_data.get('gebruikt_voor_consultaties', False),
                        organisatie_id=org_id
                    )
                    db.session.add(l)
                    db.session.flush()
                    locations_map[l.naam] = l.id
            else:
                for i, name in enumerate(['Bib Londerzeel', 'Buurttafel', 'Brouwerij De Palm']):
                    l = Location(naam=name, actief=True, volgorde=i, organisatie_id=org_id)
                    db.session.add(l)
                    db.session.flush()
                    locations_map[name] = l.id

            # 10. Herstel agenda-items
            if 'agenda_items' in data:
                for item_data in data['agenda_items']:
                    datum = datetime.fromisoformat(item_data['datum']).date() if item_data.get('datum') else None
                    type_id = activity_types_map.get(item_data.get('type_name')) or (list(activity_types_map.values())[0] if activity_types_map else None)
                    locatie_id = locations_map.get(item_data.get('locatie_name')) or (list(locations_map.values())[0] if locations_map else None)

                    item = AgendaItem(
                        datum=datum,
                        uur_van=item_data['uur_van'],
                        uur_tot=item_data['uur_tot'],
                        type_id=type_id,
                        locatie_id=locatie_id,
                        omschrijving=item_data.get('omschrijving'),
                        organisatie_id=org_id
                    )

                    selected_dds = []
                    for dd_name in item_data.get('digidokter_namen', []):
                        dd_id = digidokters_map.get(dd_name)
                        if dd_id:
                            d = db.session.get(Digidokter, dd_id)
                            if d:
                                selected_dds.append(d)
                    item.digidokters = selected_dds
                    db.session.add(item)

        db.session.commit()
        return True, 'De organisatie-data is succesvol hersteld.'
    except Exception as e:
        db.session.rollback()
        return False, f'Fout tijdens het herstellen van de data: {str(e)}'
