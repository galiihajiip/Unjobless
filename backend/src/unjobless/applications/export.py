"""CV and cover-letter export: DOCX (python-docx) and PDF (reportlab), two templates.

- `ats_classic`: single column, standard section headings, no icons/tables/columns, plain bullets.
- `modern_professional`: same structure with a restrained purple accent, rule lines and tighter type.
Both keep selectable text and clickable links. Files are versioned, stored privately and linked to
the vacancy + profile version. The master profile is never modified.
"""

from __future__ import annotations

import io
import os
import re
from datetime import datetime
from typing import Any, Literal

from sqlalchemy.orm import Session

from unjobless.applications.tailoring import resolved_document
from unjobless.core.errors import ValidationFailed
from unjobless.db.models import CoverLetter, ExportFile, JobVacancy, TailoredResume
from unjobless.ingestion.filestore import get_filestore

Template = Literal["ats_classic", "modern_professional"]
TEMPLATES = ("ats_classic", "modern_professional")
ACCENT = (0x59, 0x27, 0xB9)  # --brand-700
HEADINGS = {
    "id": {
        "summary": "Ringkasan",
        "experience": "Pengalaman",
        "projects": "Proyek",
        "education": "Pendidikan",
        "skills": "Keahlian",
        "certifications": "Sertifikasi",
        "awards": "Penghargaan",
        "publications": "Publikasi",
        "languages": "Bahasa",
        "present": "sekarang",
    },
    "en": {
        "summary": "Summary",
        "experience": "Experience",
        "projects": "Projects",
        "education": "Education",
        "skills": "Skills",
        "certifications": "Certifications",
        "awards": "Awards",
        "publications": "Publications",
        "languages": "Languages",
        "present": "present",
    },
}
FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
]


def _dates(start: str | None, end: str | None, lang: str) -> str:
    if not start and not end:
        return ""
    return f"{start or ''} – {end or HEADINGS[lang]['present']}".strip(" –")


def sections(doc: dict[str, Any]) -> list[tuple[str, list[dict[str, Any]]]]:
    """Template-independent section model shared by DOCX, PDF and the web preview."""
    h = HEADINGS[doc.get("language", "id")]
    lang = doc.get("language", "id")
    out: list[tuple[str, list[dict[str, Any]]]] = []
    if doc.get("summary"):
        out.append((h["summary"], [{"text": doc["summary"]}]))
    if doc["experiences"]:
        out.append(
            (
                h["experience"],
                [
                    {
                        "title": f"{e['title']} — {e['organization']}",
                        "meta": " · ".join(
                            x for x in [e.get("location"), _dates(e.get("start"), e.get("end"), lang)] if x
                        ),
                        "bullets": e["bullets"],
                    }
                    for e in doc["experiences"]
                ],
            )
        )
    if doc["projects"]:
        out.append(
            (
                h["projects"],
                [
                    {
                        "title": p["name"] + (f" — {p['role']}" if p.get("role") else ""),
                        "meta": ", ".join(p.get("technologies") or []),
                        "text": p.get("description"),
                        "bullets": p["bullets"],
                        "url": p.get("url"),
                    }
                    for p in doc["projects"]
                ],
            )
        )
    if doc["educations"]:
        out.append(
            (
                h["education"],
                [
                    {
                        "title": e["institution"],
                        "meta": " · ".join(
                            x
                            for x in [
                                " ".join(y for y in [e.get("degree"), e.get("field")] if y),
                                _dates(e.get("start"), e.get("end"), lang),
                                f"GPA {e['gpa']}" if e.get("gpa") else None,
                            ]
                            if x
                        ),
                    }
                    for e in doc["educations"]
                ],
            )
        )
    if doc["skills"]:
        out.append((h["skills"], [{"text": ", ".join(doc["skills"])}]))
    for key in ("certifications", "awards", "publications"):
        if doc.get(key):
            out.append(
                (
                    h[key],
                    [
                        {"text": " — ".join(x for x in [c.get("name"), c.get("issuer"), c.get("date")] if x)}
                        for c in doc[key]
                    ],
                )
            )
    if doc.get("languages"):
        out.append((h["languages"], [{"text": ", ".join(doc["languages"])}]))
    return out


def _contact_line(doc: dict[str, Any]) -> str:
    c = doc["contact"]
    return " · ".join(
        x for x in [c.get("email"), c.get("phone"), c.get("location"), *doc.get("links", [])[:3]] if x
    )


# ---------------------------------------------------------------- DOCX


