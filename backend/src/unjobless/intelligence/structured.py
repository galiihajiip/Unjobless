"""Structured data in HTML: JSON-LD schema.org JobPosting, canonical link, meta tags."""

from __future__ import annotations

import json
from typing import Any

from selectolax.parser import HTMLParser

from unjobless.intelligence.text import html_to_text


def extract_jsonld(html: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    tree = HTMLParser(html)
    for node in tree.css('script[type="application/ld+json"]'):
        raw = (node.text() or "").strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            d = stack.pop()
            if isinstance(d, dict):
                if "@graph" in d and isinstance(d["@graph"], list):
                    stack.extend(d["@graph"])
                out.append(d)
            elif isinstance(d, list):
                stack.extend(d)
    return out


def _types(d: dict[str, Any]) -> list[str]:
    t = d.get("@type")
    return [str(x) for x in (t if isinstance(t, list) else [t])]


def _name(v: Any) -> str | None:
    if isinstance(v, dict):
        return v.get("name") or v.get("@id")
    if isinstance(v, list):
        return _name(v[0]) if v else None
    return str(v) if v else None


EMPLOYMENT_MAP = {
    "FULL_TIME": "FULL_TIME", "PART_TIME": "PART_TIME", "CONTRACTOR": "CONTRACT", "TEMPORARY": "TEMPORARY",
    "INTERN": "INTERNSHIP", "VOLUNTEER": "VOLUNTEER", "PER_DIEM": "TEMPORARY", "OTHER": None,
}
UNIT_MAP = {"HOUR": "HOUR", "DAY": "DAY", "WEEK": "WEEK", "MONTH": "MONTH", "YEAR": "YEAR"}


def jobposting_to_structured(d: dict[str, Any]) -> dict[str, Any]:
    """Map schema.org JobPosting → Unjobless structured dict. Only explicit values; no inference."""
    locs: list[str] = []
    jl = d.get("jobLocation")
    for loc in jl if isinstance(jl, list) else ([jl] if jl else []):
        if isinstance(loc, dict):
            addr = loc.get("address") or {}
            if isinstance(addr, dict):
                parts = [addr.get("addressLocality"), addr.get("addressRegion"), _name(addr.get("addressCountry"))]
                s = ", ".join(p for p in parts if p)
                if s:
                    locs.append(s)
            elif isinstance(addr, str):
                locs.append(addr)
    et = d.get("employmentType")
    et_list = et if isinstance(et, list) else [et] if et else []
    employment = next((EMPLOYMENT_MAP.get(str(x).upper().replace(" ", "_")) for x in et_list if EMPLOYMENT_MAP.get(str(x).upper().replace(" ", "_"))), None)
    salary = None
    bs = d.get("baseSalary")
    if isinstance(bs, dict):
        val = bs.get("value") or {}
        if isinstance(val, dict):
            salary = {
                "min": val.get("minValue") if val.get("minValue") is not None else val.get("value"),
                "max": val.get("maxValue") if val.get("maxValue") is not None else val.get("value"),
                "currency": bs.get("currency"),
                "period": UNIT_MAP.get(str(val.get("unitText") or "").upper()),
            }
        elif isinstance(val, int | float):
            salary = {"min": val, "max": val, "currency": bs.get("currency"), "period": None}
    remote = str(d.get("jobLocationType") or "").upper() == "TELECOMMUTE"
    return {
        "@type": "UnjoblessJob",
        "provenance": "schema_org_jobposting",
        "title": d.get("title"),
        "company": _name(d.get("hiringOrganization")),
        "locations": locs,
        "employment_type": employment,
        "work_arrangement": "REMOTE" if remote else None,
        "remote_eligible_countries": [_name(x) for x in (d.get("applicantLocationRequirements") or [])] if isinstance(d.get("applicantLocationRequirements"), list) else [],
        "application_url": d.get("url") if isinstance(d.get("url"), str) else None,
        "posting_url": d.get("url") if isinstance(d.get("url"), str) else None,
        "published_at": d.get("datePosted"),
        "deadline": d.get("validThrough"),
        "salary": salary,
        "department": None,
        "industry": _name(d.get("industry")),
        "openings_count": d.get("totalJobOpenings"),
        "description_text": html_to_text(str(d.get("description") or "")),
    }


def find_jobpostings(html: str) -> list[dict[str, Any]]:
    return [jobposting_to_structured(d) for d in extract_jsonld(html) if "JobPosting" in _types(d)]


def page_meta(html: str) -> dict[str, Any]:
    tree = HTMLParser(html)
    canon = tree.css_first('link[rel="canonical"]')
    title = tree.css_first("title")
    meta: dict[str, Any] = {
        "canonical": canon.attributes.get("href") if canon else None,
        "title": (title.text() or "").strip() if title else None,
    }
    for prop in ("og:title", "og:description", "og:site_name", "article:published_time", "og:image"):
        n = tree.css_first(f'meta[property="{prop}"]')
        if n and n.attributes.get("content"):
            meta[prop] = n.attributes["content"]
    desc = tree.css_first('meta[name="description"]')
    if desc and desc.attributes.get("content"):
        meta["description"] = desc.attributes["content"]
    robots = tree.css_first('meta[name="robots"]')
    if robots and robots.attributes.get("content"):
        meta["robots"] = robots.attributes["content"].lower()
    return meta


def extract_main_text(html: str, selector: str | None = None) -> str:
    if selector:
        tree = HTMLParser(html)
        node = tree.css_first(selector)
        if node is not None:
            return html_to_text(node.html or "")
    try:
        import trafilatura

        text = trafilatura.extract(html, include_comments=False, include_tables=True, favor_recall=True)
        if text and len(text) > 200:
            return text.strip()
    except Exception:  # noqa: S110 - fall back to plain conversion
        pass
    return html_to_text(html)


ACCESS_WALL_MARKERS = (
    "captcha", "are you a robot", "verify you are human", "please enable javascript and cookies",
    "sign in to continue", "log in to continue", "login to continue", "masuk untuk melanjutkan",
    "access denied", "cf-chl", "attention required",
)


def looks_like_access_wall(html: str, text: str) -> bool:
    low = (text[:3000] + " " + html[:5000]).lower()
    return len(text) < 1500 and any(m in low for m in ACCESS_WALL_MARKERS)
