from datetime import datetime, timezone
from flask import url_for
from extensions import db
from models.feedback import FeedbackItem, FeedbackComment, FeedbackView


def markeer_feedback_bekeken(user_id, feedback_id=None):
    """
    Registreert of actualiseert het tijdstip waarop een gebruiker de feedback-overzichtspagina
    (feedback_id=None) of een specifieke detailpagina (feedback_id=<int>) voor het laatst heeft bekeken.
    """
    if not user_id:
        return None

    nu = datetime.now(timezone.utc)
    if feedback_id is None:
        view = FeedbackView.query.filter_by(user_id=user_id, feedback_id=None).first()
    else:
        view = FeedbackView.query.filter_by(user_id=user_id, feedback_id=feedback_id).first()

    if view:
        view.bekeken_op = nu
    else:
        view = FeedbackView(user_id=user_id, feedback_id=feedback_id, bekeken_op=nu)
        db.session.add(view)

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return view


def get_feedback_meldingen(user, org_id=None):
    """
    Verzamelt klikbare meldingen voor de huidige gebruiker:
    1. Nieuwe reacties op feedback-items van de gebruiker.
    2. Nieuwe feedback-items aangemaakt door andere gebruikers.
    """
    if not user or not user.is_authenticated:
        return []

    meldingen = []

    # -------------------------------------------------------------
    # 1. Nieuwe reacties op feedback-items ingediend door 'user'
    # -------------------------------------------------------------
    eigen_feedbacks = (
        FeedbackItem.query
        .filter_by(user_id=user.id)
        .order_by(FeedbackItem.gewijzigd_op.desc())
        .all()
    )

    for fb in eigen_feedbacks:
        # Zoek wanneer de eigenaar dit item voor het laatst heeft bekeken
        view = FeedbackView.query.filter_by(user_id=user.id, feedback_id=fb.id).first()
        cutoff_tijd = view.bekeken_op if view else fb.aangemaakt_op

        # Zoek reacties van ANDEREN nieuwer dan cutoff_tijd
        nieuwe_reacties = [
            r for r in fb.reacties
            if r.user_id != user.id and r.aangemaakt_op > cutoff_tijd
        ]

        if nieuwe_reacties:
            # Sorteer om de meest recente reactie te bepalen
            nieuwe_reacties.sort(key=lambda r: r.aangemaakt_op, reverse=True)
            laatste_reactie = nieuwe_reacties[0]
            auteur_naam = laatste_reactie.user.naam if laatste_reactie.user else 'Een collega'

            if len(nieuwe_reacties) == 1:
                tekst = f'"{fb.onderwerp}" van {auteur_naam}'
            else:
                tekst = f'{len(nieuwe_reacties)} nieuwe reacties op "{fb.onderwerp}" (laatste van {auteur_naam})'

            meldingen.append({
                'code': 'comment',
                'item_id': fb.id,
                'type': 'info',
                'btn_type': 'info',
                'icon': 'chat-dots-fill',
                'titel': 'Nieuwe reactie op uw feedback',
                'tekst': tekst,
                'url': url_for('feedback.detail', id=fb.id),
                'datum': laatste_reactie.aangemaakt_op
            })

    # -------------------------------------------------------------
    # 2. Nieuwe feedback-items aangemaakt door andere gebruikers
    # -------------------------------------------------------------
    # Tijdstip waarop de gebruiker de feedback-overzichtslijst voor het laatst heeft bezocht
    list_view = FeedbackView.query.filter_by(user_id=user.id, feedback_id=None).first()
    list_cutoff = list_view.bekeken_op if list_view else user.aangemaakt_op

    query = FeedbackItem.query.filter(
        FeedbackItem.user_id != user.id,
        FeedbackItem.is_afgesloten.is_(False),
        FeedbackItem.aangemaakt_op > list_cutoff
    )

    # Multi-tenant scoping: platformbeheerder ziet alles; overige rollen enkel eigen organisatie
    if user.rol != 'platformbeheerder':
        if org_id:
            query = query.filter(FeedbackItem.organisatie_id == org_id)

    ongeziene_items = []
    for item in query.order_by(FeedbackItem.aangemaakt_op.desc()).all():
        # Controleer of de gebruiker deze specifieke feedback individueel heeft geopend
        item_view = FeedbackView.query.filter_by(user_id=user.id, feedback_id=item.id).first()
        if not item_view or item_view.bekeken_op < item.aangemaakt_op:
            ongeziene_items.append(item)

    if len(ongeziene_items) == 1:
        item = ongeziene_items[0]
        auteur = item.user.naam if item.user else 'Collega'
        icon = 'lightbulb-fill' if item.type == 'voorstel' else 'bug-fill'
        meldingen.append({
            'code': 'new_feedback',
            'item_id': item.id,
            'type': 'primary',
            'btn_type': 'primary',
            'icon': icon,
            'titel': f'Nieuw {item.type_label.lower()}',
            'tekst': f'"{item.onderwerp}" van {auteur}',
            'url': url_for('feedback.detail', id=item.id),
            'datum': item.aangemaakt_op
        })
    elif len(ongeziene_items) > 1:
        if len(ongeziene_items) <= 2:
            for item in ongeziene_items:
                auteur = item.user.naam if item.user else 'Collega'
                icon = 'lightbulb-fill' if item.type == 'voorstel' else 'bug-fill'
                meldingen.append({
                    'code': 'new_feedback',
                    'item_id': item.id,
                    'type': 'primary',
                    'btn_type': 'primary',
                    'icon': icon,
                    'titel': f'Nieuw {item.type_label.lower()}',
                    'tekst': f'"{item.onderwerp}" van {auteur}',
                    'url': url_for('feedback.detail', id=item.id),
                    'datum': item.aangemaakt_op
                })
        else:
            meldingen.append({
                'code': 'new_feedback_list',
                'item_id': None,
                'type': 'primary',
                'btn_type': 'primary',
                'icon': 'chat-heart-fill',
                'titel': 'Nieuwe feedback-items',
                'tekst': f'Er zijn {len(ongeziene_items)} nieuwe feedback-items ingediend door collega\'s',
                'url': url_for('feedback.lijst'),
                'datum': ongeziene_items[0].aangemaakt_op
            })

    # Sorteer meldingen op meest recente datum eerst
    meldingen.sort(key=lambda m: m.get('datum') or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return meldingen


def markeer_melding_gelezen(user_id, melding_code, item_id=None):
    """
    Markeert een specifieke melding als gelezen (bijv. bij het klikken op het kruisje).
    """
    if melding_code == 'comment' and item_id:
        markeer_feedback_bekeken(user_id, feedback_id=item_id)
    elif melding_code == 'new_feedback' and item_id:
        markeer_feedback_bekeken(user_id, feedback_id=item_id)
    elif melding_code in ('new_feedback_list', 'new_feedback'):
        markeer_feedback_bekeken(user_id, feedback_id=None)
