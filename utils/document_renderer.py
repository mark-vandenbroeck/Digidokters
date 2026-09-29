"""
utils/document_renderer.py

Rendert diverse documentformaten naar gestructureerde HTML en data voor de in-browser viewer.
Ondersteunde formaten:
- Microsoft Word (.docx, .docm)
- Microsoft Excel & Spreadsheets (.xlsx, .xlsm, .csv, .tsv)
- Markdown (.md, .markdown)
- PDF (.pdf)
- Afbeeldingen (.png, .jpg, .jpeg, .gif, .webp, .svg)
- Platte tekst & Code (.txt, .json, .xml, .html, .log, .yaml, .yml, .sql, .py, .sh)
"""

import csv
import html
import io
import json
import os
import re


def _bepaal_extensie(bestandsnaam: str, mime_type: str = '') -> str:
    """Bepaalt de genormaliseerde bestandsextensie."""
    ext = os.path.splitext(bestandsnaam)[1].lower().lstrip('.') if bestandsnaam else ''
    if ext:
        return ext
    mime = (mime_type or '').lower()
    if 'pdf' in mime:
        return 'pdf'
    if 'word' in mime or 'document' in mime:
        return 'docx'
    if 'excel' in mime or 'sheet' in mime:
        return 'xlsx'
    if 'csv' in mime:
        return 'csv'
    if 'markdown' in mime or 'md' in mime:
        return 'md'
    if 'image' in mime:
        return 'png'
    return 'txt'


def _render_docx(inhoud_bytes: bytes) -> dict:
    """Rendert een Word (.docx) document naar semantische HTML."""
    try:
        import docx
        doc = docx.Document(io.BytesIO(inhoud_bytes))
    except Exception as e:
        return {
            'viewer_type': 'error',
            'error_message': f'Kon Word-document niet inlezen: {str(e)}'
        }

    html_parts = []
    paragraph_count = 0
    table_count = 0

    # Itereer over body elementen van het document
    for element in doc.element.body:
        tag = element.tag.split('}')[-1] if '}' in element.tag else element.tag

        if tag == 'p':
            # Vind de bijbehorende paragraph
            for p in doc.paragraphs:
                if p._element == element:
                    style_name = p.style.name.lower() if p.style and p.style.name else 'normal'
                    text = p.text.strip()
                    if not text and not p.runs:
                        continue

                    # Converteer runs met opmaak
                    run_html = []
                    for r in p.runs:
                        r_text = html.escape(r.text)
                        if not r_text:
                            continue
                        if r.bold:
                            r_text = f'<strong>{r_text}</strong>'
                        if r.italic:
                            r_text = f'<em>{r_text}</em>'
                        if r.underline:
                            r_text = f'<u>{r_text}</u>'
                        if r.font.strike:
                            r_text = f'<del>{r_text}</del>'
                        run_html.append(r_text)

                    p_content = ''.join(run_html) if run_html else html.escape(text)

                    # Bepaal heading of gewone paragraaf
                    if 'heading 1' in style_name or 'titel' in style_name or 'title' in style_name:
                        html_parts.append(f'<h1 class="docx-h1 border-bottom pb-2 mt-4 mb-3 text-dark">{p_content}</h1>')
                    elif 'heading 2' in style_name or 'kop 1' in style_name:
                        html_parts.append(f'<h2 class="docx-h2 mt-4 mb-2 text-dark">{p_content}</h2>')
                    elif 'heading 3' in style_name or 'kop 2' in style_name:
                        html_parts.append(f'<h3 class="docx-h3 mt-3 mb-2 text-dark">{p_content}</h3>')
                    elif 'heading 4' in style_name or 'kop 3' in style_name:
                        html_parts.append(f'<h4 class="docx-h4 mt-3 mb-2 text-dark">{p_content}</h4>')
                    elif 'list' in style_name or 'bullet' in style_name or 'opsomming' in style_name:
                        html_parts.append(f'<li class="docx-li">{p_content}</li>')
                    elif 'quote' in style_name or 'citaat' in style_name:
                        html_parts.append(f'<blockquote class="blockquote border-start border-primary border-3 ps-3 my-3 text-muted">{p_content}</blockquote>')
                    else:
                        html_parts.append(f'<p class="docx-p mb-2">{p_content}</p>')
                    
                    paragraph_count += 1
                    break

        elif tag == 'tbl':
            # Vind de bijbehorende tabel
            for t in doc.tables:
                if t._element == element:
                    table_rows = []
                    for row_idx, row in enumerate(t.rows):
                        cells_html = []
                        is_header = (row_idx == 0)
                        cell_tag = 'th' if is_header else 'td'
                        cell_class = 'bg-light fw-bold text-dark' if is_header else ''

                        for cell in row.cells:
                            cell_text = html.escape(cell.text.strip())
                            cells_html.append(f'<{cell_tag} class="{cell_class} p-2 align-top">{cell_text}</{cell_tag}>')

                        table_rows.append(f'<tr>{"".join(cells_html)}</tr>')

                    table_html = (
                        '<div class="table-responsive my-3">'
                        '<table class="table table-bordered table-hover docx-table mb-0">'
                        f'{"".join(table_rows)}'
                        '</table>'
                        '</div>'
                    )
                    html_parts.append(table_html)
                    table_count += 1
                    break

    full_html = '\n'.join(html_parts) if html_parts else '<p class="text-muted fst-italic">Het document bevat geen leesbare tekst.</p>'

    return {
        'viewer_type': 'word',
        'html_content': full_html,
        'paragraph_count': paragraph_count,
        'table_count': table_count,
    }