def render_docx(doc: dict[str, Any], template: Template) -> bytes:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Pt, RGBColor

    d = Document()
    modern = template == "modern_professional"
    st = d.styles["Normal"]
    st.font.name = "Calibri"
    st.font.size = Pt(10.5 if modern else 11)
    for s in d.sections:
        from docx.shared import Cm

        s.left_margin = s.right_margin = Cm(2.0)
        s.top_margin = s.bottom_margin = Cm(1.8)
    name = doc["contact"].get("full_name") or ""
    p = d.add_paragraph()
    r = p.add_run(name)
    r.bold = True
    r.font.size = Pt(20 if modern else 16)
    if modern:
        r.font.color.rgb = RGBColor(*ACCENT)
    if doc.get("headline"):
        hp = d.add_paragraph(doc["headline"])
        hp.runs[0].italic = modern
    contact = _contact_line(doc)
    if contact:
        cp = d.add_paragraph()
        for i, part in enumerate(contact.split(" · ")):
            if i:
                cp.add_run(" · ")
            if part.startswith("http"):
                _hyperlink(cp, part, part, qn, OxmlElement)
            else:
                cp.add_run(part)
    for title, items in sections(doc):
        hp = d.add_paragraph()
        hr = hp.add_run(title.upper() if not modern else title)
        hr.bold = True
        hr.font.size = Pt(12)
        if modern:
            hr.font.color.rgb = RGBColor(*ACCENT)
            _bottom_border(hp, qn, OxmlElement)
        for it in items:
            if it.get("title"):
                tp = d.add_paragraph()
                tp.add_run(it["title"]).bold = True
                if it.get("meta"):
                    tp.add_run(f"  |  {it['meta']}" if not modern else f"\n{it['meta']}").italic = modern
            if it.get("text"):
                d.add_paragraph(it["text"])
            for b in it.get("bullets", []) or []:
                d.add_paragraph(b, style="List Bullet")
            if it.get("url"):
                up = d.add_paragraph()
                _hyperlink(up, it["url"], it["url"], qn, OxmlElement)
    d.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.LEFT
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def _hyperlink(paragraph: Any, url: str, text: str, qn: Any, OxmlElement: Any) -> None:
    part = paragraph.part
    r_id = part.relate_to(
        url, "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink", is_external=True
    )
    link = OxmlElement("w:hyperlink")
    link.set(qn("r:id"), r_id)
    run = OxmlElement("w:r")
    rpr = OxmlElement("w:rPr")
    u = OxmlElement("w:u")
    u.set(qn("w:val"), "single")
    rpr.append(u)
    run.append(rpr)
    t = OxmlElement("w:t")
    t.text = text
    run.append(t)
    link.append(run)
    paragraph._p.append(link)


def _bottom_border(paragraph: Any, qn: Any, OxmlElement: Any) -> None:
    ppr = paragraph._p.get_or_add_pPr()
    bdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    for k, v in (("w:val", "single"), ("w:sz", "6"), ("w:space", "1"), ("w:color", "D6BEFF")):
        bottom.set(qn(k), v)
    bdr.append(bottom)
    ppr.append(bdr)


# ---------------------------------------------------------------- PDF

_FONT: tuple[str, str] | None = None


def _fonts() -> tuple[str, str]:
    global _FONT
    if _FONT:
        return _FONT
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont("UJSans", path))
                bold = path.replace("DejaVuSans.ttf", "DejaVuSans-Bold.ttf")
                if bold != path and os.path.exists(bold):
                    pdfmetrics.registerFont(TTFont("UJSans-Bold", bold))
                    _FONT = ("UJSans", "UJSans-Bold")
                else:
                    _FONT = ("UJSans", "UJSans")
                return _FONT
            except Exception:  # noqa: S112
                continue
    _FONT = ("Helvetica", "Helvetica-Bold")
    return _FONT


def _esc(s: str) -> str:
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    if _fonts()[0] == "Helvetica":
        s = s.encode("cp1252", errors="replace").decode("cp1252")
    return s


