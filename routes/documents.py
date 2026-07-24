import io
import mimetypes
import os
from datetime import datetime, timezone
from flask import Blueprint, render_template, redirect, url_for, flash, request, send_file, current_app
from flask_login import login_required, current_user
from extensions import db
from models.document import Folder, Document
from utils.decorators import writer_required
from utils.tenant import filter_op_organisatie, get_huidige_organisatie_id, set_organisatie_id_op_model

doc_bp = Blueprint('doc', __name__, url_prefix='/documenten')

MAX_FILE_SIZE = 16 * 1024 * 1024  # 16 MB in bytes


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


@doc_bp.route('/')
@login_required
@writer_required
def index():
    org_id = get_huidige_organisatie_id()
    map_id = request.args.get('map_id', type=int)
    zoek = request.args.get('zoek', '').strip()

    huidige_map = None
    breadcrumbs = [{'id': None, 'naam': 'Documenten'}]

    if map_id:
        huidige_map = Folder.query.filter_by(id=map_id, organisatie_id=org_id).first()
        if huidige_map:
            # Bouw breadcrumbs op vanaf de root naar huidige map
            pad = []
            curr = huidige_map
            while curr:
                pad.append({'id': curr.id, 'naam': curr.naam})
                curr = curr.parent
            pad.reverse()
            breadcrumbs.extend(pad)
        else:
            flash('Gevraagde map werd niet gevonden.', 'warning')
            return redirect(url_for('doc.index'))

    if zoek:
        # Zoeken over alle mappen en documenten van deze organisatie
        mappen = filter_op_organisatie(
            Folder.query.filter(Folder.naam.ilike(f'%{zoek}%')), Folder
        ).order_by(Folder.naam).all()
        
        documenten = filter_op_organisatie(
            Document.query.filter(
                (Document.bestandsnaam.ilike(f'%{zoek}%')) |
                (Document.omschrijving.ilike(f'%{zoek}%'))
            ), Document
        ).order_by(Document.bestandsnaam).all()
    else:
        # Gewone mappenweergave op dit niveau (huidige map of root)
        mappen_query = Folder.query.filter_by(organisatie_id=org_id, parent_id=map_id)
        mappen = mappen_query.order_by(Folder.naam).all()

        documenten_query = Document.query.filter_by(organisatie_id=org_id, map_id=map_id)
        documenten = documenten_query.order_by(Document.bestandsnaam).all()

    # Statistieken voor huidige organisatie
    totaal_documenten = Document.query.filter_by(organisatie_id=org_id).count()
    totaal_grootte_bytes = db.session.query(db.func.sum(Document.bestandsgrootte))\
        .filter(Document.organisatie_id == org_id).scalar() or 0
    totaal_grootte_mb = round(totaal_grootte_bytes / (1024 * 1024), 2)

    return render_template(
        'documents/index.html',
        huidige_map=huidige_map,
        mappen=mappen,
        documenten=documenten,
        breadcrumbs=breadcrumbs,
        zoek=zoek,
        totaal_documenten=totaal_documenten,
        totaal_grootte_mb=totaal_grootte_mb,
        max_file_size_mb=16
    )


@doc_bp.route('/mappen/nieuw', methods=['POST'])
@login_required
@writer_required
def map_toevoegen():
    org_id = get_huidige_organisatie_id()
    naam = request.form.get('naam', '').strip()
    parent_id = request.form.get('parent_id', type=int)

    if not naam:
        flash('Vul een mapnaam in.', 'danger')
        return redirect(url_for('doc.index', map_id=parent_id))

    if parent_id:
        parent = Folder.query.filter_by(id=parent_id, organisatie_id=org_id).first()
        if not parent:
            flash('Bovenliggende map niet gevonden.', 'danger')
            return redirect(url_for('doc.index'))

    nieuwe_map = Folder(
        naam=naam,
        parent_id=parent_id,
        organisatie_id=org_id,
        aangemaakt_door_id=current_user.id
    )
    db.session.add(nieuwe_map)
    db.session.commit()
    flash(f'Map "{naam}" is succesvol aangemaakt.', 'success')
    return redirect(url_for('doc.index', map_id=parent_id))


@doc_bp.route('/mappen/<int:map_id>/hernoemen', methods=['POST'])
@login_required
@writer_required
def map_hernoemen(map_id):
    org_id = get_huidige_organisatie_id()
    folder = Folder.query.filter_by(id=map_id, organisatie_id=org_id).first_or_404()
    
    nieuwe_naam = request.form.get('naam', '').strip()
    if not nieuwe_naam:
        flash('Mapnaam mag niet leeg zijn.', 'danger')
    else:
        oude_naam = folder.naam
        folder.naam = nieuwe_naam
        db.session.commit()
        flash(f'Map "{oude_naam}" is hernoemd naar "{nieuwe_naam}".', 'success')
        
    return redirect(url_for('doc.index', map_id=folder.parent_id))


@doc_bp.route('/mappen/<int:map_id>/verwijderen', methods=['POST'])
@login_required
@writer_required
def map_verwijderen(map_id):
    org_id = get_huidige_organisatie_id()
    folder = Folder.query.filter_by(id=map_id, organisatie_id=org_id).first_or_404()
    
    parent_id = folder.parent_id
    naam = folder.naam
    
    db.session.delete(folder)
    db.session.commit()
    flash(f'Map "{naam}" en alle inhoud zijn succesvol verwijderd.', 'success')
    return redirect(url_for('doc.index', map_id=parent_id))