def _render_excel(inhoud_bytes: bytes, ext: str) -> dict:
    """Rendert Excel (.xlsx, .xlsm, .csv, .tsv) spreadsheets naar gestructureerde tabellen."""
    sheets = []

    if ext in ['csv', 'tsv']:
        # CSV of TSV parser
        try:
            try:
                tekst = inhoud_bytes.decode('utf-8')
            except UnicodeDecodeError:
                tekst = inhoud_bytes.decode('latin-1', errors='ignore')

            # Detecteer scheidingsteken
            delimiter = '\t' if ext == 'tsv' else (';' if ';' in tekst.splitlines()[0] else ',')
            reader = csv.reader(io.StringIO(tekst), delimiter=delimiter)
            all_rows = []
            for row in reader:
                all_rows.append([str(c).strip() for c in row])

            max_preview_rows = 500
            truncated = len(all_rows) > max_preview_rows
            display_rows = all_rows[:max_preview_rows]

            headers = display_rows[0] if display_rows else []
            data_rows = display_rows[1:] if len(display_rows) > 1 else []

            sheets.append({
                'name': 'Gegevens',
                'headers': headers,
                'rows': data_rows,
                'total_rows': len(all_rows),
                'total_cols': max(len(r) for r in all_rows) if all_rows else 0,
                'is_truncated': truncated,
                'max_rows': max_preview_rows,
            })
        except Exception as e:
            return {
                'viewer_type': 'error',
                'error_message': f'Kon CSV-bestand niet verwerken: {str(e)}'
            }
    else:
        # XLSX / XLSM parser via openpyxl
        try:
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(inhoud_bytes), data_only=True, read_only=True)
            max_preview_rows = 500

            for sheet in wb.worksheets:
                rows_gen = sheet.iter_rows(values_only=True)
                all_rows = []
                for row in rows_gen:
                    if row is not None and any(c is not None for c in row):
                        formatted_row = [
                            '' if c is None else (f"{c:.2f}" if isinstance(c, float) and abs(c - round(c, 2)) < 1e-6 else str(c))
                            for c in row
                        ]
                        all_rows.append(formatted_row)

                if not all_rows:
                    continue

                truncated = len(all_rows) > max_preview_rows
                display_rows = all_rows[:max_preview_rows]
                headers = display_rows[0] if display_rows else []
                data_rows = display_rows[1:] if len(display_rows) > 1 else []

                sheets.append({
                    'name': sheet.title,
                    'headers': headers,
                    'rows': data_rows,
                    'total_rows': len(all_rows),
                    'total_cols': max(len(r) for r in all_rows) if all_rows else 0,
                    'is_truncated': truncated,
                    'max_rows': max_preview_rows,
                })
        except Exception as e:
            return {
                'viewer_type': 'error',
                'error_message': f'Kon Excel-spreadsheet niet verwerken: {str(e)}'
            }

    if not sheets:
        sheets.append({
            'name': 'Blad 1',
            'headers': [],
            'rows': [],
            'total_rows': 0,
            'total_cols': 0,
            'is_truncated': False,
            'max_rows': 500,
        })

    return {
        'viewer_type': 'excel',
        'sheets': sheets,
    }


