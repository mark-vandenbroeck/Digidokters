"""Import en export routes."""
import os
from datetime import datetime, date
from flask import (Blueprint, render_template, redirect, url_for, flash,
                   request, send_file, current_app, abort)
from flask_login import login_required
from werkzeug.utils import secure_filename
from app import db
from models.digidokter import Digidokter
from models.age_category import AgeCategory
from models.device import Device
from utils.decorators import admin_required
from utils.import_handler import verwerk_import
from utils.export_handler import exporteer_csv, exporteer_xlsx

ie_bp = Blueprint('ie', __name__)

TOEGESTANE_EXTENSIES = {'.csv', '.xlsx', '.xls'}


def _ext_toegestaan(bestandsnaam: str) -> bool:
    return os.path.splitext(bestandsnaam)[1].lower() in TOEGESTANE_EXTENSIES


# ─── Importeren ──────────────────────────────────────────────────────────────

@ie_bp.route('/importeer', methods=['GET', 'POST'])
@login_required
@admin_required
def importeer():
    resultaat = None

    if request.method == 'POST':
        if 'bestand' not in request.files or request.files['bestand'].filename == '':
            flash('Geen bestand geselecteerd.', 'danger')
            return redirect(request.url)

        bestand = request.files['bestand']
        if not _ext_toegestaan(bestand.filename):
            flash('Ongeldig bestandsformaat. Gebruik CSV of XLSX.', 'danger')
            return redirect(request.url)

        bestandsnaam = secure_filename(bestand.filename)
        upload_pad = os.path.join(current_app.config['UPLOAD_FOLDER'], bestandsnaam)
        bestand.save(upload_pad)

        try:
            resultaat = verwerk_import(
                upload_pad,
                bestandsnaam,
                current_app.config['IMPORT_LOG_FOLDER']
            )
        finally:
            if os.path.exists(upload_pad):
                os.remove(upload_pad)

        if resultaat['fouten']:
            flash(f'Import voltooid met {len(resultaat["fouten"])} waarschuwingen.', 'warning')
        else:
            flash(f'Import geslaagd: {resultaat["toegevoegd"]} registraties toegevoegd.', 'success')

    return render_template('import_export/import.html', resultaat=resultaat)


@ie_bp.route('/importeer/log/<path:bestandsnaam>')
@login_required
@admin_required
def import_log(bestandsnaam):
    """Download een importlogbestand."""
    log_pad = os.path.join(current_app.config['IMPORT_LOG_FOLDER'], secure_filename(bestandsnaam))
    if not os.path.exists(log_pad):
        abort(404)
    return send_file(log_pad, as_attachment=True, download_name=bestandsnaam)


# ─── Exporteren ──────────────────────────────────────────────────────────────

@ie_bp.route('/exporteer', methods=['GET', 'POST'])
@login_required
@admin_required
def exporteer():
    digidokters = Digidokter.query.order_by(Digidokter.naam).all()
    leeftijdscategorieën = AgeCategory.query.order_by(AgeCategory.naam).all()
    toestellen = Device.query.order_by(Device.naam).all()

    if request.method == 'POST':
        formaat = request.form.get('formaat', 'csv')
        van_str = request.form.get('datum_van', '')
        tot_str = request.form.get('datum_tot', '')
        digidokter_id = request.form.get('digidokter_id', 0, type=int) or None
        leeftijdscategorie_id = request.form.get('leeftijdscategorie_id', 0, type=int) or None
        toestel_id = request.form.get('toestel_id', 0, type=int) or None

        van_datum = None
        tot_datum = None
        try:
            if van_str:
                van_datum = date.fromisoformat(van_str)
            if tot_str:
                tot_datum = date.fromisoformat(tot_str)
        except ValueError:
            flash('Ongeldige datumnotatie.', 'danger')
            return redirect(request.url)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        if formaat == 'xlsx':
            data = exporteer_xlsx(van_datum, tot_datum, digidokter_id, leeftijdscategorie_id, toestel_id)
            bestandsnaam = f'digidokters_export_{timestamp}.xlsx'
            mimetype = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        else:
            data = exporteer_csv(van_datum, tot_datum, digidokter_id, leeftijdscategorie_id, toestel_id)
            bestandsnaam = f'digidokters_export_{timestamp}.csv'
            mimetype = 'text/csv'

        import io
        return send_file(
            io.BytesIO(data if isinstance(data, bytes) else data),
            mimetype=mimetype,
            as_attachment=True,
            download_name=bestandsnaam,
        )

    return render_template(
        'import_export/export.html',
        digidokters=digidokters,
        leeftijdscategorieën=leeftijdscategorieën,
        toestellen=toestellen,
    )
