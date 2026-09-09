import io
import os
from datetime import datetime, timezone
from flask import Blueprint, render_template, redirect, url_for, flash, request, send_file, abort
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from extensions import db
from models.feedback import FeedbackItem, FeedbackVote, FeedbackComment
from utils.tenant import get_huidige_organisatie_id, filter_op_organisatie

feedback_bp = Blueprint('feedback', __name__, url_prefix='/feedback')

TOEGESTANE_BEELDFORMATEN = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}
MAX_SCREENSHOT_GROOTTE = 5 * 1024 * 1024  # 5 MB


@feedback_bp.route('/')
@login_required
def lijst():
    """Toont overzicht van alle feedbacks, gesorteerd op aanmaaktijdstip (aflopend)."""
    org_id = get_huidige_organisatie_id()
    status_filter = request.args.get('status', 'alle').strip().lower()
    type_filter = request.args.get('type', 'alle').strip().lower()
    zoek = request.args.get('zoek', '').strip()

    if current_user.rol == 'platformbeheerder':
        query = FeedbackItem.query
    else:
        query = filter_op_organisatie(FeedbackItem.query, FeedbackItem)

    if status_filter == 'open':
        query = query.filter_by(is_afgesloten=False)
    elif status_filter == 'afgesloten':
        query = query.filter_by(is_afgesloten=True)

    if type_filter in ('foutje', 'voorstel'):
        query = query.filter_by(type=type_filter)

    if zoek:
        zoek_term = f"%{zoek}%"
        query = query.filter(
            (FeedbackItem.onderwerp.ilike(zoek_term)) |
            (FeedbackItem.beschrijving.ilike(zoek_term))
        )

    # Standaard gesorteerd in dalende volgorde van aanmaaktijdstip
    feedbacks = query.order_by(FeedbackItem.aangemaakt_op.desc()).all()

    # Tellers voor filterknoppen
    if current_user.rol == 'platformbeheerder':
        basis_query = FeedbackItem.query
    else:
        basis_query = filter_op_organisatie(FeedbackItem.query, FeedbackItem)
    totaal_aantal = basis_query.count()
    open_aantal = basis_query.filter_by(is_afgesloten=False).count()
    afgesloten_aantal = basis_query.filter_by(is_afgesloten=True).count()

    return render_template(
        'feedback/lijst.html',
        feedbacks=feedbacks,
        status_filter=status_filter,
        type_filter=type_filter,
        zoek=zoek,
        totaal_aantal=totaal_aantal,
        open_aantal=open_aantal,
        afgesloten_aantal=afgesloten_aantal
    )


@feedback_bp.route('/nieuw', methods=['GET', 'POST'])
@login_required
def nieuw():
    """Invoeren van nieuwe feedback (Foutje? of Voorstel)."""
    if current_user.is_lezer():
        flash('Als lezer heeft u enkel leesrechten en kunt u geen feedback indienen.', 'warning')
        return redirect(url_for('feedback.lijst'))

    org_id = get_huidige_organisatie_id()
    if not org_id:
        if current_user.user_organisaties:
            org_id = current_user.user_organisaties[0].organisatie_id
        else:
            from models.organisatie import Organisatie
            first_org = Organisatie.query.filter_by(actief=True).first()
            org_id = first_org.id if first_org else 1

    if request.method == 'POST':
        type_val = request.form.get('type', 'voorstel').strip().lower()
        if type_val not in ('foutje', 'voorstel'):
            type_val = 'voorstel'

        onderwerp = request.form.get('onderwerp', '').strip()
        beschrijving = request.form.get('beschrijving', '').strip()

        if not onderwerp or not beschrijving:
            flash('Onderwerp en beschrijving zijn verplicht.', 'danger')
            return render_template(
                'feedback/form.html',
                form_data=request.form,
                vandaag_str=datetime.now().strftime('%d-%m-%Y om %H:%M')
            )

        # Screenshot verwerking
        screenshot_naam = None
        screenshot_mime = None
        screenshot_data = None

        if 'screenshot' in request.files:
            file = request.files['screenshot']
            if file and file.filename:
                ext = os.path.splitext(file.filename)[1].lower()
                if ext in TOEGESTANE_BEELDFORMATEN:
                    bestand_bytes = file.read()
                    if len(bestand_bytes) > MAX_SCREENSHOT_GROOTTE:
                        flash('Het screenshot is te groot (maximaal 5 MB toegestaan).', 'warning')
                        return render_template(
                            'feedback/form.html',
                            form_data=request.form,
                            vandaag_str=datetime.now().strftime('%d-%m-%Y om %H:%M')
                        )
                    screenshot_naam = secure_filename(file.filename)
                    screenshot_mime = file.mimetype or 'image/png'
                    screenshot_data = bestand_bytes
                else:
                    flash('Ongeldig bestandsformaat voor screenshot. Gebruik PNG, JPG, JPEG, GIF of WEBP.', 'warning')
                    return render_template(
                        'feedback/form.html',
                        form_data=request.form,
                        vandaag_str=datetime.now().strftime('%d-%m-%Y om %H:%M')
                    )

        fb = FeedbackItem(
            organisatie_id=org_id,
            user_id=current_user.id,
            type=type_val,
            onderwerp=onderwerp,
            beschrijving=beschrijving,
            screenshot_naam=screenshot_naam,
            screenshot_mime=screenshot_mime,
            screenshot_data=screenshot_data
        )
        db.session.add(fb)
        db.session.commit()

        flash(f'Feedback "{fb.onderwerp}" succesvol ingediend. Bedankt voor je bijdrage!', 'success')
        return redirect(url_for('feedback.detail', id=fb.id))

    return render_template(
        'feedback/form.html',
        form_data=None,
        vandaag_str=datetime.now().strftime('%d-%m-%Y om %H:%M')
    )