@doc_bp.route('/upload', methods=['POST'])
@login_required
@writer_required
def upload():
    org_id = get_huidige_organisatie_id()
    map_id = request.form.get('map_id', type=int)
    omschrijving = request.form.get('omschrijving', '').strip()

    if map_id:
        target_folder = Folder.query.filter_by(id=map_id, organisatie_id=org_id).first()
        if not target_folder:
            flash('Map niet gevonden.', 'danger')
            return redirect(url_for('doc.index'))

    if 'bestand' not in request.files:
        flash('Geen bestand geselecteerd.', 'danger')
        return redirect(url_for('doc.index', map_id=map_id))

    bestand = request.files['bestand']
    if not bestand or bestand.filename == '':
        flash('Geen bestand geselecteerd.', 'danger')
        return redirect(url_for('doc.index', map_id=map_id))

    inhoud = bestand.read()
    bestandsgrootte = len(inhoud)

    if bestandsgrootte > MAX_FILE_SIZE:
        flash('Het bestand is te groot. De maximale bestandsgrootte is 16 MB.', 'danger')
        return redirect(url_for('doc.index', map_id=map_id))

    bestandsnaam = os.path.basename(bestand.filename)
    mime_type = bestand.content_type or mimetypes.guess_type(bestandsnaam)[0] or 'application/octet-stream'
    doc_type = _bepaal_bestandstype(bestandsnaam, mime_type)

    document = Document(
        organisatie_id=org_id,
        map_id=map_id,
        bestandsnaam=bestandsnaam,
        omschrijving=omschrijving or None,
        type=doc_type,
        mime_type=mime_type,
        bestandsgrootte=bestandsgrootte,
        inhoud=inhoud,
        aangemaakt_door_id=current_user.id
    )
    db.session.add(document)
    db.session.commit()

    flash(f'Document "{bestandsnaam}" ({round(bestandsgrootte / 1024, 1)} KB) is succesvol geüpload.', 'success')
    return redirect(url_for('doc.index', map_id=map_id))


@doc_bp.route('/<int:doc_id>/download')
@login_required
@writer_required
def download(doc_id):
    org_id = get_huidige_organisatie_id()
    doc = Document.query.filter_by(id=doc_id, organisatie_id=org_id).first_or_404()
    
    response = send_file(
        io.BytesIO(doc.inhoud),
        mimetype=doc.mime_type or 'application/octet-stream',
        download_name=doc.bestandsnaam,
        as_attachment=True
    )
    return response


@doc_bp.route('/<int:doc_id>/bekijken')
@login_required
@writer_required
def bekijken(doc_id):
    org_id = get_huidige_organisatie_id()
    doc = Document.query.filter_by(id=doc_id, organisatie_id=org_id).first_or_404()
    
    # Whitelist safe file types for inline viewing. HTML/SVG/etc. will be forced as attachment download.
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
        # Add strict Content-Security-Policy to block execution of script content
        response.headers['Content-Security-Policy'] = "default-src 'none'; sandbox;"
    return response



@doc_bp.route('/<int:doc_id>/overschrijven', methods=['POST'])
@login_required
@writer_required
def overschrijven(doc_id):
    org_id = get_huidige_organisatie_id()
    doc = Document.query.filter_by(id=doc_id, organisatie_id=org_id).first_or_404()

    if 'bestand' not in request.files:
        flash('Geen nieuw bestand geselecteerd.', 'danger')
        return redirect(url_for('doc.index', map_id=doc.map_id))

    bestand = request.files['bestand']
    if not bestand or bestand.filename == '':
        flash('Geen nieuw bestand geselecteerd.', 'danger')
        return redirect(url_for('doc.index', map_id=doc.map_id))

    inhoud = bestand.read()
    bestandsgrootte = len(inhoud)

    if bestandsgrootte > MAX_FILE_SIZE:
        flash('Het nieuwe bestand is te groot. De maximale bestandsgrootte is 16 MB.', 'danger')
        return redirect(url_for('doc.index', map_id=doc.map_id))

    nieuwe_naam = os.path.basename(bestand.filename)
    mime_type = bestand.content_type or mimetypes.guess_type(nieuwe_naam)[0] or 'application/octet-stream'
    doc_type = _bepaal_bestandstype(nieuwe_naam, mime_type)

    doc.bestandsnaam = nieuwe_naam
    doc.inhoud = inhoud
    doc.bestandsgrootte = bestandsgrootte
    doc.mime_type = mime_type
    doc.type = doc_type
    doc.versie += 1
    doc.gewijzigd_op = datetime.now(timezone.utc)
    doc.gewijzigd_door_id = current_user.id

    db.session.commit()
    flash(f'Document is overschreven met "{nieuwe_naam}". Versienummer is nu v{doc.versie}.', 'success')
    return redirect(url_for('doc.index', map_id=doc.map_id))


@doc_bp.route('/<int:doc_id>/bewerken', methods=['POST'])
@login_required
@writer_required
def bewerken(doc_id):
    org_id = get_huidige_organisatie_id()
    doc = Document.query.filter_by(id=doc_id, organisatie_id=org_id).first_or_404()

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

    return redirect(url_for('doc.index', map_id=doc.map_id))


@doc_bp.route('/<int:doc_id>/verwijderen', methods=['POST'])
@login_required
@writer_required
def verwijderen(doc_id):
    org_id = get_huidige_organisatie_id()
    doc = Document.query.filter_by(id=doc_id, organisatie_id=org_id).first_or_404()

    map_id = doc.map_id
    naam = doc.bestandsnaam

    db.session.delete(doc)
    db.session.commit()

    flash(f'Document "{naam}" is verwijderd.', 'success')
    return redirect(url_for('doc.index', map_id=map_id))
