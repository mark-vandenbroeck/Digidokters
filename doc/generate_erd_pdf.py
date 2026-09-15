"""Genereer een compleet en professioneel Entity-Relationship Diagram (ERD) in PDF formaat voor Digidokters."""
import os
import sys
from datetime import datetime
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import mm, cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
)
from reportlab.pdfgen import canvas
from reportlab.graphics.shapes import Drawing, Rect, String, Line


class NumberedCanvas(canvas.Canvas):
    """Canvas die paginanummers en consistente headers/footers in twee passes toevoegt."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_header_footer(num_pages)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def draw_header_footer(self, total_pages):
        self.saveState()
        self.setFont('Helvetica', 8)
        self.setFillColor(colors.HexColor('#64748B'))

        # Header (vanaf pagina 2)
        if self._pageNumber > 1:
            self.drawString(20 * mm, 198 * mm, "Digidokters Platform — Entity-Relationship Diagram (ERD)")
            self.drawRightString(277 * mm, 198 * mm, "Databankarchitectuur & Relatiemodel")
            self.setStrokeColor(colors.HexColor('#CBD5E1'))
            self.setLineWidth(0.5)
            self.line(20 * mm, 196 * mm, 277 * mm, 196 * mm)

        # Footer (op alle pagina's)
        self.setStrokeColor(colors.HexColor('#CBD5E1'))
        self.setLineWidth(0.5)
        self.line(20 * mm, 13 * mm, 277 * mm, 13 * mm)

        datum_str = datetime.now().strftime("%d-%m-%Y")
        self.drawString(20 * mm, 8.5 * mm, f"Digidokters v2.2 | Technisch Referentiedocument | Gegenereerd op {datum_str}")
        self.drawRightString(277 * mm, 8.5 * mm, f"Pagina {self._pageNumber} van {total_pages}")
        self.restoreState()


def draw_visual_erd():
    """Teken een overzichtelijk vector-gebaseerd ERD diagram met alle hoofddomeinen en relaties."""
    d = Drawing(710, 410)

    # Achtergrond canvas
    d.add(Rect(0, 0, 710, 410, fillColor=colors.HexColor('#F8FAFC'), strokeColor=colors.HexColor('#CBD5E1'), strokeWidth=1, rx=6, ry=6))

    # 1. LEGENDA (ONDERIN: y = 5, h = 21)
    d.add(Rect(10, 5, 690, 21, fillColor=colors.white, strokeColor=colors.HexColor('#CBD5E1'), strokeWidth=0.8, rx=4, ry=4))
    d.add(String(18, 11.5, "LEGENDA:", fillColor=colors.HexColor('#0F172A'), fontSize=7.5, fontName='Helvetica-Bold'))
    
    d.add(Rect(70, 9, 8, 8, fillColor=colors.HexColor('#DC2626'), strokeColor=None))
    d.add(String(82, 11.5, "PK: Primary Key", fillColor=colors.HexColor('#334155'), fontSize=7, fontName='Helvetica'))
    
    d.add(Rect(165, 9, 8, 8, fillColor=colors.HexColor('#2563EB'), strokeColor=None))
    d.add(String(177, 11.5, "FK: Foreign Key (1:N)", fillColor=colors.HexColor('#334155'), fontSize=7, fontName='Helvetica'))
    
    d.add(Rect(280, 9, 8, 8, fillColor=colors.HexColor('#D97706'), strokeColor=None))
    d.add(String(292, 11.5, "N:M: Veel-op-veel (Koppeltabel)", fillColor=colors.HexColor('#334155'), fontSize=7, fontName='Helvetica'))
    
    d.add(Rect(435, 9, 8, 8, fillColor=colors.HexColor('#059669'), strokeColor=None))
    d.add(String(447, 11.5, "Self-Ref: Historische Mapping (mapped_to_id)", fillColor=colors.HexColor('#334155'), fontSize=7, fontName='Helvetica'))
    
    d.add(Rect(630, 9, 8, 8, fillColor=colors.HexColor('#4338CA'), strokeColor=None))
    d.add(String(642, 11.5, "AI: Gemini NLP", fillColor=colors.HexColor('#334155'), fontSize=7, fontName='Helvetica'))

    # Domein-groeperingen (Containers)
    domains = [
        # RIJ 1 (Boven): y = 276, h = 128
        (10, 276, 215, 128, "1. MULTI-TENANCY & GEBRUIKERS", "#1D4ED8", "#EFF6FF"),
        (235, 276, 235, 128, "2. STAMGEGEVENS (MASTER DATA)", "#047857", "#ECFDF5"),
        (480, 276, 220, 128, "3. CONSULTATIES & REGISTRATIES", "#6D28D9", "#F5F3FF"),

        # RIJ 2 (Midden): y = 145, h = 124
        (10, 145, 215, 124, "4. AGENDA & VRIJWILLIGERS", "#B45309", "#FFFBEB"),
        (235, 145, 235, 124, "5. EVALUATIES & KWALITEIT", "#C2410C", "#FFF7ED"),
        (480, 145, 220, 124, "6. AI-VRAGENANALYSE", "#4338CA", "#EEF2FF"),

        # RIJ 3 (Onder): y = 32, h = 106
        (10, 32, 340, 106, "7. DOCUMENTBEHEER (TENANT & PLATFORM)", "#0E7490", "#ECFEFF"),
        (360, 32, 340, 106, "8. FEEDBACK & COMMUNICATIE", "#BE123C", "#FFF1F2"),
    ]

    for x, y, w, h, title, hdr_col, bg_col in domains:
        d.add(Rect(x, y, w, h, fillColor=colors.HexColor(bg_col), strokeColor=colors.HexColor(hdr_col), strokeWidth=1, rx=5, ry=5))
        d.add(Rect(x, y + h - 17, w, 17, fillColor=colors.HexColor(hdr_col), strokeColor=None, rx=5, ry=5))
        d.add(Rect(x, y + h - 17, w, 6, fillColor=colors.HexColor(hdr_col), strokeColor=None))
        d.add(String(x + 8, y + h - 12, title, fillColor=colors.white, fontSize=7.5, fontName='Helvetica-Bold'))

    # Helper om een entiteit-boxje te tekenen
    def entity_box(ex, ey, ew, eh, name, pk_txt, fks, tag_col="#1E293B"):
        d.add(Rect(ex, ey, ew, eh, fillColor=colors.white, strokeColor=colors.HexColor('#94A3B8'), strokeWidth=0.7, rx=3, ry=3))
        d.add(Rect(ex, ey + eh - 14, ew, 14, fillColor=colors.HexColor(tag_col), strokeColor=None, rx=3, ry=3))
        d.add(Rect(ex, ey + eh - 14, ew, 4, fillColor=colors.HexColor(tag_col), strokeColor=None))
        d.add(String(ex + 5, ey + eh - 10, name, fillColor=colors.white, fontSize=7.2, fontName='Helvetica-Bold'))
        d.add(String(ex + 5, ey + eh - 22, f"PK: {pk_txt}", fillColor=colors.HexColor('#DC2626'), fontSize=6.2, fontName='Helvetica-Bold'))
        curr_y = ey + eh - 30
        for fk in fks:
            d.add(String(ex + 5, curr_y, fk, fillColor=colors.HexColor('#475569'), fontSize=5.8, fontName='Helvetica'))
            curr_y -= 7.5

    # DOMEIN 1: Multi-Tenancy & Users (y: 276 .. 404)
    entity_box(18, 338, 95, 48, "organisaties", "id", ["naam (unique), slug", "actief, datum"], "#1D4ED8")
    entity_box(120, 338, 97, 48, "users", "id", ["email (unique), rol", "actief, reset_code"], "#1D4ED8")
    entity_box(18, 282, 95, 50, "user_organisaties", "id", ["FK user_id", "FK organisatie_id", "rol, actief"], "#2563EB")
    entity_box(120, 282, 97, 50, "audit_logs", "id", ["FK organisatie_id", "tabel, operatie", "record_id, timestamp"], "#3B82F6")

    # DOMEIN 2: Stamgegevens (y: 276 .. 404)
    entity_box(243, 338, 103, 48, "digidokters", "id", ["FK organisatie_id", "FK user_id (opt)", "naam, volgorde"], "#047857")
    entity_box(356, 338, 105, 48, "devices", "id", ["FK organisatie_id", "FK mapped_to_id (Self)", "naam, volgorde, actief"], "#047857")
    entity_box(243, 282, 103, 50, "age_categories", "id", ["FK organisatie_id", "FK mapped_to_id (Self)", "naam, volgorde, actief"], "#059669")
    entity_box(356, 282, 105, 50, "herkomst", "id", ["FK organisatie_id", "naam, volgorde", "actief"], "#059669")

    # DOMEIN 3: Consultaties & Registraties (y: 276 .. 404)
    entity_box(490, 282, 200, 104, "registrations", "id", [
        "FK organisatie_id   (1:N)",
        "FK digidokter_id    (1:N)",
        "FK toestel_id       (1:N -> devices)",
        "FK leeftijdscat_id  (1:N -> age_categories)",
        "FK herkomst_id      (1:N -> herkomst, opt)",
        "FK aangemaakt_door  (1:N -> users)",
        "datum, client, nieuwe_klant, geslacht",
        "onderwerp (volledige tekst voor AI analyse)"
    ], "#6D28D9")

    # DOMEIN 4: Agenda & Vrijwilligers (y: 145 .. 269)
    entity_box(18, 203, 95, 50, "locations", "id", ["FK organisatie_id", "naam, volgorde", "actief"], "#B45309")
    entity_box(120, 203, 97, 50, "activity_types", "id", ["FK organisatie_id", "naam, volgorde", "heeft_evaluatie, kleur"], "#B45309")
    entity_box(18, 151, 95, 48, "agenda_items", "id", ["FK type_id, loc_id", "datum, uur_van/tot", "FK organisatie_id"], "#D97706")
    entity_box(120, 151, 97, 48, "agenda_digidokters", "Composite", ["FK agenda_item_id", "FK digidokter_id", "(N:M koppeling)"], "#D97706")

    # DOMEIN 5: Evaluaties (y: 145 .. 269)
    entity_box(243, 203, 103, 50, "eval_formulieren", "id", ["FK organisatie_id", "FK activity_type_id", "titel, toelichting"], "#C2410C")
    entity_box(356, 203, 105, 50, "eval_vragen", "id", ["FK form_id", "vraag_tekst, type", "opties (JSON), volgorde"], "#C2410C")
    entity_box(243, 151, 103, 48, "eval_uitnodigingen", "id", ["FK agenda_item_id", "FK digidokter_id", "token (unique), status"], "#EA580C")
    entity_box(356, 151, 105, 48, "eval_reacties", "id", ["FK agenda, form, dd, user", "antwoorden (JSON)", "ingediend_op"], "#EA580C")

    # DOMEIN 6: AI-Vragenanalyse (y: 145 .. 269)
    entity_box(490, 208, 200, 45, "question_categories", "id", [
        "naam (unique), omschrijving",
        "volgorde, actief (platformbreed)"
    ], "#4338CA")
    entity_box(490, 151, 200, 52, "question_classifications", "id", [
        "FK registration_id (1:1 naar registrations)",
        "FK category_id     (1:N naar question_cat)",
        "zekerheid (score), model_naam",
        "is_handmatig_aangepast, FK user_id"
    ], "#4F46E5")

    # DOMEIN 7: Documentbeheer (y: 32 .. 138)
    entity_box(18, 38, 75, 74, "mappen", "id", ["FK organisatie", "FK parent_id (Self)", "naam, user_id"], "#0E7490")
    entity_box(99, 38, 77, 74, "documenten", "id", ["FK organisatie, map", "bestandsnaam, type", "inhoud (BLOB), FTS"], "#0E7490")
    entity_box(182, 38, 77, 74, "app_mappen", "id", ["(Platformbreed)", "FK parent_id (Self)", "naam, user_id"], "#0891B2")
    entity_box(265, 38, 77, 74, "app_documenten", "id", ["(Platformbreed)", "FK app_map_id", "bestandsnaam, BLOB"], "#0891B2")

    # DOMEIN 8: Feedback & Communicatie (y: 32 .. 138)
    entity_box(368, 67, 76, 45, "feedback_items", "id", ["FK org, user_id", "type, status, screenshot"], "#BE123C")
    entity_box(450, 67, 76, 45, "fb_reacties", "id", ["FK feedback_id", "FK user_id, tekst"], "#BE123C")
    entity_box(532, 67, 76, 45, "fb_stemmen", "id", ["FK feedback_id", "FK user_id, stem"], "#E11D48")
    entity_box(614, 67, 76, 45, "fb_views", "id", ["FK feedback_id", "FK user_id, bekeken_op"], "#E11D48")
    entity_box(368, 38, 322, 25, "email_templates", "id", ["sleutel (unique), naam, onderwerp, inhoud, variabelen"], "#9F1239")

    # Relatielijnen tussen de blokken
    def draw_rel(x1, y1, x2, y2, color_hex="#64748B", dashed=False):
        l = Line(x1, y1, x2, y2, strokeColor=colors.HexColor(color_hex), strokeWidth=1)
        if dashed:
            l.strokeDashArray = [2, 2]
        d.add(l)

    # Relatie Organisaties -> Registraties
    draw_rel(113, 362, 490, 362, "#2563EB", dashed=True)
    # Relatie Registraties -> Question Classification
    draw_rel(590, 282, 590, 203, "#6D28D9")
    # Relatie Agenda Items -> Agenda Digidokters
    draw_rel(113, 175, 120, 175, "#D97706")
    # Relatie Agenda Items -> Evaluatie Uitnodigingen
    draw_rel(113, 170, 243, 170, "#EA580C")
    # Relatie Evaluatie Formulieren -> Evaluatie Vragen
    draw_rel(346, 228, 356, 228, "#C2410C")
    # Relatie Feedback Items -> Reacties / Stemmen / Views
    draw_rel(444, 90, 450, 90, "#BE123C")
    draw_rel(526, 90, 532, 90, "#BE123C")
    draw_rel(608, 90, 614, 90, "#BE123C")

    return d


def create_erd_pdf(output_path):
    """Bouw het volledige multi-pagina ERD PDF rapport."""
    doc = SimpleDocTemplate(
        output_path,
        pagesize=landscape(A4),
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=15 * mm
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=colors.HexColor('#1E3A8A'),
        spaceAfter=2
    )
    subtitle_style = ParagraphStyle(
        'DocSub',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=13,
        textColor=colors.HexColor('#64748B'),
        spaceAfter=8
    )
    h1_style = ParagraphStyle(
        'H1',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=15,
        textColor=colors.HexColor('#0F172A'),
        spaceBefore=6,
        spaceAfter=4,
        keepWithNext=True
    )
    h2_style = ParagraphStyle(
        'H2',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9.5,
        leading=12,
        textColor=colors.HexColor('#1E40AF'),
        spaceBefore=5,
        spaceAfter=2,
        keepWithNext=True
    )
    body_style = ParagraphStyle(
        'Body',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.8,
        leading=10.5,
        textColor=colors.HexColor('#334155')
    )
    th_style = ParagraphStyle(
        'TH',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=6.8,
        leading=8.2,
        textColor=colors.white
    )
    td_style = ParagraphStyle(
        'TD',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=6.8,
        leading=8.2,
        textColor=colors.HexColor('#1E293B')
    )
    td_mono = ParagraphStyle(
        'TDMono',
        parent=styles['Normal'],
        fontName='Courier-Bold',
        fontSize=6.5,
        leading=8.2,
        textColor=colors.HexColor('#0F172A')
    )

    story = []

    # ==========================================
    # PAGINA 1: TITELBLAD & EXECUTIVE SUMMARY (PAST OP 1 PAGINA)
    # ==========================================
    story.append(Paragraph("Digidokters Platform — Databankarchitectuur & ERD", title_style))
    story.append(Paragraph("Technisch Referentiedocument: Entiteiten, Relaties, Kardinaliteiten & Data Dictionary", subtitle_style))

    meta_data = [
        [
            Paragraph("<b>Documentversie:</b> 2.2 (Multi-Tenant + Mapping)", body_style),
            Paragraph("<b>Datum:</b> 12 september 2026", body_style),
            Paragraph("<b>DBMS:</b> PostgreSQL / SQLite", body_style)
        ],
        [
            Paragraph("<b>ORM Framework:</b> SQLAlchemy 2.0 (Flask)", body_style),
            Paragraph("<b>Totaal Tabellen:</b> 28 entiteiten (33 FK relaties)", body_style),
            Paragraph("<b>Status:</b> Productie-architectuur", body_style)
        ]
    ]
    meta_table = Table(meta_data, colWidths=[85 * mm, 85 * mm, 91 * mm])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
        ('BOX', (0, 0), (-1, -1), 0.8, colors.HexColor('#E2E8F0')),
        ('INNERGRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#E2E8F0')),
        ('TOPPADDING', (0, 0), (-1, -1), 3.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3.5),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 6))

    story.append(Paragraph("1. Managementsamenvatting & Belangrijkste Architectuurprincipes", h1_style))
    arch_intro = (
        "Het <b>Digidokters-platform</b> is ontworpen als een schaalbaar multi-tenant systeem voor bibliotheken en welzijnsorganisaties. "
        "Het datamodel telt <b>28 tabellen</b> en is opgebouwd rond 5 kernpijlers: "
        "<b>(1) Strikte Multi-Tenancy:</b> data-isolatie op organisatieniveau via <code>organisatie_id</code>; "
        "<b>(2) Historische Consolidatie:</b> self-referencing <code>mapped_to_id</code> op stamgegevens om historische data zuiver te behouden; "
        "<b>(3) AI-Vragenclassificatie:</b> automatische categorisatie van consultatie-onderwerpen door Google Gemini; "
        "<b>(4) Agenda & Evaluatieloop:</b> sessiebeheer met vrijwilligerskoppeling (N:M) en one-time token evaluaties; "
        "<b>(5) Geïntegreerde Kennisbank & Feedback:</b> binaire blob-opslag met full-text search en ticketbeheer met stemmen en leesindicatoren."
    )
    story.append(Paragraph(arch_intro, body_style))
    story.append(Spacer(1, 6))

    story.append(Paragraph("2. Functioneel Overzicht van de 8 Subsystemen", h1_style))
    subsys_data = [
        [
            Paragraph("Subkader / Domein", th_style),
            Paragraph("Tabellen", th_style),
            Paragraph("Kernentiteiten", th_style),
            Paragraph("Primaire Verantwoordelijkheid & Databankrelaties", th_style)
        ],
        [
            Paragraph("<b>1. Multi-Tenancy & Auth</b>", td_style),
            Paragraph("4", td_style),
            Paragraph("organisaties, users, user_organisaties, audit_logs", td_mono),
            Paragraph("Tenant-isolatie, gebruikersaccounts, RBAC rollen, mutatie-auditing.", td_style)
        ],
        [
            Paragraph("<b>2. Stamgegevens (Master Data)</b>", td_style),
            Paragraph("6", td_style),
            Paragraph("digidokters, devices, age_categories, herkomst, locations, activity_types", td_mono),
            Paragraph("Configureerbare entiteiten per organisatie, volgorde-sortering en historische mapping.", td_style)
        ],
        [
            Paragraph("<b>3. Consultaties & Registraties</b>", td_style),
            Paragraph("1", td_style),
            Paragraph("registrations", td_mono),
            Paragraph("Centrale registraties van bezoeken, hulpvragen, toestellen, digidokters en doelgroepen.", td_style)
        ],
        [
            Paragraph("<b>4. Agenda & Planning</b>", td_style),
            Paragraph("2", td_style),
            Paragraph("agenda_items, agenda_digidokters", td_mono),
            Paragraph("Sessiebeheer, herhalende reeksen, vrijwilligersroostering via N:M koppeltabel.", td_style)
        ],
        [
            Paragraph("<b>5. Evaluaties & Kwaliteit</b>", td_style),
            Paragraph("4", td_style),
            Paragraph("evaluatie_formulieren, evaluatie_vragen, uitnodigingen, reacties", td_mono),
            Paragraph("Tevredenheidsmetingen na consultaties met beveiligde tokens en automatische herinneringen.", td_style)
        ],
        [
            Paragraph("<b>6. AI Vragenanalyse</b>", td_style),
            Paragraph("2", td_style),
            Paragraph("question_categories, question_classifications", td_mono),
            Paragraph("Gemini AI clustering, betrouwbaarheidsscores, trendmonitoring en handmatige overrides.", td_style)
        ],
        [
            Paragraph("<b>7. Documentenbeheer</b>", td_style),
            Paragraph("4", td_style),
            Paragraph("mappen, documenten, app_mappen, app_documenten", td_mono),
            Paragraph("Hiërarchische opslag van lokaal lesmateriaal én platformbrede handleidingen (blob + FTS).", td_style)
        ],
        [
            Paragraph("<b>8. Feedback & Communicatie</b>", td_style),
            Paragraph("5", td_style),
            Paragraph("feedback_items, reacties, stemmen, views, email_templates", td_mono),
            Paragraph("Interne tickets, bug- & wensenbeheer, up/downvotes, gelezen-status en e-mailsjablonen.", td_style)
        ],
    ]
    subsys_table = Table(subsys_data, colWidths=[52 * mm, 18 * mm, 96 * mm, 95 * mm])
    subsys_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E3A8A')),
        ('BOX', (0, 0), (-1, -1), 0.8, colors.HexColor('#CBD5E1')),
        ('INNERGRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#E2E8F0')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
        ('TOPPADDING', (0, 0), (-1, -1), 2.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(subsys_table)

    # ==========================================
    # PAGINA 2: VISUEEL OVERZICHTSDIAGRAM
    # ==========================================
    story.append(PageBreak())
    story.append(Paragraph("3. Visueel Entity-Relationship Diagram (Volledig Datamodel)", h1_style))
    story.append(Paragraph("Overzicht van alle 28 tabellen gegroepeerd per domein met primaire sleutels (PK), vreemde sleutels (FK) en relaties.", subtitle_style))
    story.append(draw_visual_erd())

    # ==========================================
    # HELPER VOOR GEDETAILLEERDE TABELSPECIFICATIES
    # ==========================================
    def build_entity_spec_table(entities):
        table_story = []
        for table_name, domain_title, header_hex, cols in entities:
            hdr_para = Paragraph(f"<b>Tabel:</b> <font name='Courier'><b>{table_name}</b></font> ({domain_title})", h2_style)
            
            rows = [
                [
                    Paragraph("Kolomnaam", th_style),
                    Paragraph("Datatype", th_style),
                    Paragraph("Sleutel / Relatie", th_style),
                    Paragraph("Nullable", th_style),
                    Paragraph("Omschrijving & Business Rule", th_style)
                ]
            ]
            for col_name, col_type, key_type, is_null, desc in cols:
                rows.append([
                    Paragraph(f"<b>{col_name}</b>", td_mono),
                    Paragraph(col_type, td_mono),
                    Paragraph(key_type, td_style),
                    Paragraph("Nee" if not is_null else "Ja", td_style),
                    Paragraph(desc, td_style)
                ])
            
            t = Table(rows, colWidths=[40 * mm, 28 * mm, 48 * mm, 17 * mm, 128 * mm])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(header_hex)),
                ('BOX', (0, 0), (-1, -1), 0.8, colors.HexColor('#CBD5E1')),
                ('INNERGRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#E2E8F0')),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
                ('TOPPADDING', (0, 0), (-1, -1), 1.6),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 1.6),
                ('LEFTPADDING', (0, 0), (-1, -1), 4),
                ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ]))
            table_story.append(KeepTogether([hdr_para, t, Spacer(1, 4)]))
        return table_story

    # ==========================================
    # PAGINA 3: DOMEIN 1 (MULTI-TENANCY & AUTH)
    # ==========================================
    story.append(PageBreak())
    story.append(Paragraph("4. Domeinspecificatie: Multi-Tenancy, Autorisatie & Auditing", h1_style))
    story.append(Paragraph("Beheert de tenant-organisaties, gebruikersaccounts, lidmaatschappen met specifieke rollen en centrale audit logging.", subtitle_style))

    d1_entities = [
        ("organisaties", "Multi-Tenancy", "#1D4ED8", [
            ("id", "INTEGER", "PK", False, "Unieke identificatie van de organisatie (tenant)."),
            ("naam", "VARCHAR(150)", "Unique", False, "Officiële naam van de organisatie of bibliotheek."),
            ("slug", "VARCHAR(80)", "Unique, Index", False, "URL-vriendelijke unieke identificatie."),
            ("actief", "BOOLEAN", "Default: True", False, "Bepaalt of de organisatie toegankelijk is op het platform."),
            ("aangemaakt_op", "DATETIME", "Audit", False, "Tijdstip van creatie van de organisatie (UTC).")
        ]),
        ("users", "Authenticatie & Profielen", "#1D4ED8", [
            ("id", "INTEGER", "PK", False, "Unieke gebruikersidentificatie."),
            ("naam", "VARCHAR(100)", "-", False, "Volledige naam van de medewerker of vrijwilliger."),
            ("email", "VARCHAR(150)", "Unique, Index", True, "Inlog- en notificatieadres van de gebruiker."),
            ("wachtwoord_hash", "VARCHAR(256)", "Werkzeug Hash", False, "Veilig gehashte wachtwoordreeks."),
            ("rol", "VARCHAR(20)", "Default: 'invoerder'", False, "Globale rol: 'platformbeheerder', 'beheerder', 'invoerder' of 'lezer'."),
            ("actief", "BOOLEAN", "Default: True", False, "Accountstatus; geblokkeerde gebruikers kunnen niet inloggen."),
            ("moet_wachtwoord_wijzigen", "BOOLEAN", "Default: False", False, "Forceert wachtwoordwissel bij de eerstvolgende aanmelding."),
            ("aangemaakt_op", "DATETIME", "Audit", False, "Registratiedatum van de gebruiker."),
            ("laatste_login", "DATETIME", "Audit", True, "Tijdstip van meest recente succesvolle login."),
            ("reset_code", "VARCHAR(6)", "OTP", True, "6-cijferige herstelcode voor wachtwoordreset."),
            ("reset_code_verloopt_op", "DATETIME", "OTP Expiry", True, "Vervaltijdstip van de herstelcode (standaard 15 minuten)."),
            ("reset_pogingen", "INTEGER", "Brute-force", True, "Aantal gefaalde pogingen voor de actieve resetcode.")
        ]),
        ("user_organisaties", "Tenant-Koppeling (N:M)", "#2563EB", [
            ("id", "INTEGER", "PK", False, "Koppelrecord identificatie."),
            ("user_id", "INTEGER", "FK -> users.id", False, "Verwijzing naar de gebruiker."),
            ("organisatie_id", "INTEGER", "FK -> organisaties.id", False, "Verwijzing naar de organisatie."),
            ("rol", "VARCHAR(20)", "Default: 'invoerder'", False, "Organisatiespecifieke rol ('beheerder', 'invoerder', 'lezer')."),
            ("actief", "BOOLEAN", "Default: True", False, "Status van het lidmaatschap in deze organisatie."),
            ("aangemaakt_op", "DATETIME", "Audit", False, "Tijdstip waarop koppeling tot stand kwam.")
        ]),
        ("audit_logs", "Mutatiehistoriek", "#3B82F6", [
            ("id", "INTEGER", "PK", False, "Uniek audit-ID."),
            ("organisatie_id", "INTEGER", "FK -> organisaties.id", False, "Organisatie waarbinnen de mutatie plaatsvond."),
            ("tabel", "VARCHAR(100)", "Index", False, "Naam van de gemuteerde databanktabel."),
            ("operatie", "VARCHAR(20)", "INSERT/UPDATE/DELETE", False, "Aard van de uitgevoerde databankbewerking."),
            ("record_id", "INTEGER", "-", True, "Primaire sleutel van het gewijzigde record."),
            ("gebruiker", "VARCHAR(100)", "-", True, "Naam of e-mail van de uitvoerende gebruiker."),
            ("timestamp", "DATETIME", "Default: now", False, "Exact tijdstip van de bewerking."),
            ("details", "TEXT", "JSON / String", True, "Gedetailleerde weergave van gewijzigde kolomwaarden.")
        ])
    ]
    story.extend(build_entity_spec_table(d1_entities))

    # ==========================================
    # PAGINA 4: DOMEIN 2 & 3 (STAMGEGEVENS & REGISTRATIES)
    # ==========================================
    story.append(PageBreak())
    story.append(Paragraph("5. Domeinspecificatie: Stamgegevens, Consultaties & Mapping", h1_style))
    story.append(Paragraph("Registreert individuele consultaties en koppelt deze aan stamgegevens met historische mapping (mapped_to_id) en volgorde-sortering.", subtitle_style))

    d2_entities = [
        ("registrations", "Consultaties & Bezoeken", "#6D28D9", [
            ("id", "INTEGER", "PK", False, "Uniek registratienummer."),
            ("organisatie_id", "INTEGER", "FK -> organisaties.id", False, "Organisatie waar het bezoek geregistreerd werd."),
            ("registratienummer", "VARCHAR(20)", "Formaat: JJJJ-XXXX", False, "Menselijk leesbaar volgnummer binnen het kalenderjaar."),
            ("datum", "DATE", "Index", False, "Datum van het digidokter-consult."),
            ("client", "VARCHAR(150)", "-", False, "Naam of identificatie van de bezoeker."),
            ("digidokter_id", "INTEGER", "FK -> digidokters.id", False, "Begeleidende vrijwilliger."),
            ("nieuwe_klant", "BOOLEAN", "Default: False", False, "Geeft aan of dit de eerste consultatie van de bezoeker betreft."),
            ("herkomst_id", "INTEGER", "FK -> herkomst.id", True, "Kanaal waarlangs de bezoeker bij de digidokter terechtkwam."),
            ("geslacht", "VARCHAR(10)", "'man', 'vrouw', 'onbekend'", True, "Geslacht van de bezoeker (t.b.v. demografische analyse)."),
            ("onderwerp", "TEXT", "-", False, "Volledige probleem- en vraagstelling van de bezoeker (invoer voor AI)."),
            ("leeftijdscategorie_id", "INTEGER", "FK -> age_categories.id", False, "Leeftijdscategorie van de bezoeker."),
            ("toestel_id", "INTEGER", "FK -> devices.id", False, "Toestel waarmee bezoeker hulp zocht."),
            ("aangemaakt_door_id", "INTEGER", "FK -> users.id", False, "Gebruiker die de registratie heeft ingevoerd."),
            ("aangemaakt_op", "DATETIME", "Audit", False, "Tijdstip van aanmaken."),
            ("gewijzigd_op", "DATETIME", "Audit", False, "Tijdstip van meest recente bewerking.")
        ]),
        ("devices", "Stamgegevens Toestellen", "#047857", [
            ("id", "INTEGER", "PK", False, "Toestel-ID."),
            ("organisatie_id", "INTEGER", "FK -> organisaties.id", False, "Eigenaar-organisatie."),
            ("naam", "VARCHAR(100)", "-", False, "Naam van het toesteltype (bijv. Laptop, Smartphone, Tablet)."),
            ("actief", "BOOLEAN", "Default: True", False, "Actieve keuzemogelijkheid in nieuwe invoerformulieren."),
            ("volgorde", "INTEGER", "Default: 0", False, "Volgorde in dropdown-lijsten en statistiekweergaven."),
            ("mapped_to_id", "INTEGER", "FK -> devices.id (Self)", True, "Consolidatiedoel: verwijst naar actieve vervanger voor historische data.")
        ]),
        ("age_categories", "Stamgegevens Leeftijdscategorieën", "#059669", [
            ("id", "INTEGER", "PK", False, "Leeftijdscategorie-ID."),
            ("organisatie_id", "INTEGER", "FK -> organisaties.id", False, "Eigenaar-organisatie."),
            ("naam", "VARCHAR(100)", "-", False, "Leeftijdsgroep (bijv. '<18', '18-25', '26-50', '50-65', '65+')."),
            ("actief", "BOOLEAN", "Default: True", False, "Actief in selectiemenu's."),
            ("volgorde", "INTEGER", "Default: 0", False, "Chronologische / logische volgorde in statistieken."),
            ("mapped_to_id", "INTEGER", "FK -> age_categories.id (Self)", True, "Consolidatiedoel voor historische/gedesactiveerde categorieën.")
        ]),
        ("digidokters", "Vrijwilligersprofielen", "#047857", [
            ("id", "INTEGER", "PK", False, "Digidokter-ID."),
            ("organisatie_id", "INTEGER", "FK -> organisaties.id", False, "Organisatie."),
            ("naam", "VARCHAR(100)", "Unique per Org", False, "Naam van de vrijwilliger."),
            ("user_id", "INTEGER", "FK -> users.id", True, "Optionele koppeling aan inlogaccount."),
            ("actief", "BOOLEAN", "Default: True", False, "Actieve inzetbaarheid."),
            ("volgorde", "INTEGER", "Default: 0", False, "Weergavevolgorde.")
        ]),
        ("herkomst", "Stamgegevens Herkomstkanalen", "#059669", [
            ("id", "INTEGER", "PK", False, "Herkomst-ID."),
            ("organisatie_id", "INTEGER", "FK -> organisaties.id", False, "Organisatie."),
            ("naam", "VARCHAR(100)", "-", False, "Kanaal (bijv. 'Website', 'Mond-aan-mond', 'Flyer')."),
            ("actief", "BOOLEAN", "Default: True", False, "Actieve status."),
            ("volgorde", "INTEGER", "Default: 0", False, "Sorteervolgorde.")
        ])
    ]
    story.extend(build_entity_spec_table(d2_entities))

    # ==========================================
    # PAGINA 5: DOMEIN 4 & 5 (AGENDA & EVALUATIES)
    # ==========================================
    story.append(PageBreak())
    story.append(Paragraph("6. Domeinspecificatie: Agenda, Vrijwilligersplanning & Evaluaties", h1_style))
    story.append(Paragraph("Beheert sessies, locaties, activiteitstypes, vrijwilligersbezetting en geautomatiseerde tevredenheidsmetingen.", subtitle_style))

    d3_entities = [
        ("agenda_items", "Sessiebeheer", "#B45309", [
            ("id", "INTEGER", "PK", False, "Sessie-ID."),
            ("organisatie_id", "INTEGER", "FK -> organisaties.id", False, "Organisatie."),
            ("datum", "DATE", "Index", False, "Datum van de activiteit."),
            ("uur_van", "VARCHAR(5)", "HH:MM", False, "Aanvangsuur van de sessie."),
            ("uur_tot", "VARCHAR(5)", "HH:MM", False, "Einduur van de sessie."),
            ("type_id", "INTEGER", "FK -> activity_types.id", False, "Activiteitstype (inloop, workshop, consult)."),
            ("locatie_id", "INTEGER", "FK -> locations.id", False, "Locatie van de activiteit."),
            ("omschrijving", "TEXT", "-", True, "Inhoudelijke omschrijving of instructies."),
            ("reeks_id", "VARCHAR(50)", "UUID", True, "Koppelt herhalende sessies binnen één reeks."),
            ("is_terugkerend", "BOOLEAN", "Default: False", False, "Geeft aan of de sessie deel uitmaakt van een herhaling."),
            ("interval", "VARCHAR(20)", "'wekelijks', etc.", True, "Herhaalfrequentie."),
            ("einddatum", "DATE", "-", True, "Einddatum van de herhalende reeks.")
        ]),
        ("agenda_digidokters", "Koppeltabel Vrijwilligers (N:M)", "#D97706", [
            ("agenda_item_id", "INTEGER", "PK, FK -> agenda_items.id", False, "Sessie waaraan de vrijwilliger deelneemt."),
            ("digidokter_id", "INTEGER", "PK, FK -> digidokters.id", False, "Ingezette vrijwilliger/digidokter.")
        ]),
        ("locations", "Stamgegevens Locaties", "#B45309", [
            ("id", "INTEGER", "PK", False, "Locatie-ID."),
            ("organisatie_id", "INTEGER", "FK -> organisaties.id", False, "Organisatie."),
            ("naam", "VARCHAR(150)", "-", False, "Benaming van de vestiging/zaal."),
            ("actief", "BOOLEAN", "Default: True", False, "Actieve status."),
            ("volgorde", "INTEGER", "Default: 0", False, "Sorteervolgorde.")
        ]),
        ("activity_types", "Stamgegevens Activiteitstypes", "#B45309", [
            ("id", "INTEGER", "PK", False, "Type-ID."),
            ("organisatie_id", "INTEGER", "FK -> organisaties.id", False, "Organisatie."),
            ("naam", "VARCHAR(100)", "-", False, "Naam (bijv. 'Open Inloop', 'Digicafé', 'Opleiding')."),
            ("actief", "BOOLEAN", "Default: True", False, "Actieve status."),
            ("heeft_evaluatie", "BOOLEAN", "Default: False", False, "Activeert automatische evaluatie-uitnodiging na afloop."),
            ("kleur", "VARCHAR(20)", "HEX kleurcode", True, "Visuele kleur in agendakalenders."),
            ("volgorde", "INTEGER", "Default: 0", False, "Sorteervolgorde.")
        ]),
        ("evaluatie_formulieren", "Formulierdefinities", "#C2410C", [
            ("id", "INTEGER", "PK", False, "Formulier-ID."),
            ("organisatie_id", "INTEGER", "FK -> organisaties.id", False, "Organisatie."),
            ("activity_type_id", "INTEGER", "FK -> activity_types.id", False, "Gekoppeld activiteitstype."),
            ("titel", "VARCHAR(150)", "-", False, "Titel van de evaluatie."),
            ("toelichting", "TEXT", "-", True, "Inleidende toelichting voor de respondent."),
            ("actief", "BOOLEAN", "Default: True", False, "Status van het formulier."),
            ("aangemaakt_op", "DATETIME", "Audit", False, "Aanmaakdatum."),
            ("gewijzigd_op", "DATETIME", "Audit", False, "Recentste wijzigingsdatum.")
        ]),
        ("evaluatie_vragen", "Vraagstellingen", "#C2410C", [
            ("id", "INTEGER", "PK", False, "Vraag-ID."),
            ("form_id", "INTEGER", "FK -> evaluatie_formulieren.id", False, "Gekoppeld formulier."),
            ("vraag_tekst", "TEXT", "-", False, "Vraagtekst."),
            ("type", "VARCHAR(30)", "'schaal', 'sterren', 'tekst'", False, "Type antwoordmechanisme."),
            ("opties", "JSON", "Keuzelijst", True, "Opties bij keuzelijst- of radiovragen."),
            ("volgorde", "INTEGER", "Default: 0", False, "Weergavevolgorde van de vraag in het formulier."),
            ("verplicht", "BOOLEAN", "Default: True", False, "Verplichte beantwoording.")
        ]),
        ("evaluatie_uitnodigingen", "Uitnodigingen & Tokens", "#EA580C", [
            ("id", "INTEGER", "PK", False, "Uitnodiging-ID."),
            ("agenda_item_id", "INTEGER", "FK -> agenda_items.id", False, "Betrokken sessie."),
            ("digidokter_id", "INTEGER", "FK -> digidokters.id", False, "Uitgenodigde vrijwilliger."),
            ("token", "VARCHAR(64)", "Unique, Index", False, "Cryptografische one-time access token."),
            ("verzonden_op", "DATETIME", "Audit", True, "Tijdstip van uitnodigingsmail."),
            ("is_ingevuld", "BOOLEAN", "Default: False", False, "Geeft aan of evaluatie reeds voltooid is."),
            ("herinnering_verzonden_op", "DATETIME", "Audit", True, "Tijdstip recentste herinnering."),
            ("herinnering_aantal", "INTEGER", "Default: 0", False, "Aantal verstuurde herinneringsmails.")
        ]),
        ("evaluatie_reacties", "Ingevulde Respons", "#EA580C", [
            ("id", "INTEGER", "PK", False, "Reactie-ID."),
            ("organisatie_id", "INTEGER", "FK -> organisaties.id", False, "Organisatie."),
            ("agenda_item_id", "INTEGER", "FK -> agenda_items.id", False, "Geëvalueerde sessie."),
            ("form_id", "INTEGER", "FK -> evaluatie_formulieren.id", False, "Gebruikt formulier."),
            ("digidokter_id", "INTEGER", "FK -> digidokters.id", True, "Vrijwilliger (indien niet anoniem)."),
            ("user_id", "INTEGER", "FK -> users.id", True, "Ingevuld door gebruiker."),
            ("ingediend_op", "DATETIME", "Default: now", False, "Tijdstip van indiening."),
            ("antwoorden", "JSON", "Key-value", False, "Ingevulde antwoorden gekoppeld aan vraag-ID's.")
        ])
    ]
    story.extend(build_entity_spec_table(d3_entities))

    # ==========================================
    # PAGINA 6: DOMEIN 6 & 7 (AI ANALYSE & DOCUMENTEN)
    # ==========================================
    story.append(PageBreak())
    story.append(Paragraph("7. Domeinspecificatie: AI-Vragenanalyse & Documentbeheer", h1_style))
    story.append(Paragraph("Verwerkt automatische categorisaties via Google Gemini en beheert de gestructureerde kennisbank (zowel organisatie- als platformbreed).", subtitle_style))

    d4_entities = [
        ("question_categories", "AI Vraagcategorieën (Platform)", "#4338CA", [
            ("id", "INTEGER", "PK", False, "Categorie-ID."),
            ("naam", "VARCHAR(100)", "Unique, Index", False, "Officiële categorienaam (bijv. 'E-mail', 'Itsme & Overheid', 'Hardware')."),
            ("omschrijving", "TEXT", "-", False, "Gedetailleerde beschrijving voor promptcontext en beheerder."),
            ("volgorde", "INTEGER", "Default: 0", False, "Sorteervolgorde in rapportages."),
            ("actief", "BOOLEAN", "Default: True", False, "Beschikbaarheid voor automatische classificatie."),
            ("aangemaakt_op", "DATETIME", "Audit", False, "Aanmaaktijdstip."),
            ("gewijzigd_op", "DATETIME", "Audit", False, "Recentste wijzigingstijdstip.")
        ]),
        ("question_classifications", "AI Classificatieresultaten", "#4F46E5", [
            ("id", "INTEGER", "PK", False, "Classificatie-ID."),
            ("registration_id", "INTEGER", "FK -> registrations.id (1:1)", False, "Uniek gekoppelde consultatie-registratie."),
            ("category_id", "INTEGER", "FK -> question_categories.id", False, "Toegekende vraagcategorie."),
            ("zekerheid", "FLOAT", "0.00 - 1.00", True, "AI betrouwbaarheidsscore (zekerheidspercentage)."),
            ("toelichting", "TEXT", "-", True, "Redenering / motivatie gegeven door het AI-model."),
            ("model_naam", "VARCHAR(50)", "-", True, "Gebruikte AI-modelidentificatie (bijv. 'gemini-1.5-flash')."),
            ("is_handmatig_aangepast", "BOOLEAN", "Default: False", False, "Indicator of beheerder de AI-classificatie overschreven heeft."),
            ("aangepast_door_id", "INTEGER", "FK -> users.id", True, "Gebruiker die handmatige override heeft doorgevoerd."),
            ("geclassificeerd_op", "DATETIME", "Audit", False, "Tijdstip van AI analyse."),
            ("gewijzigd_op", "DATETIME", "Audit", False, "Tijdstip van handmatige correctie.")
        ]),
        ("mappen", "Organisatie Documentmappen", "#0E7490", [
            ("id", "INTEGER", "PK", False, "Map-ID."),
            ("organisatie_id", "INTEGER", "FK -> organisaties.id", False, "Organisatie."),
            ("parent_id", "INTEGER", "FK -> mappen.id (Self)", True, "Bovenliggende map (ondersteunt oneindige boomstructuur)."),
            ("naam", "VARCHAR(100)", "-", False, "Mapnaam."),
            ("aangemaakt_op", "DATETIME", "Audit", False, "Aanmaaktijdstip."),
            ("aangemaakt_door_id", "INTEGER", "FK -> users.id", True, "Aanmaker van de map.")
        ]),
        ("documenten", "Organisatiedocumenten", "#0E7490", [
            ("id", "INTEGER", "PK", False, "Document-ID."),
            ("organisatie_id", "INTEGER", "FK -> organisaties.id", False, "Organisatie."),
            ("map_id", "INTEGER", "FK -> mappen.id", True, "Map waarin het document is ondergebracht."),
            ("bestandsnaam", "VARCHAR(255)", "-", False, "Oorspronkelijke bestandsnaam met extensie."),
            ("omschrijving", "TEXT", "-", True, "Optionele inhoudelijke samenvatting."),
            ("type", "VARCHAR(20)", "'pdf', 'docx', etc.", False, "Bestandsformaat."),
            ("mime_type", "VARCHAR(100)", "-", False, "MIME-type voor streaming en downloads."),
            ("bestandsgrootte", "INTEGER", "Bytes", False, "Grootte van het bestand in bytes."),
            ("inhoud", "BLOB", "Binaire payload", True, "Het fysieke bestand opgeslagen in de database."),
            ("tekst_inhoud", "TEXT", "FTS Search", True, "Geëxtraheerde tekstinhoud voor snelle full-text zoekopdrachten."),
            ("versie", "INTEGER", "Default: 1", False, "Versienummer van het bestand."),
            ("aangemaakt_op", "DATETIME", "Audit", False, "Uploadtijdstip."),
            ("aangemaakt_door_id", "INTEGER", "FK -> users.id", True, "Uploader."),
            ("gewijzigd_op", "DATETIME", "Audit", False, "Tijdstip laatste revisie."),
            ("gewijzigd_door_id", "INTEGER", "FK -> users.id", True, "Bewerker van de revisie.")
        ]),
        ("app_mappen", "Platform Documentmappen", "#0891B2", [
            ("id", "INTEGER", "PK", False, "Platformmap-ID."),
            ("parent_id", "INTEGER", "FK -> app_mappen.id (Self)", True, "Bovenliggende platformmap."),
            ("naam", "VARCHAR(100)", "-", False, "Mapnaam (globaal gedeeld over alle organisaties)."),
            ("aangemaakt_op", "DATETIME", "Audit", False, "Aanmaaktijdstip."),
            ("aangemaakt_door_id", "INTEGER", "FK -> users.id", True, "Platformbeheerder die map heeft aangemaakt.")
        ]),
        ("app_documenten", "Platformdocumenten", "#0891B2", [
            ("id", "INTEGER", "PK", False, "Platformdocument-ID (centraal lesmateriaal, handleidingen)."),
            ("map_id", "INTEGER", "FK -> app_mappen.id", True, "Maplocatie binnen platformstructuur."),
            ("bestandsnaam", "VARCHAR(255)", "-", False, "Bestandsnaam."),
            ("omschrijving", "TEXT", "-", True, "Omschrijving van het algemene document."),
            ("type", "VARCHAR(20)", "-", False, "Bestandstype."),
            ("mime_type", "VARCHAR(100)", "-", False, "MIME-formaat."),
            ("bestandsgrootte", "INTEGER", "Bytes", False, "Bestandsomvang."),
            ("inhoud", "BLOB", "-", True, "Binaire opslag van het document."),
            ("tekst_inhoud", "TEXT", "FTS", True, "Geëxtraheerde tekst voor platformzoekfunctie."),
            ("versie", "INTEGER", "Default: 1", False, "Versienummer."),
            ("aangemaakt_op", "DATETIME", "Audit", False, "Uploadtijdstip."),
            ("aangemaakt_door_id", "INTEGER", "FK -> users.id", True, "Aanmaker."),
            ("gewijzigd_op", "DATETIME", "Audit", False, "Wijzigingstijdstip."),
            ("gewijzigd_door_id", "INTEGER", "FK -> users.id", True, "Bewerker.")
        ])
    ]
    story.extend(build_entity_spec_table(d4_entities))

    # ==========================================
    # PAGINA 7: DOMEIN 8 & RELATIEMATRIX
    # ==========================================
    story.append(PageBreak())
    story.append(Paragraph("8. Domeinspecificatie: Feedback, Communicatie & E-mail", h1_style))
    story.append(Paragraph("Ondersteunt interne verbetersuggesties, bugrapportages, stemmen, ongelezen meldingen en dynamische e-mailsjablonen.", subtitle_style))

    d5_entities = [
        ("feedback_items", "Feedback Tickets", "#BE123C", [
            ("id", "INTEGER", "PK", False, "Feedback-ID."),
            ("organisatie_id", "INTEGER", "FK -> organisaties.id", False, "Organisatie van de indiener."),
            ("user_id", "INTEGER", "FK -> users.id", False, "Auteur van het feedbackitem."),
            ("type", "VARCHAR(30)", "'bug', 'wens', 'vraag', 'compliment'", False, "Aard van het feedbackticket."),
            ("onderwerp", "VARCHAR(200)", "-", False, "Korte titel van het item."),
            ("beschrijving", "TEXT", "-", False, "Gedetailleerde toelichting of stappenplan bij een fout."),
            ("screenshot_naam", "VARCHAR(255)", "-", True, "Bestandsnaam van optionele screenshot."),
            ("screenshot_mime", "VARCHAR(100)", "-", True, "MIME-type van screenshot."),
            ("screenshot_data", "BLOB", "-", True, "Binaire opslag van screenshotafbeelding."),
            ("is_afgesloten", "BOOLEAN", "Default: False", False, "Status of het ticket afgehandeld is."),
            ("afgesloten_op", "DATETIME", "Audit", True, "Tijdstip van afsluiten."),
            ("afgesloten_door_id", "INTEGER", "FK -> users.id", True, "Beheerder die ticket heeft gesloten."),
            ("aangemaakt_op", "DATETIME", "Audit", False, "Aanmaaktijdstip."),
            ("gewijzigd_op", "DATETIME", "Audit", False, "Recentste wijzigingstijdstip.")
        ]),
        ("feedback_reacties", "Commentaren op Feedback", "#BE123C", [
            ("id", "INTEGER", "PK", False, "Reactie-ID."),
            ("feedback_id", "INTEGER", "FK -> feedback_items.id", False, "Gekoppeld feedbackticket."),
            ("user_id", "INTEGER", "FK -> users.id", False, "Auteur van het commentaar."),
            ("tekst", "TEXT", "-", False, "Inhoud van het bericht."),
            ("aangemaakt_op", "DATETIME", "Default: now", False, "Plaatsingstijdstip.")
        ]),
        ("feedback_stemmen", "Upvotes & Downvotes", "#E11D48", [
            ("id", "INTEGER", "PK", False, "Stem-ID."),
            ("feedback_id", "INTEGER", "FK -> feedback_items.id", False, "Ticket waarop gestemd is."),
            ("user_id", "INTEGER", "FK -> users.id", False, "Gebruiker die de stem heeft uitgebracht."),
            ("stem", "SMALLINT", "+1 of -1", False, "Waardering van het verzoek."),
            ("aangemaakt_op", "DATETIME", "Default: now", False, "Tijdstip van stemmen.")
        ]),
        ("feedback_views", "Gelezen / Ongelezen Status", "#E11D48", [
            ("id", "INTEGER", "PK", False, "View-ID."),
            ("user_id", "INTEGER", "FK -> users.id", False, "Gebruiker die de pagina heeft bekeken."),
            ("feedback_id", "INTEGER", "FK -> feedback_items.id", False, "Bekeken feedback-item."),
            ("bekeken_op", "DATETIME", "Default: now", False, "Laatste timestamp waarop gebruiker de discussie bekeek.")
        ]),
        ("email_templates", "Dynamische E-mailsjablonen", "#9F1239", [
            ("id", "INTEGER", "PK", False, "Template-ID."),
            ("sleutel", "VARCHAR(50)", "Unique, Index", False, "Vaste code (bijv. 'welkomstmail', 'evaluatie_uitnodiging')."),
            ("naam", "VARCHAR(100)", "-", False, "Weergavenaam voor beheer."),
            ("onderwerp", "VARCHAR(200)", "-", False, "Onderwerpregel van de mail met variabelen."),
            ("inhoud", "TEXT", "HTML / Tekst", False, "Body van het sjabloon met {variabelen}."),
            ("beschrijving", "VARCHAR(255)", "-", True, "Functionele uitleg wanneer dit sjabloon getriggerd wordt."),
            ("beschikbare_variabelen", "VARCHAR(255)", "-", True, "Lijst van placeholders (bijv. '{naam}, {organisatie}, {link}')."),
            ("gewijzigd_op", "DATETIME", "Audit", False, "Tijdstip van recentste aanpassing.")
        ])
    ]
    story.extend(build_entity_spec_table(d5_entities))

    # ==========================================
    # PAGINA 8: FOREIGN KEY RELATIEMATRIX
    # ==========================================
    story.append(PageBreak())
    story.append(Paragraph("9. Integrale Foreign Key Relatiematrix (Kardinaliteiten)", h1_style))
    story.append(Paragraph("Volledig overzicht van alle 33 vreemde-sleutel relaties tussen de tabellen, inclusief kardinaliteiten en integriteitsregels.", subtitle_style))

    fks_data = [
        [
            Paragraph("Brontabel", th_style),
            Paragraph("Vreemde Sleutel (Bronkolom)", th_style),
            Paragraph("Doeltabel (Doelkolom)", th_style),
            Paragraph("Kardinaliteit", th_style),
            Paragraph("Rol & Functionele Betekenis", th_style)
        ],
        [Paragraph("user_organisaties", td_mono), Paragraph("user_id", td_mono), Paragraph("users.id", td_mono), Paragraph("N : 1", td_style), Paragraph("Gebruiker gekoppeld aan organisatie-lidmaatschap", td_style)],
        [Paragraph("user_organisaties", td_mono), Paragraph("organisatie_id", td_mono), Paragraph("organisaties.id", td_mono), Paragraph("N : 1", td_style), Paragraph("Organisatie gekoppeld aan gebruikerslidmaatschap", td_style)],
        [Paragraph("audit_logs", td_mono), Paragraph("organisatie_id", td_mono), Paragraph("organisaties.id", td_mono), Paragraph("N : 1", td_style), Paragraph("Tenant-scheiding voor audit entries", td_style)],
        [Paragraph("digidokters", td_mono), Paragraph("organisatie_id", td_mono), Paragraph("organisaties.id", td_mono), Paragraph("N : 1", td_style), Paragraph("Vrijwilliger behoort tot een specifieke organisatie", td_style)],
        [Paragraph("digidokters", td_mono), Paragraph("user_id", td_mono), Paragraph("users.id", td_mono), Paragraph("N : 1 (opt)", td_style), Paragraph("Optionele login-koppeling voor digidokter-vrijwilliger", td_style)],
        [Paragraph("devices", td_mono), Paragraph("organisatie_id", td_mono), Paragraph("organisaties.id", td_mono), Paragraph("N : 1", td_style), Paragraph("Toestelstamgegeven behoort tot organisatie", td_style)],
        [Paragraph("devices", td_mono), Paragraph("mapped_to_id", td_mono), Paragraph("devices.id", td_mono), Paragraph("N : 1 (Self)", td_style), Paragraph("Historische mapping van oud naar actief toesteltype", td_style)],
        [Paragraph("age_categories", td_mono), Paragraph("organisatie_id", td_mono), Paragraph("organisaties.id", td_mono), Paragraph("N : 1", td_style), Paragraph("Leeftijdscategorie behoort tot organisatie", td_style)],
        [Paragraph("age_categories", td_mono), Paragraph("mapped_to_id", td_mono), Paragraph("age_categories.id", td_mono), Paragraph("N : 1 (Self)", td_style), Paragraph("Historische mapping van oude naar actieve leeftijdscategorie", td_style)],
        [Paragraph("herkomst", td_mono), Paragraph("organisatie_id", td_mono), Paragraph("organisaties.id", td_mono), Paragraph("N : 1", td_style), Paragraph("Herkomstkanaal behoort tot organisatie", td_style)],
        [Paragraph("locations", td_mono), Paragraph("organisatie_id", td_mono), Paragraph("organisaties.id", td_mono), Paragraph("N : 1", td_style), Paragraph("Sessielocatie behoort tot organisatie", td_style)],
        [Paragraph("activity_types", td_mono), Paragraph("organisatie_id", td_mono), Paragraph("organisaties.id", td_mono), Paragraph("N : 1", td_style), Paragraph("Type activiteit behoort tot organisatie", td_style)],
        [Paragraph("registrations", td_mono), Paragraph("organisatie_id", td_mono), Paragraph("organisaties.id", td_mono), Paragraph("N : 1", td_style), Paragraph("Consultatie geregistreerd binnen organisatie (Tenant-isolatie)", td_style)],
        [Paragraph("registrations", td_mono), Paragraph("digidokter_id", td_mono), Paragraph("digidokters.id", td_mono), Paragraph("N : 1", td_style), Paragraph("Digidokter die het consult heeft verzorgd", td_style)],
        [Paragraph("registrations", td_mono), Paragraph("toestel_id", td_mono), Paragraph("devices.id", td_mono), Paragraph("N : 1", td_style), Paragraph("Geregistreerd toesteltype van de bezoeker", td_style)],
        [Paragraph("registrations", td_mono), Paragraph("leeftijdscategorie_id", td_mono), Paragraph("age_categories.id", td_mono), Paragraph("N : 1", td_style), Paragraph("Leeftijdscategorie van de bezoeker", td_style)],
        [Paragraph("registrations", td_mono), Paragraph("herkomst_id", td_mono), Paragraph("herkomst.id", td_mono), Paragraph("N : 1 (opt)", td_style), Paragraph("Optioneel herkomstkanaal van de bezoeker", td_style)],
        [Paragraph("registrations", td_mono), Paragraph("aangemaakt_door_id", td_mono), Paragraph("users.id", td_mono), Paragraph("N : 1", td_style), Paragraph("Gebruiker die de consultatie heeft geregistreerd", td_style)],
        [Paragraph("question_classifications", td_mono), Paragraph("registration_id", td_mono), Paragraph("registrations.id", td_mono), Paragraph("1 : 1", td_style), Paragraph("Unieke AI vraagclassificatie per registratie", td_style)],
        [Paragraph("question_classifications", td_mono), Paragraph("category_id", td_mono), Paragraph("question_categories.id", td_mono), Paragraph("N : 1", td_style), Paragraph("Toegekende platform-vraagcategorie", td_style)],
        [Paragraph("question_classifications", td_mono), Paragraph("aangepast_door_id", td_mono), Paragraph("users.id", td_mono), Paragraph("N : 1 (opt)", td_style), Paragraph("Beheerder die classificatie handmatig heeft aangepast", td_style)],
        [Paragraph("agenda_items", td_mono), Paragraph("organisatie_id", td_mono), Paragraph("organisaties.id", td_mono), Paragraph("N : 1", td_style), Paragraph("Agenda-item behoort tot organisatie", td_style)],
        [Paragraph("agenda_items", td_mono), Paragraph("locatie_id", td_mono), Paragraph("locations.id", td_mono), Paragraph("N : 1", td_style), Paragraph("Locatie waar de sessie plaatsvindt", td_style)],
        [Paragraph("agenda_items", td_mono), Paragraph("type_id", td_mono), Paragraph("activity_types.id", td_mono), Paragraph("N : 1", td_style), Paragraph("Activiteitstype van de sessie", td_style)],
        [Paragraph("agenda_digidokters", td_mono), Paragraph("agenda_item_id", td_mono), Paragraph("agenda_items.id", td_mono), Paragraph("N : M (Part)", td_style), Paragraph("Sessie-zijde van veel-op-veel vrijwilligerskoppeling", td_style)],
        [Paragraph("agenda_digidokters", td_mono), Paragraph("digidokter_id", td_mono), Paragraph("digidokters.id", td_mono), Paragraph("N : M (Part)", td_style), Paragraph("Vrijwilliger-zijde van veel-op-veel koppeling", td_style)],
        [Paragraph("evaluatie_formulieren", td_mono), Paragraph("organisatie_id", td_mono), Paragraph("organisaties.id", td_mono), Paragraph("N : 1", td_style), Paragraph("Formulier behoort tot organisatie", td_style)],
        [Paragraph("evaluatie_formulieren", td_mono), Paragraph("activity_type_id", td_mono), Paragraph("activity_types.id", td_mono), Paragraph("N : 1", td_style), Paragraph("Formulier gekoppeld aan activiteitstype", td_style)],
        [Paragraph("evaluatie_vragen", td_mono), Paragraph("form_id", td_mono), Paragraph("evaluatie_formulieren.id", td_mono), Paragraph("N : 1", td_style), Paragraph("Vraag behoort tot specifiek evaluatieformulier", td_style)],
        [Paragraph("evaluatie_uitnodigingen", td_mono), Paragraph("agenda_item_id", td_mono), Paragraph("agenda_items.id", td_mono), Paragraph("N : 1", td_style), Paragraph("Uitnodiging verzonden voor voltooide sessie", td_style)],
        [Paragraph("evaluatie_uitnodigingen", td_mono), Paragraph("digidokter_id", td_mono), Paragraph("digidokters.id", td_mono), Paragraph("N : 1", td_style), Paragraph("Vrijwilliger die de uitnodiging ontving", td_style)],
        [Paragraph("evaluatie_reacties", td_mono), Paragraph("agenda_item_id", td_mono), Paragraph("agenda_items.id", td_mono), Paragraph("N : 1", td_style), Paragraph("Ingevulde evaluatie gekoppeld aan sessie", td_style)],
        [Paragraph("mappen", td_mono), Paragraph("parent_id", td_mono), Paragraph("mappen.id", td_mono), Paragraph("N : 1 (Self)", td_style), Paragraph("Hiërarchische boomstructuur van mappen", td_style)],
        [Paragraph("documenten", td_mono), Paragraph("map_id", td_mono), Paragraph("mappen.id", td_mono), Paragraph("N : 1 (opt)", td_style), Paragraph("Locatie van document in mappenstructuur", td_style)],
        [Paragraph("app_mappen", td_mono), Paragraph("parent_id", td_mono), Paragraph("app_mappen.id", td_mono), Paragraph("N : 1 (Self)", td_style), Paragraph("Platformbrede maphiërarchie", td_style)],
        [Paragraph("app_documenten", td_mono), Paragraph("map_id", td_mono), Paragraph("app_mappen.id", td_mono), Paragraph("N : 1 (opt)", td_style), Paragraph("Locatie van platformdocument in app-mappen", td_style)],
        [Paragraph("feedback_items", td_mono), Paragraph("organisatie_id", td_mono), Paragraph("organisaties.id", td_mono), Paragraph("N : 1", td_style), Paragraph("Organisatie waaruit feedback afkomstig is", td_style)],
        [Paragraph("feedback_items", td_mono), Paragraph("user_id", td_mono), Paragraph("users.id", td_mono), Paragraph("N : 1", td_style), Paragraph("Melder van het feedback-item", td_style)],
        [Paragraph("feedback_reacties", td_mono), Paragraph("feedback_id", td_mono), Paragraph("feedback_items.id", td_mono), Paragraph("N : 1", td_style), Paragraph("Commentaar gekoppeld aan feedbackticket", td_style)],
        [Paragraph("feedback_stemmen", td_mono), Paragraph("feedback_id", td_mono), Paragraph("feedback_items.id", td_mono), Paragraph("N : 1", td_style), Paragraph("Stem uitgebracht op feedbackticket", td_style)],
        [Paragraph("feedback_views", td_mono), Paragraph("feedback_id", td_mono), Paragraph("feedback_items.id", td_mono), Paragraph("N : 1", td_style), Paragraph("Gelezen-markering op feedbackticket per gebruiker", td_style)]
    ]

    fks_table = Table(fks_data, colWidths=[38 * mm, 44 * mm, 44 * mm, 25 * mm, 110 * mm])
    fks_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0F172A')),
        ('BOX', (0, 0), (-1, -1), 0.8, colors.HexColor('#CBD5E1')),
        ('INNERGRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#E2E8F0')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
        ('TOPPADDING', (0, 0), (-1, -1), 1.1),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1.1),
        ('LEFTPADDING', (0, 0), (-1, -1), 3.5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3.5),
    ]))
    story.append(fks_table)

    # Document bouwen
    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"ERD PDF succesvol gegenereerd op: {output_path}")


if __name__ == '__main__':
    target = sys.argv[1] if len(sys.argv) > 1 else 'doc/Entity_Relationship_Diagram_Digidokters.pdf'
    create_erd_pdf(target)