@feedback_bp.route('/<int:id>')
@login_required
def detail(id):
    """Detailweergave van een feedback met stemmen en conversatie."""
    fb = db.get_or_404(FeedbackItem, id)
    org_id = get_huidige_organisatie_id()

    # Multi-tenant check voor niet-platformbeheerders
    if current_user.rol != 'platformbeheerder' and fb.organisatie_id != org_id:
        abort(404)

    mijn_stem = fb.gebruiker_stem(current_user.id)
    nu_str = datetime.now().strftime('%d-%m-%Y om %H:%M')

    return render_template(
        'feedback/detail.html',
        feedback=fb,
        mijn_stem=mijn_stem,
        nu_str=nu_str
    )


@feedback_bp.route('/<int:id>/screenshot')
@login_required
def screenshot(id):
    """Serveert het screenshot van een feedback."""
    fb = db.get_or_404(FeedbackItem, id)
    org_id = get_huidige_organisatie_id()

    if current_user.rol != 'platformbeheerder' and fb.organisatie_id != org_id:
        abort(404)

    if not fb.screenshot_data:
        abort(404)

    return send_file(
        io.BytesIO(fb.screenshot_data),
        mimetype=fb.screenshot_mime or 'image/png',
        as_attachment=False,
        download_name=fb.screenshot_naam or 'screenshot.png'
    )


@feedback_bp.route('/<int:id>/stem', methods=['POST'])
@login_required
def stem(id):
    """Stemmen met duim omhoog (+1) of duim omlaag (-1)."""
    if current_user.is_lezer():
        flash('Als lezer heeft u enkel leesrechten en kunt u niet stemmen.', 'warning')
        return redirect(request.referrer or url_for('feedback.detail', id=id))

    fb = db.get_or_404(FeedbackItem, id)

    if fb.is_afgesloten:
        flash('Deze feedback is afgesloten. Er kan niet meer gestemd worden.', 'warning')
        return redirect(request.referrer or url_for('feedback.detail', id=fb.id))

    try:
        stem_val = int(request.form.get('stem', 0))
    except (ValueError, TypeError):
        stem_val = 0

    if stem_val not in (1, -1):
        abort(400)

    bestaande_stem = FeedbackVote.query.filter_by(feedback_id=fb.id, user_id=current_user.id).first()

    if bestaande_stem:
        if bestaande_stem.stem == stem_val:
            # Toggle unvote: nogmaals op zelfde duim klikken verwijdert stem
            db.session.delete(bestaande_stem)
            db.session.commit()
            flash('Je stem is ingetrokken.', 'info')
        else:
            # Wisselen van stem (+1 naar -1 of andersom)
            bestaande_stem.stem = stem_val
            bestaande_stem.aangemaakt_op = datetime.now(timezone.utc)
            db.session.commit()
            flash('Je stem is aangepast.', 'success')
    else:
        nieuwe_stem = FeedbackVote(
            feedback_id=fb.id,
            user_id=current_user.id,
            stem=stem_val
        )
        db.session.add(nieuwe_stem)
        db.session.commit()
        flash('Bedankt voor je stem!', 'success')

    return redirect(request.referrer or url_for('feedback.detail', id=fb.id))


@feedback_bp.route('/<int:id>/reageer', methods=['POST'])
@login_required
def reageer(id):
    """Bijdrage toevoegen aan de conversatie onder een feedback."""
    if current_user.is_lezer():
        flash('Als lezer heeft u enkel leesrechten en kunt u niet reageren.', 'warning')
        return redirect(url_for('feedback.detail', id=id))

    fb = db.get_or_404(FeedbackItem, id)

    if fb.is_afgesloten:
        flash('Deze feedback is afgesloten. Er kunnen geen nieuwe reacties meer geplaatst worden.', 'warning')
        return redirect(url_for('feedback.detail', id=fb.id))

    tekst = request.form.get('tekst', '').strip()
    if not tekst:
        flash('Reactie mag niet leeg zijn.', 'danger')
        return redirect(url_for('feedback.detail', id=fb.id))

    reactie = FeedbackComment(
        feedback_id=fb.id,
        user_id=current_user.id,
        tekst=tekst
    )
    db.session.add(reactie)
    db.session.commit()

    flash('Je bijdrage is toegevoegd aan de conversatie.', 'success')
    return redirect(url_for('feedback.detail', id=fb.id))


@feedback_bp.route('/<int:id>/status', methods=['POST'])
@login_required
def status(id):
    """Afsluiten of heropenen van een feedback door een beheerder."""
    if not current_user.is_beheerder():
        flash('Enkel beheerders zijn gemachtigd om feedback af te sluiten of te heropenen.', 'danger')
        return redirect(url_for('feedback.detail', id=id))

    fb = db.get_or_404(FeedbackItem, id)

    if fb.is_afgesloten:
        fb.is_afgesloten = False
        fb.afgesloten_op = None
        fb.afgesloten_door_id = None
        db.session.commit()
        flash(f'Feedback "{fb.onderwerp}" is heropend. Conversaties en stemmen zijn weer actief.', 'info')
    else:
        fb.is_afgesloten = True
        fb.afgesloten_op = datetime.now(timezone.utc)
        fb.afgesloten_door_id = current_user.id
        db.session.commit()
        flash(f'Feedback "{fb.onderwerp}" is succesvol afgesloten. Conversaties en stemmen zijn vergrendeld.', 'warning')

    return redirect(url_for('feedback.detail', id=fb.id))
