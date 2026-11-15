"""Text utilities: HTML → readable text, language guess, normalisation."""

from __future__ import annotations

import html
import re
import unicodedata

from selectolax.lexbor import LexborHTMLParser as HTMLParser

_WS = re.compile(r"[ \t ]+")
_NL = re.compile(r"\n{3,}")
BLOCK_TAGS = {"p", "div", "li", "br", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section", "article", "ul", "ol", "table"}

ID_WORDS = {
    "dan", "yang", "untuk", "dengan", "di", "ke", "dari", "kami", "anda", "atau", "akan", "ini", "itu", "adalah",
    "pada", "dalam", "lowongan", "magang", "kerja", "pengalaman", "minimal", "lulusan", "kirim", "perusahaan", "bisa",
    "tidak", "ada", "juga", "sebagai", "bidang", "tahun", "bulan", "gaji", "syarat", "persyaratan", "kualifikasi",
}
EN_WORDS = {
    "the", "and", "for", "with", "you", "our", "are", "will", "this", "that", "from", "have", "your", "experience",
    "team", "work", "role", "we", "of", "to", "in", "is", "a", "an", "be", "as", "requirements", "about", "job",
}


def html_to_text(raw_html: str) -> str:
    """Readable text from HTML (scripts/styles removed). Keeps paragraph breaks and list items."""
    if not raw_html:
        return ""
    if "<" not in raw_html and "&lt;" in raw_html:
        raw_html = html.unescape(raw_html)  # entity-escaped HTML (e.g. Greenhouse `content`)
    if "<" not in raw_html:
        return clean_text(html.unescape(raw_html))
    tree = HTMLParser(raw_html)
    for sel in ("script", "style", "noscript", "template", "svg", "iframe"):
        for n in tree.css(sel):
            n.decompose()
    out: list[str] = []
    root = tree.body or tree.root
    if root is None:
        return ""
    for node in root.traverse(include_text=True):
        if node.tag == "-text":
            out.append(node.text(deep=False))
        elif node.tag in BLOCK_TAGS:
            out.append("\n- " if node.tag == "li" else "\n")
    return clean_text(html.unescape("".join(out)))


def clean_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    lines = [_WS.sub(" ", ln).strip() for ln in text.split("\n")]
    text = "\n".join(lines)
    return _NL.sub("\n\n", text).strip()


def guess_language(text: str) -> str | None:
    words = re.findall(r"[a-zA-Z]+", text.lower()[:20000])
    if len(words) < 5:
        return None
    id_score = sum(1 for w in words if w in ID_WORDS)
    en_score = sum(1 for w in words if w in EN_WORDS)
    if id_score == en_score == 0:
        return None
    return "id" if id_score > en_score * 0.8 else "en"


def normalize_key(text: str | None) -> str:
    """Lowercase, accent-free, punctuation-free key for matching."""
    if not text:
        return ""
    t = unicodedata.normalize("NFKD", text)
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    t = re.sub(r"[^a-z0-9+#.]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def find_span(haystack: str, needle: str) -> tuple[int, int] | None:
    """Locate an evidence excerpt in source text (whitespace/case tolerant)."""
    if not needle or not haystack:
        return None
    i = haystack.find(needle)
    if i >= 0:
        return i, i + len(needle)
    pattern = r"\s+".join(re.escape(p) for p in needle.split())
    if not pattern:
        return None
    m = re.search(pattern, haystack, re.IGNORECASE)
    return (m.start(), m.end()) if m else None
