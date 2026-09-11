import io
import mimetypes
import os
from datetime import datetime, timezone
from functools import wraps
from flask import Blueprint, render_template, redirect, url_for, flash, request, send_file
from flask_login import login_required, current_user
from extensions import db
from models.app_document import AppFolder, AppDocument

app_docs_bp = Blueprint('app_docs', __name__, url_prefix='/app-documentatie')

MAX_FILE_SIZE = 16 * 1024 * 1024  # 16 MB in bytes


def platformbeheerder_required(f):
    """Decorator die vereist dat de gebruiker de rol platformbeheerder heeft."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        if current_user.rol != 'platformbeheerder':
            flash('Enkel de platformbeheerder kan documenten in App Documentatie beheren.', 'danger')
            return redirect(url_for('app_docs.index'))
        return f(*args, **kwargs)
    return decorated_function


def _bepaal_bestandstype(bestandsnaam, mime_type):
    """Bepaal een leesbare extensie/type op basis van bestandsnaam of MIME-type."""
    ext = os.path.splitext(bestandsnaam)[1].lower().lstrip('.')
    if ext:
        return ext
    if mime_type == 'application/pdf':
        return 'pdf'
    if 'word' in mime_type or 'document' in mime_type:
        return 'docx'
    if 'excel' in mime_type or 'sheet' in mime_type:
        return 'xlsx'
    if 'image' in mime_type:
        return 'afbeelding'
    return 'bestand'


@app_docs_bp.route('/')
@login_required
def index():
    map_id = request.args.get('map_id', type=int)
    zoek = request.args.get('zoek', '').strip()

    huidige_map = None
    breadcrumbs = [{'id': None, 'naam': 'App documentatie'}]

    if map_id:
        huidige_map = AppFolder.query.filter_by(id=map_id).first()
        if huidige_map:
            pad = []
            curr = huidige_map
            while curr:
                pad.append({'id': curr.id, 'naam': curr.naam})
                curr = curr.parent
            pad.reverse()
            breadcrumbs.extend(pad)
        else:
            flash('Gevraagde map werd niet gevonden.', 'warning')
            return redirect(url_for('app_docs.index'))

    zoek_snippets = {}
    if zoek:
        mappen = AppFolder.query.filter(AppFolder.naam.ilike(f'%{zoek}%')).order_by(AppFolder.naam).all()
        documenten = AppDocument.query.filter(
            (AppDocument.bestandsnaam.ilike(f'%{zoek}%')) |
            (AppDocument.omschrijving.ilike(f'%{zoek}%')) |
            (AppDocument.tekst_inhoud.ilike(f'%{zoek}%'))
        ).order_by(AppDocument.bestandsnaam).all()

        from utils.text_extractor import genereer_zoek_snippet
        for doc in documenten:
            snippet = genereer_zoek_snippet(doc.tekst_inhoud, zoek)
            if snippet:
                zoek_snippets[doc.id] = snippet
    else:
        mappen = AppFolder.query.filter_by(parent_id=map_id).order_by(AppFolder.naam).all()
        documenten = AppDocument.query.filter_by(map_id=map_id).order_by(AppDocument.bestandsnaam).all()

    # Algemene statistieken
    totaal_documenten = AppDocument.query.count()
    totaal_grootte_bytes = db.session.query(db.func.sum(AppDocument.bestandsgrootte)).scalar() or 0
    totaal_grootte_mb = round(totaal_grootte_bytes / (1024 * 1024), 2)

    is_beheerder = current_user.rol == 'platformbeheerder'

    return render_template(
        'app_documents/index.html',
        huidige_map=huidige_map,
        mappen=mappen,
        documenten=documenten,
        breadcrumbs=breadcrumbs,
        zoek=zoek,
        zoek_snippets=zoek_snippets,
        totaal_documenten=totaal_documenten,
        totaal_grootte_mb=totaal_grootte_mb,
        max_file_size_mb=16,
        is_beheerder=is_beheerder
    )


@app_docs_bp.route('/mappen/nieuw', methods=['POST'])
@login_required
@platformbeheerder_required
def map_toevoegen():
    naam = request.form.get('naam', '').strip()
    parent_id = request.form.get('parent_id', type=int)

    if not naam:
        flash('Vul een mapnaam in.', 'danger')
        return redirect(url_for('app_docs.index', map_id=parent_id))

    if parent_id:
        parent = AppFolder.query.filter_by(id=parent_id).first()
        if not parent:
            flash('Bovenliggende map niet gevonden.', 'danger')
            return redirect(url_for('app_docs.index'))

    nieuwe_map = AppFolder(
        naam=naam,
        parent_id=parent_id,
        aangemaakt_door_id=current_user.id
    )
    db.session.add(nieuwe_map)
    db.session.commit()
    flash(f'Map "{naam}" is succesvol aangemaakt.', 'success')
    return redirect(url_for('app_docs.index', map_id=parent_id))


@app_docs_bp.route('/mappen/<int:map_id>/hernoemen', methods=['POST'])
@login_required
@platformbeheerder_required
def map_hernoemen(map_id):
    folder = AppFolder.query.filter_by(id=map_id).first_or_404()
    nieuwe_naam = request.form.get('naam', '').strip()

    if not nieuwe_naam:
        flash('Mapnaam mag niet leeg zijn.', 'danger')
    else:
        oude_naam = folder.naam
        folder.naam = nieuwe_naam
        db.session.commit()
        flash(f'Map "{oude_naam}" is hernoemd naar "{nieuwe_naam}".', 'success')

    return_to = request.form.get('return_to')
    if return_to == 'self':
        return redirect(url_for('app_docs.index', map_id=folder.id))
    return redirect(url_for('app_docs.index', map_id=folder.parent_id))


@app_docs_bp.route('/mappen/<int:map_id>/verwijderen', methods=['POST'])
@login_required
@platformbeheerder_required
def map_verwijderen(map_id):
    folder = AppFolder.query.filter_by(id=map_id).first_or_404()
    parent_id = folder.parent_id
    naam = folder.naam

    db.session.delete(folder)
    db.session.commit()
    flash(f'Map "{naam}" en alle inhoud zijn succesvol verwijderd.', 'success')
    return redirect(url_for('app_docs.index', map_id=parent_id))


@app_docs_bp.route('/upload', methods=['POST'])
@login_required
@platformbeheerder_required
def upload():
    map_id = request.form.get('map_id', type=int)
    omschrijving = request.form.get('omschrijving', '').strip()

    if map_id:
        target_folder = AppFolder.query.filter_by(id=map_id).first()
        if not target_folder:
            flash('Map niet gevonden.', 'danger')
            return redirect(url_for('app_docs.index'))

    if 'bestand' not in request.files:
        flash('Geen bestand geselecteerd.', 'danger')
        return redirect(url_for('app_docs.index', map_id=map_id))

    bestand = request.files['bestand']
    if not bestand or bestand.filename == '':
        flash('Geen bestand geselecteerd.', 'danger')
        return redirect(url_for('app_docs.index', map_id=map_id))

    inhoud = bestand.read()
    bestandsgrootte = len(inhoud)

    if bestandsgrootte > MAX_FILE_SIZE:
        flash('Het bestand is te groot. De maximale bestandsgrootte is 16 MB.', 'danger')
        return redirect(url_for('app_docs.index', map_id=map_id))

    bestandsnaam = os.path.basename(bestand.filename)
    mime_type = bestand.content_type or mimetypes.guess_type(bestandsnaam)[0] or 'application/octet-stream'
    doc_type = _bepaal_bestandstype(bestandsnaam, mime_type)

    from utils.text_extractor import extraheer_tekst_uit_bestand
    tekst_inhoud = extraheer_tekst_uit_bestand(inhoud, bestandsnaam, mime_type)

    document = AppDocument(
        map_id=map_id,
        bestandsnaam=bestandsnaam,
        omschrijving=omschrijving or None,
        type=doc_type,
        mime_type=mime_type,
        bestandsgrootte=bestandsgrootte,
        inhoud=inhoud,
        tekst_inhoud=tekst_inhoud,
        aangemaakt_door_id=current_user.id
    )
    db.session.add(document)
    db.session.commit()

    flash(f'Document "{bestandsnaam}" ({round(bestandsgrootte / 1024, 1)} KB) is succesvol geüpload.', 'success')
    return redirect(url_for('app_docs.index', map_id=map_id))


@app_docs_bp.route('/<int:doc_id>/download')
@login_required
def download(doc_id):
    doc = AppDocument.query.filter_by(id=doc_id).first_or_404()
    return send_file(
        io.BytesIO(doc.inhoud),
        mimetype=doc.mime_type or 'application/octet-stream',
        download_name=doc.bestandsnaam,
        as_attachment=True
    )


@app_docs_bp.route('/<int:doc_id>/bekijken')
@login_required
def bekijken(doc_id):
    doc = AppDocument.query.filter_by(id=doc_id).first_or_404()
    safe_mimetypes = {'image/png', 'image/jpeg', 'image/gif', 'application/pdf'}
    mime = doc.mime_type or 'application/octet-stream'
    as_attachment = mime.lower().strip() not in safe_mimetypes

    response = send_file(
        io.BytesIO(doc.inhoud),
        mimetype=mime,
        download_name=doc.bestandsnaam,
        as_attachment=as_attachment
    )
    if not as_attachment:
        response.headers['Content-Security-Policy'] = "default-src 'none'; sandbox;"
    return response


@app_docs_bp.route('/<int:doc_id>/overschrijven', methods=['POST'])
@login_required
@platformbeheerder_required
def overschrijven(doc_id):
    doc = AppDocument.query.filter_by(id=doc_id).first_or_404()

    if 'bestand' not in request.files:
        flash('Geen nieuw bestand geselecteerd.', 'danger')
        return redirect(url_for('app_docs.index', map_id=doc.map_id))

    bestand = request.files['bestand']
    if not bestand or bestand.filename == '':
        flash('Geen nieuw bestand geselecteerd.', 'danger')
        return redirect(url_for('app_docs.index', map_id=doc.map_id))

    inhoud = bestand.read()
    bestandsgrootte = len(inhoud)

    if bestandsgrootte > MAX_FILE_SIZE:
        flash('Het nieuwe bestand is te groot. De maximale bestandsgrootte is 16 MB.', 'danger')
        return redirect(url_for('app_docs.index', map_id=doc.map_id))

    nieuwe_naam = os.path.basename(bestand.filename)
    mime_type = bestand.content_type or mimetypes.guess_type(nieuwe_naam)[0] or 'application/octet-stream'
    doc_type = _bepaal_bestandstype(nieuwe_naam, mime_type)

    from utils.text_extractor import extraheer_tekst_uit_bestand
    tekst_inhoud = extraheer_tekst_uit_bestand(inhoud, nieuwe_naam, mime_type)

    doc.bestandsnaam = nieuwe_naam
    doc.inhoud = inhoud
    doc.tekst_inhoud = tekst_inhoud
    doc.bestandsgrootte = bestandsgrootte
    doc.mime_type = mime_type
    doc.type = doc_type
    doc.versie += 1
    doc.gewijzigd_op = datetime.now(timezone.utc)
    doc.gewijzigd_door_id = current_user.id

    db.session.commit()
    flash(f'Document is overschreven met "{nieuwe_naam}". Versienummer is nu v{doc.versie}.', 'success')
    return redirect(url_for('app_docs.index', map_id=doc.map_id))


@app_docs_bp.route('/<int:doc_id>/bewerken', methods=['POST'])
@login_required
@platformbeheerder_required
def bewerken(doc_id):
    doc = AppDocument.query.filter_by(id=doc_id).first_or_404()

    bestandsnaam = request.form.get('bestandsnaam', '').strip()
    omschrijving = request.form.get('omschrijving', '').strip()

    if not bestandsnaam:
        flash('Bestandsnaam mag niet leeg zijn.', 'danger')
    else:
        doc.bestandsnaam = bestandsnaam
        doc.omschrijving = omschrijving or None
        doc.gewijzigd_op = datetime.now(timezone.utc)
        doc.gewijzigd_door_id = current_user.id
        db.session.commit()
        flash(f'Details voor document "{bestandsnaam}" zijn bijgewerkt.', 'success')

    return redirect(url_for('app_docs.index', map_id=doc.map_id))


@app_docs_bp.route('/<int:doc_id>/verwijderen', methods=['POST'])
@login_required
@platformbeheerder_required
def verwijderen(doc_id):
    doc = AppDocument.query.filter_by(id=doc_id).first_or_404()
    map_id = doc.map_id
    naam = doc.bestandsnaam

    db.session.delete(doc)
    db.session.commit()

    flash(f'Document "{naam}" is verwijderd.', 'success')
    return redirect(url_for('app_docs.index', map_id=map_id))