def render_pdf(doc: dict[str, Any], template: Template) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import HRFlowable, ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer

    regular, bold = _fonts()
    modern = template == "modern_professional"
    accent = colors.Color(ACCENT[0] / 255, ACCENT[1] / 255, ACCENT[2] / 255)
    base = ParagraphStyle(
        "base", fontName=regular, fontSize=10 if modern else 10.5, leading=13.5 if modern else 14
    )
    name_st = ParagraphStyle(
        "name",
        parent=base,
        fontName=bold,
        fontSize=19 if modern else 16,
        leading=23,
        textColor=accent if modern else colors.black,
    )
    head_st = ParagraphStyle(
        "head",
        parent=base,
        fontName=bold,
        fontSize=11.5,
        leading=15,
        spaceBefore=9,
        spaceAfter=3,
        textColor=accent if modern else colors.black,
    )
    title_st = ParagraphStyle("title", parent=base, fontName=bold, spaceBefore=4)
    meta_st = ParagraphStyle("meta", parent=base, textColor=colors.Color(0.33, 0.33, 0.39), fontSize=9.5)
    buf = io.BytesIO()
    pdf = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=1.7 * cm,
        bottomMargin=1.7 * cm,
        title=f"CV {doc['contact'].get('full_name') or ''}".strip(),
        author=doc["contact"].get("full_name") or "",
    )
    story: list[Any] = [Paragraph(_esc(doc["contact"].get("full_name") or ""), name_st)]
    if doc.get("headline"):
        story.append(Paragraph(_esc(doc["headline"]), base))
    contact = _contact_line(doc)
    if contact:
        parts = [
            f'<link href="{_esc(p)}" color="blue">{_esc(p)}</link>' if p.startswith("http") else _esc(p)
            for p in contact.split(" · ")
        ]
        story.append(Paragraph(" · ".join(parts), meta_st))
    story.append(Spacer(1, 6))
    for title, items in sections(doc):
        story.append(Paragraph(_esc(title if modern else title.upper()), head_st))
        if modern:
            story.append(
                HRFlowable(width="100%", thickness=0.6, color=colors.Color(0.84, 0.75, 1), spaceAfter=4)
            )
        for it in items:
            if it.get("title"):
                story.append(Paragraph(_esc(it["title"]), title_st))
            if it.get("meta"):
                story.append(Paragraph(_esc(it["meta"]), meta_st))
            if it.get("text"):
                story.append(Paragraph(_esc(it["text"]), base))
            if it.get("bullets"):
                story.append(
                    ListFlowable(
                        [ListItem(Paragraph(_esc(b), base), leftIndent=12) for b in it["bullets"]],
                        bulletType="bullet",
                        start="•",
                        leftIndent=12,
                        bulletFontName=regular,
                    )
                )
            if it.get("url"):
                story.append(
                    Paragraph(
                        f'<link href="{_esc(it["url"])}" color="blue">{_esc(it["url"])}</link>', meta_st
                    )
                )
    pdf.build(story)
    return buf.getvalue()


def render_letter_pdf(body: str) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    regular, _ = _fonts()
    st = ParagraphStyle("b", fontName=regular, fontSize=11, leading=16)
    buf = io.BytesIO()
    pdf = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=2.5 * cm, rightMargin=2.5 * cm, topMargin=2.5 * cm, bottomMargin=2.5 * cm
    )
    story: list[Any] = []
    for para in body.split("\n\n"):
        story += [Paragraph(_esc(para).replace("\n", "<br/>"), st), Spacer(1, 8)]
    pdf.build(story)
    return buf.getvalue()


def render_letter_docx(body: str) -> bytes:
    from docx import Document

    d = Document()
    for para in body.split("\n\n"):
        d.add_paragraph(para)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------- persistence


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-")[:40] or "cv"


def export_resume(
    db: Session, tr: TailoredResume, fmt: Literal["pdf", "docx"], template: Template
) -> ExportFile:
    if template not in TEMPLATES:
        raise ValidationFailed("Unknown template.")
    doc = resolved_document(db, tr)
    data = render_pdf(doc, template) if fmt == "pdf" else render_docx(doc, template)
    v = db.get(JobVacancy, tr.vacancy_id)
    name = f"CV-{_slug(doc['contact'].get('full_name') or 'candidate')}-{_slug(v.company_name or v.title if v else 'role')}-v{tr.id}-{datetime.now():%Y%m%d}.{fmt}"
    ref, _ = get_filestore().put(data, namespace="exports", suffix=f".{fmt}")
    ef = ExportFile(
        tailored_resume_id=tr.id,
        profile_version_id=tr.profile_version_id,
        vacancy_id=tr.vacancy_id,
        format=fmt,
        template=template,
        filename=name,
        blob_ref=ref,
        byte_size=len(data),
    )
    db.add(ef)
    db.flush()
    return ef


def export_letter(db: Session, cl: CoverLetter, fmt: Literal["pdf", "docx"]) -> ExportFile:
    data = render_letter_pdf(cl.body) if fmt == "pdf" else render_letter_docx(cl.body)
    ref, _ = get_filestore().put(data, namespace="exports", suffix=f".{fmt}")
    ef = ExportFile(
        cover_letter_id=cl.id,
        profile_version_id=cl.profile_version_id,
        vacancy_id=cl.vacancy_id,
        format=fmt,
        template="letter",
        filename=f"Cover-letter-v{cl.id}-{datetime.now():%Y%m%d}.{fmt}",
        blob_ref=ref,
        byte_size=len(data),
    )
    db.add(ef)
    db.flush()
    return ef