def _render_markdown(inhoud_bytes: bytes) -> dict:
    """Rendert een Markdown (.md) bestand naar veilige GitHub-stijl HTML."""
    try:
        try:
            tekst = inhoud_bytes.decode('utf-8')
        except UnicodeDecodeError:
            tekst = inhoud_bytes.decode('latin-1', errors='ignore')

        import markdown
        html_out = markdown.markdown(
            tekst,
            extensions=[
                'extra',
                'tables',
                'fenced_code',
                'nl2br',
                'sane_lists',
                'toc',
            ]
        )
        return {
            'viewer_type': 'markdown',
            'html_content': html_out,
            'raw_text': tekst,
            'line_count': len(tekst.splitlines()),
        }
    except Exception as e:
        return {
            'viewer_type': 'error',
            'error_message': f'Kon Markdown niet renderen: {str(e)}'
        }


def _render_text_or_code(inhoud_bytes: bytes, ext: str) -> dict:
    """Rendert platte tekst of codebestanden met regelnummers."""
    try:
        try:
            tekst = inhoud_bytes.decode('utf-8')
        except UnicodeDecodeError:
            tekst = inhoud_bytes.decode('latin-1', errors='ignore')

        # Formatteer JSON indien geldig
        if ext == 'json':
            try:
                parsed = json.loads(tekst)
                tekst = json.dumps(parsed, indent=2, ensure_ascii=False)
            except Exception:
                pass

        lines = tekst.splitlines()
        return {
            'viewer_type': 'text',
            'raw_text': tekst,
            'lines': lines,
            'line_count': len(lines),
            'ext': ext,
        }
    except Exception as e:
        return {
            'viewer_type': 'error',
            'error_message': f'Kon tekstbestand niet inlezen: {str(e)}'
        }


def render_document_preview(inhoud_bytes: bytes, bestandsnaam: str, mime_type: str = '') -> dict:
    """
    Hoofdfunctie om een document om te zetten naar viewer-data.
    Retourneert een dictionary met alle benodigde render-informatie voor de template.
    """
    if not inhoud_bytes:
        return {
            'viewer_type': 'error',
            'error_message': 'Het bestand is leeg of kon niet worden geladen.',
            'bestandsnaam': bestandsnaam,
            'ext': 'unknown',
        }

    ext = _bepaal_extensie(bestandsnaam, mime_type)
    mime = (mime_type or '').lower()

    base_result = {
        'bestandsnaam': bestandsnaam,
        'ext': ext,
        'bestandsgrootte': len(inhoud_bytes),
    }

    # 1. PDF
    if ext == 'pdf' or 'application/pdf' in mime:
        base_result.update({
            'viewer_type': 'pdf',
        })
        return base_result

    # 2. Afbeeldingen
    if ext in ['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'] or 'image/' in mime:
        base_result.update({
            'viewer_type': 'image',
        })
        return base_result

    # 3. Microsoft Word (.docx, .docm)
    if ext in ['docx', 'docm'] or 'word' in mime:
        res = _render_docx(inhoud_bytes)
        base_result.update(res)
        return base_result

    # 4. Spreadsheets (.xlsx, .xlsm, .csv, .tsv)
    if ext in ['xlsx', 'xlsm', 'csv', 'tsv'] or 'excel' in mime or 'spreadsheet' in mime:
        res = _render_excel(inhoud_bytes, ext)
        base_result.update(res)
        return base_result

    # 5. Markdown (.md, .markdown)
    if ext in ['md', 'markdown'] or 'markdown' in mime:
        res = _render_markdown(inhoud_bytes)
        base_result.update(res)
        return base_result

    # 6. Platte tekst & Broncode (.txt, .json, .xml, .html, .log, .yaml, .yml, .sql, .py, .sh, .css, .js)
    if ext in ['txt', 'json', 'xml', 'html', 'log', 'yaml', 'yml', 'sql', 'py', 'sh', 'css', 'js', 'ini', 'env', 'conf'] or 'text/' in mime or 'json' in mime:
        res = _render_text_or_code(inhoud_bytes, ext)
        base_result.update(res)
        return base_result

    # 7. Niet-ondersteund formaat
    base_result.update({
        'viewer_type': 'unsupported',
        'error_message': f'Voor bestandstype ".{ext}" is geen directe browser-viewer beschikbaar. Download het bestand om het lokaal te openen.'
    })
    return base_result
