"""
PDF DEVIS — model tip foaiă franceză.

Layout (coloane, bandă Destinataire / Référence) calibrat după „devis Nr0009.ods“.
Tabel: antet + câte un rând per poziție (tabel normal).
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    Image,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from utils_fmt import eur

BASE_DIR = Path(__file__).resolve().parent
LOGO_SOURCE = BASE_DIR / "static" / "images" / "logo_source.png"


M_LEFT = 20 * mm
M_RIGHT = 18 * mm
M_TOP = 12 * mm
M_BOTTOM = 48 * mm

# Din ODS: co1×2 + co2…co5 față de zona cu Référence (co6…co10)
_MM = 1.0  # scala mm
_CO1_MM = 7.18 * _MM
_LEFT_BAND_MM = _CO1_MM * 2 + 72.09 + 19.72 + 19.00 + 23.32
_RIGHT_BAND_MM = 17.94 + 28.33 + 30.48 + 9.33 + 28.70
COL_LEFT_FRAC = _LEFT_BAND_MM / (_LEFT_BAND_MM + _RIGHT_BAND_MM)

# Lățimi coloane tabel (co2…co8 = 7 coloane „Description … Total TTC”; co9 din ODS = spațiu după tabel)
TABLE_COL_MM = [72.09, 19.72, 19.00, 23.32, 17.94, 28.33, 30.48]
TABLE_COL_SUM_MM = sum(TABLE_COL_MM)

FOOTER_GAP_BELOW_LINE = 5 * mm

FOOTER_COL1 = """<b>Siège social</b><br/>
MON ENTREPRISE<br/>
Dan Renov<br/>
22 Rue De Ferre<br/>
SIRET 994653657 RCS METZ<br/>
TVA : FR35994653657"""

FOOTER_COL2 = """<b>Coordonnées</b><br/>
Dan Vasile<br/>
Tel : 0686039752<br/>
E-mail: <font color="blue"><u>danrenov57@gmail.com</u></font>"""

FOOTER_COL3 = """<b>Détails bancaires</b><br/>
Banque :<br/>
Code banque :<br/>
N° de compte :<br/>
IBAN :<br/>
SWIFT/BIC :"""

META_VALUE_COL_W_MIN = 26 * mm
META_VALUE_COL_W_MAX = 44 * mm


def _fit_value_col_width(values: list[str], *, font_name: str, font_size: float) -> float:
    """Pick a value-column width so longest value ends near right margin."""
    max_w = 0.0
    for v in values:
        s = str(v or "")
        max_w = max(max_w, float(pdfmetrics.stringWidth(s, font_name, font_size)))
    # small breathing room so text doesn't touch the right edge
    w = max_w + 2 * mm
    if w < META_VALUE_COL_W_MIN:
        return META_VALUE_COL_W_MIN
    if w > META_VALUE_COL_W_MAX:
        return META_VALUE_COL_W_MAX
    return w

def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "mon_ent": ParagraphStyle(
            "me",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=14,
            alignment=TA_LEFT,
            leftIndent=0,
            firstLineIndent=0,
        ),
        "addr_under": ParagraphStyle(
            "au",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=10,
            leading=11.5,
            alignment=TA_LEFT,
            leftIndent=0,
            firstLineIndent=0,
        ),
        "devis_word": ParagraphStyle(
            "dw",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=14,
            textColor=colors.HexColor("#111111"),
            alignment=TA_LEFT,
            splitLongWords=0,
            leftIndent=0,
            firstLineIndent=0,
        ),
        "meta": ParagraphStyle(
            "meta",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=10,
            alignment=TA_LEFT,
            leftIndent=0,
            firstLineIndent=0,
        ),
        "meta_lbl": ParagraphStyle(
            "mlb",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=10,
            alignment=TA_LEFT,
            leftIndent=0,
            firstLineIndent=0,
        ),
        "meta_val": ParagraphStyle(
            "mval",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=10,
            alignment=TA_LEFT,
            leftIndent=0,
            firstLineIndent=0,
        ),
        "table_header": ParagraphStyle(
            "th",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=8.5,
            alignment=TA_CENTER,
            splitLongWords=0,
        ),
        "table_body": ParagraphStyle(
            "tb",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=9.9,
            alignment=TA_CENTER,
        ),
        "table_body_desc": ParagraphStyle(
            "tbd",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=9.9,
            alignment=TA_LEFT,
        ),
        "bold": ParagraphStyle(
            "b",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9.5,
            leading=11,
            alignment=TA_LEFT,
            leftIndent=0,
            firstLineIndent=0,
        ),
        "footer_small": ParagraphStyle(
            "fs",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=9.5,
            alignment=TA_LEFT,
            leftIndent=0,
            firstLineIndent=0,
        ),
        "sig_note": ParagraphStyle(
            "sig",
            parent=base["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=6.5,
            leading=7.5,
            textColor=colors.HexColor("#555555"),
            alignment=TA_LEFT,
        ),
    }


def _logo_image(path: Path, max_h: float, max_w: float) -> tuple[Any, float, float]:
    if not path.exists():
        w, h = max_w * 0.35, max_h
        return Spacer(w, h), w, h
    with PILImage.open(path) as im:
        im = im.convert("RGBA")
        iw, ih = im.size
    if ih <= 0:
        w, h = max_w * 0.35, max_h
        return Spacer(w, h), w, h
    aspect = iw / ih
    h = max_h
    w = h * aspect
    if w > max_w:
        w = max_w
        h = w / aspect
    return Image(str(path), width=w, height=h), w, h


def _tel_bold(phone_raw: str) -> str:
    raw = str(phone_raw).strip()
    esc = _escape_html(raw)
    for prefix in ("Tel :", "Tel:", "tel :", "tel:"):
        if raw.lower().startswith(prefix.lower()):
            rest = raw[len(prefix) :].strip()
            return f"<b>{_escape_html(prefix)}</b> <b>{_escape_html(rest)}</b>"
    return f"<b>Tel :</b> <b>{esc}</b>"


def _ods_table_col_widths(w_full: float) -> list[float]:
    """Proporții coloane tabel ca în LibreOffice (co2…co9)."""
    raw = [w_full * (mm / TABLE_COL_SUM_MM) for mm in TABLE_COL_MM]
    raw[-1] = w_full - sum(raw[:-1])
    return raw


def build_pdf(devis: dict[str, Any], *, kind: str = "devis") -> bytes:
    styles = _styles()

    def _make_story(doc_w: SimpleDocTemplate) -> list[Any]:
        story: list[Any] = []
        w_full = doc_w.width
        col_l = w_full * COL_LEFT_FRAC
        col_r = w_full * (1.0 - COL_LEFT_FRAC)
        
        # ----- Antet: stânga = MON ENTREPRISE + imediat sub adresă firmă (aceeași margine, fără gol uriaș de la logo)
        logo_max_h = 26 * mm
        logo_max_w = 30 * mm
        logo_cell, lw, _ = _logo_image(LOGO_SOURCE, logo_max_h, logo_max_w)
        kind_l = (kind or "devis").strip().lower()
        if kind_l not in ("devis", "facture"):
            kind_l = "devis"
        
        is_acompte = bool(devis.get("is_acompte")) if kind_l == "facture" else False
        title_word = "DEVIS" if kind_l == "devis" else ("FACTURE D'ACOMPTE" if is_acompte else "FACTURE")
        title_style = ParagraphStyle(
            "doc_title",
            parent=styles["devis_word"],
            alignment=TA_RIGHT,
            splitLongWords=0,
        )
        devis_word = Paragraph(title_word, title_style)
        
        addr_firm = Paragraph(
            "Dan Renov<br/>22 Rue De Ferre<br/>57070 Metz",
            styles["addr_under"],
        )
        left_header_stack = Table(
            [
                [Paragraph("<b>MON ENTREPRISE</b>", styles["mon_ent"])],
                [Spacer(1, 2 * mm)],
                [addr_firm],
            ],
            colWidths=[col_l],
        )
        left_header_stack.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
        
        # Antet: logo centrat perfect pe pagină (stil “titlu de carte”),
        # în timp ce blocul firmă rămâne la stânga și titlul documentului la dreapta.
        logo_w = max(lw, 20 * mm)
        side_w = max(10 * mm, (w_full - logo_w) / 2.0)
        # actualizează lățimea stivei din stânga pentru noua coloană
        left_header_stack._argW[0] = side_w  # type: ignore[attr-defined]
        header_top = Table([[left_header_stack, logo_cell, devis_word]], colWidths=[side_w, logo_w, side_w])
        header_top.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (1, 0), (1, 0), "CENTER"),
                    ("ALIGN", (2, 0), (2, 0), "RIGHT"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
        
        story.append(header_top)
        story.append(Spacer(1, 3 * mm))
        
        num_key = "devis_num" if kind_l == "devis" else "facture_num"
        ref_prefix = "DEVIS N°" if kind_l == "devis" else ("FACTURE D'ACOMPTE N°" if is_acompte else "FACTURE N°")
        ref = f"{ref_prefix}{devis[num_key]}"
        # În blocul de meta din dreapta, e suficient "N°xxxx" (labelul spune deja tipul documentului).
        ref_meta = f"N°{devis[num_key]}"
        tel_html = _tel_bold(devis["destinataire_telephone"])
        cp = str(devis.get("destinataire_cp") or "").strip()
        siret = str(devis.get("destinataire_siret") or "").strip()
        cp_line = f"{_escape_html(cp)}<br/>" if cp else ""
        siret_line = f"{_escape_html(siret)}<br/>" if siret else ""
        meta_left = Paragraph(
            f"<b>Destinataire</b><br/>"
            f"{_escape_html(devis['destinataire_nom'])}<br/>"
            f"{_escape_html(devis['destinataire_adresse'])}<br/>"
            f"{cp_line}"
            f"{siret_line}"
            f"{tel_html}",
            styles["meta"],
        )
        date_key = "date_devis" if kind_l == "devis" else "date_facture"
        ddv = _escape_html(devis[date_key])
        dv = _escape_html(devis["date_validite"])
        esc_ref = _escape_html(ref_meta)
        # Dreapta: două coloane fixe — etichete toate încep la aceeași margine stânga (col.1), valorile la aceeași margine (col.2)
        # Pentru "facture", etichetele sunt mai lungi; dăm mai mult spațiu valorilor (număr / dată),
        # ca să rămână pe un singur rând.
        if kind_l == "facture":
            meta_lbl_w = min(72 * mm, col_r - 34 * mm)
        else:
            meta_lbl_w = min(54 * mm, col_r - 26 * mm)
        meta_val_w = col_r - meta_lbl_w
        ml = styles["meta_lbl"]
        mv = styles["meta_val"]
        mv_col = ParagraphStyle("meta_val_col", parent=mv, alignment=TA_LEFT, splitLongWords=0)
        if kind_l == "devis":
            # Exact ca la facturi: etichetă + coloană fixă de valori,
            # astfel încât valorile sunt mereu între “linia verde” și “linia roșie”.
            val_w = META_VALUE_COL_W_MIN
            lbl_w = max(60 * mm, col_r - val_w)
            meta_lines = [
                [Paragraph("Référence du devis :", ml), Paragraph(esc_ref, mv_col)],
                [Paragraph("Date du devis :", ml), Paragraph(ddv, mv_col)],
                [Paragraph("<b>Date de validité du devis :</b>", ml), Paragraph(f"<b>{dv}</b>", mv_col)],
            ]
            meta_right = Table(meta_lines, colWidths=[lbl_w, col_r - lbl_w])
        else:
            # Factură: ':' la finalul etichetei, iar valorile stau într-o coloană fixă
            # (încep pe aceeași verticală și nu depășesc marginea din dreapta).
            ml_f = ParagraphStyle("ml_f", parent=ml, fontSize=8.2, leading=8.8, splitLongWords=0)
            mv_f = ParagraphStyle("mv_f", parent=mv, fontSize=9.5, leading=10, splitLongWords=0)
            mv_f_col = ParagraphStyle("mv_f_col", parent=mv_f, alignment=TA_LEFT)

            mp = _escape_html(str(devis.get("mode_paiement") or ""))
            # Pentru d'acompte: evităm ruperea între "facture" și "d'acompte" și alocăm mai mult spațiu etichetei.
            fac_phrase = "facture d'acompte" if is_acompte else "facture"
            fac_phrase_nb = "facture&nbsp;d'acompte" if is_acompte else "facture"
            valid_lbl_nb = f"Date&nbsp;de&nbsp;validité&nbsp;de&nbsp;la&nbsp;{fac_phrase_nb}"

            meta_lines = [
                [Paragraph(f"Référence de la {fac_phrase} :", ml_f), Paragraph(esc_ref, mv_f_col)],
                [Paragraph(f"Date de la {fac_phrase} :", ml_f), Paragraph(ddv, mv_f_col)],
                [Paragraph(f"<b>{valid_lbl_nb} :</b>", ml_f), Paragraph(f"<b>{dv}</b>", mv_f_col)],
                [Paragraph("<b>Mode de paiement :</b>", ml_f), Paragraph(f"<b>{mp}</b>", mv_f_col)],
            ]
            val_w = META_VALUE_COL_W_MIN
            lbl_w = max(60 * mm, col_r - val_w)
            meta_right = Table(meta_lines, colWidths=[lbl_w, col_r - lbl_w])
        label_push = 0 * mm
        # Nu atingem deloc coloana de valori; mutăm doar etichetele (câmpurile).
        # DEVIS + FACTURE normală:
        if kind_l == "devis" or (kind_l == "facture" and not is_acompte):
            label_push = 17 * mm
        # FACTURE D'ACOMPTE:
        if kind_l == "facture" and is_acompte:
            label_push = 2 * mm
        meta_right.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    # împinge DOAR etichetele (col 0) mai la dreapta
                    ("LEFTPADDING", (0, 0), (0, -1), label_push),
                    # Elimină padding-ul implicit ca valorile să ajungă exact la marginea dreaptă.
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    # Păstrează doar un mic spațiu între etichetă și valoare.
                    ("RIGHTPADDING", (0, 0), (0, -1), 2 * mm),
                    ("LEFTPADDING", (1, 0), (1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                ]
            )
        )
        meta_tbl = Table([[meta_left, meta_right]], colWidths=[col_l, col_r])
        meta_tbl.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
        story.append(meta_tbl)
        story.append(Spacer(1, 3 * mm))
        
        infos = devis.get("infos_additionnelles") or ""
        # Păstrează newline-urile ca <br/> și aliniază textul cu titlul.
        meta_infos = ParagraphStyle(
            "meta_infos",
            parent=styles["meta"],
            leftIndent=0,
            firstLineIndent=0,
        )
        infos_html = _escape_html(infos).replace("\n", "<br/>") if infos else "&nbsp;"
        infos_block = Table(
            [
                [Paragraph("<b>Informations additionnelles :</b>", styles["bold"])],
                [Spacer(1, 1.5 * mm)],
                [Paragraph(infos_html, meta_infos)],
            ],
            colWidths=[w_full],
        )
        infos_block.setStyle(
            TableStyle(
                [
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        story.append(infos_block)
        story.append(Spacer(1, 4 * mm))
        
        # ----- Tabel: antet + câte un rând per poziție (tabel normal)
        th = styles["table_header"]
        tb = styles["table_body"]
        tbd = styles["table_body_desc"]
        
        def hp(txt: str) -> Paragraph:
            t = (
                txt.replace("Prix unitaire", "Prix&nbsp;unitaire")
                .replace("% de TVA", "%&nbsp;de&nbsp;TVA")
            )
            return Paragraph(f"<b>{t}</b>", th)
        
        col_w = _ods_table_col_widths(w_full)
        
        header_row = [
            hp("Description"),
            hp("Quantité"),
            hp("Unité"),
            hp("Prix unitaire"),
            hp("% de TVA"),
            hp("Total TVA"),
            hp("Total TTC"),
        ]
        
        lignes = list(devis.get("lignes") or [])
        body_rows: list[list[Any]] = []
        if lignes:
            for x in lignes:
                u = _escape_html(str(x.get("unite", "")))
                up = x.get("unite_pow")
                if up is not None and str(up).strip() != "":
                    try:
                        up_i = int(up)
                    except Exception:
                        up_i = None
                    if up_i is not None:
                        u = f"{u}<super>{up_i}</super>"
                body_rows.append(
                    [
                        Paragraph(_escape_html(str(x["description"])), tbd),
                        Paragraph(str(int(x["quantite"])), tb),
                        Paragraph(u, tb),
                        Paragraph(eur(float(x["prix_unitaire"])), tb),
                        Paragraph(f"{int(x['taux_tva'])} %", tb),
                        Paragraph(eur(float(x["ligne_total_tva"])), tb),
                        Paragraph(eur(float(x["ligne_total_ttc"])), tb),
                    ]
                )
        else:
            body_rows.append(
                [
                    Paragraph("&nbsp;", tbd),
                    Paragraph("&nbsp;", tb),
                    Paragraph("&nbsp;", tb),
                    Paragraph("&nbsp;", tb),
                    Paragraph("&nbsp;", tb),
                    Paragraph("&nbsp;", tb),
                    Paragraph("&nbsp;", tb),
                ]
            )
        
        table_rows = [header_row, *body_rows]
        
        t = Table(
            table_rows,
            colWidths=col_w,
            # Nu repetăm antetul pe paginile următoare: continuăm doar cu rândurile de date.
            repeatRows=0,
        )
        ts = [
            ("GRID", (0, 0), (-1, -1), 0.4, colors.black),
            ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
            ("VALIGN", (0, 1), (0, -1), "TOP"),
            ("VALIGN", (1, 1), (6, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("ALIGN", (0, 1), (0, -1), "LEFT"),
            ("ALIGN", (1, 1), (6, -1), "CENTER"),
            ("LEFTPADDING", (0, 0), (-1, 0), 1.5),
            ("RIGHTPADDING", (0, 0), (-1, 0), 1.5),
            ("TOPPADDING", (0, 0), (-1, 0), 3),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 3),
            ("TOPPADDING", (0, 1), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 5),
            ("LEFTPADDING", (0, 1), (-1, -1), 3),
            ("RIGHTPADDING", (0, 1), (-1, -1), 3),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f5f5f5")),
        ]
        t.setStyle(TableStyle(ts))
        story.append(t)
        story.append(Spacer(1, 6 * mm))
        
        tot_ht = float(devis["total_ht"])
        # Total TVA din blocul de sub tabel trebuie să fie suma coloanei "Total TVA" din tabel.
        # Asta evită orice diferențe de formulă/rotunjire din payload.
        tot_tva = sum(float(x.get("ligne_total_tva") or 0.0) for x in (lignes or []))
        tot_ttc = float(devis["total_ttc"])
        
        # Bloc dreapta: etichete lipite de sume; aceeași verticală pentru €
        amt_w = 28 * mm
        lbl_w = 34 * mm
        block_w = lbl_w + amt_w
        
        tot_a = ParagraphStyle(
            "ta",
            parent=styles["meta"],
            fontSize=9,
            leading=11,
            alignment=TA_RIGHT,
            fontName="Helvetica",
        )
        tot_b_l = ParagraphStyle(
            "tbl",
            parent=styles["meta"],
            fontSize=9,
            leading=11,
            alignment=TA_RIGHT,
            fontName="Helvetica-Bold",
        )
        tot_b_a = ParagraphStyle(
            "tba",
            parent=styles["meta"],
            fontSize=9,
            leading=11,
            alignment=TA_RIGHT,
            fontName="Helvetica-Bold",
        )
        
        totals_inner = Table(
            [
                [Paragraph("Total HT :", tot_b_l), Paragraph(eur(tot_ht), tot_a)],
                [Paragraph("Total TVA :", tot_b_l), Paragraph(eur(tot_tva), tot_a)],
                [Paragraph("Total TTC :", tot_b_l), Paragraph(eur(tot_ttc), tot_b_a)],
            ],
            colWidths=[lbl_w, amt_w],
        )
        totals_inner.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                    ("LINEABOVE", (0, 2), (1, 2), 0.6, colors.black),
                    ("TOPPADDING", (0, 2), (-1, 2), 4),
                    ("TOPPADDING", (0, 0), (-1, 1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
        
        # Semnătură: lățime limită, aliniată la dreapta; doar text, fără marcatori grafici
        sig_w = w_full * 0.58
        if sig_w < block_w + 20 * mm:
            sig_w = block_w + 20 * mm
        sig_box_h = 26 * mm
        
        sig_para = ParagraphStyle(
            "sig2",
            parent=styles["sig_note"],
            fontName="Helvetica-Oblique",
            fontSize=7,
            leading=8.5,
            alignment=TA_RIGHT,
            textColor=colors.HexColor("#555555"),
            splitLongWords=0,
        )
        sig_note = Paragraph(
            "Signature du client (précédée de la mention « Bon pour accord »)",
            sig_para,
        )
        
        sig_inner = Table(
            [[sig_note]],
            colWidths=[sig_w],
            rowHeights=[sig_box_h],
        )
        sig_inner.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f6f6f6")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        
        # Totaluri + semnătură: mereu împreună (nu se despart între pagini).
        totals_wrap = Table(
            [[Spacer(w_full - block_w, 1), totals_inner]],
            colWidths=[w_full - block_w, block_w],
        )
        sig_wrap = Table(
            [[Spacer(w_full - sig_w, 1), sig_inner]],
            colWidths=[w_full - sig_w, sig_w],
        )
        story.append(KeepTogether([totals_wrap, Spacer(1, 4 * mm), sig_wrap]))
        return story
        
    def _footer(c: canvas.Canvas, doc_w: SimpleDocTemplate | None = None) -> None:
        """Desenat în banda marginii de jos: linia la limita cu story-ul, textul cât mai jos (fără suprapunere)."""
        c.saveState()
        # În anumite cazuri (ex. document cu o singură pagină), `doc` poate să nu fie disponibil pe canvas.
        # Folosim valorile din doc când există, altfel cădem pe constantele de layout (A4 + marginile definite sus).
        if doc_w is not None:
            page_w, _ = doc_w.pagesize
            left = float(doc_w.leftMargin)
            right = float(page_w - doc_w.rightMargin)
            bm = float(doc_w.bottomMargin)
        else:
            page_w, _ = A4
            left = float(M_LEFT)
            right = float(page_w - M_RIGHT)
            bm = float(M_BOTTOM)

        # Înainte: line_y = bm + 34mm → linia intra în cadru și footer-ul se desena peste semnătură.
        line_y = bm
        c.setStrokeColor(colors.black)
        c.setLineWidth(0.5)
        c.line(left, line_y, right, line_y)

        colw = (right - left) / 3.0
        x_pad = 2 * mm
        pad_bottom = 3 * mm
        content_top = line_y - FOOTER_GAP_BELOW_LINE
        max_h = max(12 * mm, content_top - pad_bottom)

        include_bank = bool(devis.get("include_bank_details"))
        iban = "FR7320041010101223622B03105" if include_bank else ""
        swift = "PSSTFRPPNCY" if include_bank else ""
        bank_txt = """<b>Détails bancaires</b><br/>
