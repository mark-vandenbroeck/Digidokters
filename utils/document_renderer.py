"""
utils/document_renderer.py

Rendert diverse documentformaten naar gestructureerde HTML en data voor de in-browser viewer.
Ondersteunde formaten:
- Microsoft Word (.docx, .docm)
- OpenDocument Tekst (.odt)
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
import xml.etree.ElementTree as ET
import zipfile


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
    if 'opendocument.text' in mime or 'odt' in mime:
        return 'odt'
    if 'excel' in mime or 'sheet' in mime:
        return 'xlsx'
    if 'csv' in mime:
        return 'csv'
    if 'markdown' in mime or 'md' in mime:
        return 'md'
    if 'image' in mime:
        return 'png'
    return 'txt'


def _render_odt(inhoud_bytes: bytes) -> dict:
    """Rendert een OpenDocument Tekst (.odt) bestand naar semantische HTML."""
    try:
        with zipfile.ZipFile(io.BytesIO(inhoud_bytes)) as zf:
            if 'content.xml' not in zf.namelist():
                return {
                    'viewer_type': 'error',
                    'error_message': 'Ongeldig ODT-bestand: content.xml ontbreekt.'
                }
            content_xml = zf.read('content.xml')
            styles_xml = zf.read('styles.xml') if 'styles.xml' in zf.namelist() else None
    except Exception as e:
        return {
            'viewer_type': 'error',
            'error_message': f'Kon ODT-archief niet openen: {str(e)}'
        }

    try:
        root = ET.fromstring(content_xml)
        styles_root = ET.fromstring(styles_xml) if styles_xml else None

        NS = {
            'office': 'urn:oasis:names:tc:opendocument:xmlns:office:1.0',
            'text': 'urn:oasis:names:tc:opendocument:xmlns:text:1.0',
            'table': 'urn:oasis:names:tc:opendocument:xmlns:table:1.0',
            'style': 'urn:oasis:names:tc:opendocument:xmlns:style:1.0',
            'fo': 'urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0',
            'xlink': 'http://www.w3.org/1999/xlink',
        }

        # Parse text styles uit content.xml en styles.xml
        text_styles = {}
        all_roots = [root]
        if styles_root is not None:
            all_roots.append(styles_root)

        for r in all_roots:
            for style in r.findall('.//style:style', NS):
                s_name = style.attrib.get(f'{{{NS["style"]}}}name')
                t_prop = style.find('style:text-properties', NS)
                if s_name and t_prop is not None:
                    props = {}
                    fw = t_prop.attrib.get(f'{{{NS["fo"]}}}font-weight', '')
                    if 'bold' in fw or fw in ['700', '800', '900']:
                        props['bold'] = True
                    fs = t_prop.attrib.get(f'{{{NS["fo"]}}}font-style', '')
                    if 'italic' in fs or 'oblique' in fs:
                        props['italic'] = True
                    if 'underline' in str(t_prop.attrib.get(f'{{{NS["style"]}}}text-underline-style', '')):
                        props['underline'] = True
                    if t_prop.attrib.get(f'{{{NS["style"]}}}text-line-through-style'):
                        props['strike'] = True
                    text_styles[s_name] = props

        def render_inline(elem) -> str:
            out = []
            if elem.text:
                out.append(html.escape(elem.text))
            for child in elem:
                tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                if tag == 's':
                    count = int(child.attrib.get(f'{{{NS["text"]}}}c', 1))
                    out.append(' ' * count)
                elif tag == 'tab':
                    out.append('&emsp;')
                elif tag == 'line-break':
                    out.append('<br>')
                elif tag == 'a':
                    href = child.attrib.get(f'{{{NS["xlink"]}}}href', '#')
                    inner = render_inline(child)
                    out.append(f'<a href="{html.escape(href)}" target="_blank" rel="noopener noreferrer">{inner}</a>')
                elif tag == 'span':
                    s_name = child.attrib.get(f'{{{NS["text"]}}}style-name')
                    inner = render_inline(child)
                    style_info = text_styles.get(s_name, {})
                    if style_info.get('bold'):
                        inner = f'<strong>{inner}</strong>'
                    if style_info.get('italic'):
                        inner = f'<em>{inner}</em>'
                    if style_info.get('underline'):
                        inner = f'<u>{inner}</u>'
                    if style_info.get('strike'):
                        inner = f'<del>{inner}</del>'
                    out.append(inner)
                else:
                    out.append(render_inline(child))
                if child.tail:
                    out.append(html.escape(child.tail))
            return ''.join(out)

        body_text = root.find('.//office:text', NS)
        if body_text is None:
            return {
                'viewer_type': 'word',
                'html_content': '<p class="text-muted fst-italic">Het ODT-document bevat geen leesbare tekst.</p>',
                'paragraph_count': 0,
                'table_count': 0,
            }

        html_parts = []
        paragraph_count = 0
        table_count = 0

        for elem in body_text:
            tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
            if tag == 'h':
                level = elem.attrib.get(f'{{{NS["text"]}}}outline-level', '1')
                text_inner = render_inline(elem)
                if not text_inner.strip():
                    continue
                lvl = int(level) if level.isdigit() else 1
                lvl = max(1, min(lvl, 4))
                if lvl == 1:
                    html_parts.append(f'<h1 class="docx-h1 border-bottom pb-2 mt-4 mb-3 text-dark">{text_inner}</h1>')
                elif lvl == 2:
                    html_parts.append(f'<h2 class="docx-h2 mt-4 mb-2 text-dark">{text_inner}</h2>')
                elif lvl == 3:
                    html_parts.append(f'<h3 class="docx-h3 mt-3 mb-2 text-dark">{text_inner}</h3>')
                else:
                    html_parts.append(f'<h4 class="docx-h4 mt-3 mb-2 text-dark">{text_inner}</h4>')
                paragraph_count += 1

            elif tag == 'p':
                text_inner = render_inline(elem)
                if text_inner.strip():
                    html_parts.append(f'<p class="docx-p mb-2">{text_inner}</p>')
                    paragraph_count += 1

            elif tag == 'list':
                list_items = []
                for item in elem.findall('.//text:list-item', NS):
                    item_content = ' '.join(render_inline(p) for p in item.findall('text:p', NS))
                    if item_content.strip():
                        list_items.append(f'<li class="docx-li">{item_content}</li>')
                if list_items:
                    html_parts.append(f'<ul class="mb-3">{" ".join(list_items)}</ul>')
                    paragraph_count += len(list_items)

            elif tag == 'table':
                table_rows = []
                for row_idx, row in enumerate(elem.findall('.//table:table-row', NS)):
                    cells_html = []
                    is_header = (row_idx == 0)
                    cell_tag = 'th' if is_header else 'td'
                    cell_class = 'bg-light fw-bold text-dark' if is_header else ''
                    for cell in row.findall('table:table-cell', NS):
                        cell_inner = '<br>'.join(render_inline(p) for p in cell.findall('text:p', NS))
                        cells_html.append(f'<{cell_tag} class="{cell_class} p-2 align-top">{cell_inner}</{cell_tag}>')
                    table_rows.append(f'<tr>{" ".join(cells_html)}</tr>')
                if table_rows:
                    html_parts.append(
                        '<div class="table-responsive my-3">'
                        '<table class="table table-bordered table-hover docx-table mb-0">'
                        f'{" ".join(table_rows)}'
                        '</table>'
                        '</div>'
                    )
                    table_count += 1

        full_html = '\n'.join(html_parts) if html_parts else '<p class="text-muted fst-italic">Het ODT-document bevat geen leesbare tekst.</p>'

        return {
            'viewer_type': 'word',
            'html_content': full_html,
            'paragraph_count': paragraph_count,
            'table_count': table_count,
        }
    except Exception as e:
        return {
            'viewer_type': 'error',
            'error_message': f'Fout bij verwerken van ODT-inhoud: {str(e)}'
        }


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

    # 3. Microsoft Word (.docx, .docm) & OpenDocument Tekst (.odt)
    if ext in ['docx', 'docm'] or 'word' in mime:
        res = _render_docx(inhoud_bytes)
        base_result.update(res)
        return base_result

    if ext == 'odt' or 'opendocument.text' in mime:
        res = _render_odt(inhoud_bytes)
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
