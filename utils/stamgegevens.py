"""Stamgegevens controller helpers voor overzichten, volgorde, status en veilige verwijdering."""
from typing import Type
from flask import abort
from extensions import db
from models.registration import Registration
from models.agenda import AgendaItem
from utils.tenant import filter_op_organisatie


def get_usage_counts(model: Type[db.Model], org_id: int) -> dict[int, int]:
    """Bereken efficiënt de gebruikstellingen voor stamgegevens in 1 query."""
    name = model.__name__
    if name == 'AgeCategory':
        return dict(
            db.session.query(Registration.leeftijdscategorie_id, db.func.count(Registration.id))
            .filter_by(organisatie_id=org_id)
            .group_by(Registration.leeftijdscategorie_id)
            .all()
        )
    if name == 'Device':
        return dict(
            db.session.query(Registration.toestel_id, db.func.count(Registration.id))
            .filter_by(organisatie_id=org_id)
            .group_by(Registration.toestel_id)
            .all()
        )
    if name == 'Herkomst':
        return dict(
            db.session.query(Registration.herkomst_id, db.func.count(Registration.id))
            .filter_by(organisatie_id=org_id)
            .group_by(Registration.herkomst_id)
            .all()
        )
    if name == 'Digidokter':
        return dict(
            db.session.query(Registration.digidokter_id, db.func.count(Registration.id))
            .filter_by(organisatie_id=org_id)
            .group_by(Registration.digidokter_id)
            .all()
        )
    if name == 'Location':
        agenda_counts = dict(
            db.session.query(AgendaItem.locatie_id, db.func.count(AgendaItem.id))
            .filter_by(organisatie_id=org_id)
            .group_by(AgendaItem.locatie_id)
            .all()
        )
        reg_counts = dict(
            db.session.query(Registration.locatie_id, db.func.count(Registration.id))
            .filter_by(organisatie_id=org_id)
            .group_by(Registration.locatie_id)
            .all()
        )
        usage = {}
        for lid in set(list(agenda_counts.keys()) + list(reg_counts.keys())):
            usage[lid] = agenda_counts.get(lid, 0) + reg_counts.get(lid, 0)
        return usage
    return {}


def toggle_stamgegeven_status(model: Type[db.Model], item_id: int, org_id: int) -> tuple[str, bool]:
    """Toggle de actief-status van een stamgegeven item. Geeft (naam, nieuwe_status) terug."""
    item = db.get_or_404(model, item_id)
    if item.organisatie_id != org_id:
        abort(403)
    item.actief = not item.actief
    if item.actief and hasattr(item, 'mapped_to_id'):
        item.mapped_to_id = None
    db.session.commit()
    return item.naam, item.actief


def wijzig_stamgegeven_volgorde(model: Type[db.Model], item_id: int, richting: str, org_id: int) -> None:
    """Verplaats een item omhoog of omlaag in de volgorde en herindexeer."""
    item = db.get_or_404(model, item_id)
    if item.organisatie_id != org_id:
        abort(403)

    alle = filter_op_organisatie(model.query, model).order_by(model.volgorde, model.naam).all()
    idx = next((i for i, x in enumerate(alle) if x.id == item_id), None)
    if idx is None:
        return

    if richting == 'omhoog' and idx > 0:
        buurman = alle[idx - 1]
        item.volgorde, buurman.volgorde = buurman.volgorde, item.volgorde
        if item.volgorde == buurman.volgorde:
            item.volgorde = max(0, buurman.volgorde - 1)
    elif richting == 'omlaag' and idx < len(alle) - 1:
        buurman = alle[idx + 1]
        item.volgorde, buurman.volgorde = buurman.volgorde, item.volgorde
        if item.volgorde == buurman.volgorde:
            item.volgorde = buurman.volgorde + 1

    # Herbereken volgordes netjes op 0, 1, 2, ...
    herordend = sorted(alle, key=lambda x: (x.volgorde, x.naam))
    for i, x in enumerate(herordend):
        x.volgorde = i
    db.session.commit()