Banque :<br/>
Code banque :<br/>
N° de compte :<br/>
IBAN : <b>{iban}</b><br/>
SWIFT/BIC : <b>{swift}</b>""".format(
            iban=_escape_html(iban),
            swift=_escape_html(swift),
        )
        for i, txt in enumerate((FOOTER_COL1, FOOTER_COL2, bank_txt)):
            p = Paragraph(txt, styles["footer_small"])
            _pw, ph = p.wrap(colw - 2 * x_pad, max_h)
            y_bottom = max(pad_bottom, content_top - ph)
            p.drawOn(c, left + i * colw + x_pad, y_bottom)
        c.restoreState()

    class _FooterLastPageCanvas(Canvas):
        """
        Desenează footer-ul doar pe ultima pagină.

        ReportLab nu oferă direct totalul de pagini în `onPage`, așa că folosim
        tehnica standard: salvăm starea fiecărei pagini în `showPage`, iar în `save`
        re-randăm toate paginile și aplicăm footer-ul doar pe ultima.
        """

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self._saved_page_states: list[dict[str, Any]] = []

        def showPage(self) -> None:  # noqa: N802 (ReportLab API)
            self._saved_page_states.append(dict(self.__dict__))
            self._startPage()

        def save(self) -> None:  # noqa: A003 (ReportLab API)
            # IMPORTANT: nu adăugăm o pagină “în plus”.
            # ReportLab apelează `showPage()` pentru fiecare pagină reală, inclusiv ultima,
            # deci `self._saved_page_states` conține toate paginile din document.
            page_states = self._saved_page_states or [dict(self.__dict__)]
            total_pages = len(page_states)
            for idx, state in enumerate(page_states, start=1):
                self.__dict__.update(state)
                if idx == total_pages:
                    doc_w = getattr(self, "_doctemplate", None) or getattr(self, "doc", None)
                    _footer(self, doc_w if doc_w is not None else None)
                super().showPage()
            super().save()

    buf = BytesIO()
    doc_final = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=M_LEFT,
        rightMargin=M_RIGHT,
        topMargin=M_TOP,
        bottomMargin=M_BOTTOM,
    )
    doc_final.build(_make_story(doc_final), canvasmaker=_FooterLastPageCanvas)

    return buf.getvalue()


def _escape_html(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
