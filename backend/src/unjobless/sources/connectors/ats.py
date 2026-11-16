"""Documented public ATS job-board connectors.

These read *public job-board APIs* that the ATS vendors document for exactly this purpose
(listing an employer's published postings). They do not cover every job on these platforms —
only the boards (company slugs) the owner configures.

- Greenhouse Job Board API: GET https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true
  https://developers.greenhouse.io/job-board.html
- Lever Postings API: GET https://api.lever.co/v0/postings/{site}?mode=json
  https://github.com/lever/postings-api
- Ashby Job Posting API: GET https://api.ashbyhq.com/posting-api/job-board/{board}?includeCompensation=true
  https://developers.ashbyhq.com/docs/public-job-posting-api
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from unjobless.core.errors import BlockedURL, FetchFailed
from unjobless.domain.enums import CollectionMethod, SourceCategory
from unjobless.intelligence.text import html_to_text
from unjobless.sources.contract import (
    CollectContext,
    CollectedItem,
    Connector,
    ConnectorInfo,
    HealthResult,
    SourceRateLimited,
    SourceUnavailable,
)
from unjobless.sources.registry import register

SLUG = r"^[A-Za-z0-9][A-Za-z0-9_\-.]{0,99}$"


class BoardConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    board: str = Field(pattern=SLUG, description="Board token / site name shown in the public job board URL.")
    company_name: str | None = Field(
        default=None, max_length=200, description="Display name if the API omits it."
    )


def _get_json(ctx: CollectContext, url: str) -> Any:
    try:
        res = ctx.fetcher.get(url, accept="application/json", content_types=("application/json",))
    except BlockedURL as e:
        raise SourceUnavailable(f"Blocked: {e.message}") from e
    except FetchFailed as e:
        raise RuntimeError(e.message) from e
    if res.status_code == 429:
        ra = res.headers.get("retry-after")
        raise SourceRateLimited("ATS API rate limit", retry_after=float(ra) if ra and ra.isdigit() else None)
    if res.status_code in (401, 403):
        raise SourceUnavailable(f"Board is not public (HTTP {res.status_code}).")
    if res.status_code == 404:
        raise SourceUnavailable("Board not found. Check the board token.")
    if res.status_code >= 400:
        raise RuntimeError(f"HTTP {res.status_code}")
    return json.loads(res.body)


def _iso(v: Any) -> datetime | None:
    if v is None or v == "":
        return None
    try:
        if isinstance(v, int | float):
            return datetime.fromtimestamp(v / 1000 if v > 1e11 else v, tz=UTC)
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None


def _item(
    native_id: str,
    url: str | None,
    apply_url: str | None,
    title: str,
    text: str,
    structured: dict[str, Any],
    published: datetime | None,
    lang: str | None,
    raw: dict[str, Any],
) -> CollectedItem:
    return CollectedItem(
        native_id=native_id,
        url=url,
        application_url=apply_url,
        content_type="application/json",
        raw_text=json.dumps(raw, ensure_ascii=False, sort_keys=True, default=str),
        extracted_text=text,
        title=title,
        published_at=published,
        language=lang,
        structured=[structured],
        metadata={"connector_payload": "ats_api"},
    )


def _common(**kw: Any) -> dict[str, Any]:
    return {"@type": "UnjoblessJob", "provenance": "documented_ats_api", **kw}


@register
class GreenhouseConnector(Connector):
    info = ConnectorInfo(
        type="greenhouse_board",
        name="Greenhouse public job board",
        category=SourceCategory.ATS_BOARD,
        collection_method=CollectionMethod.ATS_PUBLIC_API,
        description="Published jobs from one employer's public Greenhouse job board (documented Job Board API).",
        documentation_url="https://developers.greenhouse.io/job-board.html",
        terms_url="https://www.greenhouse.com/legal",
        config_model=BoardConfig,
        default_schedule_seconds=3600,
        default_rate_limit_per_minute=30,
        terms_review="Public Job Board API intended for displaying an employer's published jobs. Confirm the employer's board is public.",
    )

    def collect(self, ctx: CollectContext) -> Iterator[CollectedItem]:
        cfg: Any = ctx.config
        data = _get_json(ctx, f"https://boards-api.greenhouse.io/v1/boards/{cfg.board}/jobs?content=true")
        for j in data.get("jobs", []):
            ctx.check_cancel()
            loc = (j.get("location") or {}).get("name")
            if not location_ok(cfg, [loc]):
                continue
            text = html_to_text(str(j.get("content") or ""))
            structured = _common(
                title=j.get("title"),
                company=j.get("company_name") or cfg.company_name,
                locations=[loc] if loc else [],
                department=", ".join(d.get("name", "") for d in j.get("departments") or [] if d.get("name"))
                or None,
                application_url=j.get("absolute_url"),
                posting_url=j.get("absolute_url"),
                published_at=j.get("first_published") or j.get("updated_at"),
                deadline=j.get("application_deadline"),
                description_text=text,
                language=j.get("language"),
            )
            yield _item(
                str(j["id"]),
                j.get("absolute_url"),
                j.get("absolute_url"),
                j.get("title") or "",
                text,
                structured,
                _iso(j.get("first_published") or j.get("updated_at")),
                j.get("language"),
                j,
            )
        ctx.listing_complete = True

    def health_check(self, ctx: CollectContext) -> HealthResult:
        try:
            data = _get_json(ctx, f"https://boards-api.greenhouse.io/v1/boards/{ctx.config.board}/jobs")  # type: ignore[attr-defined]
            return HealthResult(ok=True, message=f"{len(data.get('jobs', []))} published jobs")
        except Exception as e:
            return HealthResult(ok=False, message=str(e)[:200])


LEVER_WORKPLACE = {"remote": "REMOTE", "hybrid": "HYBRID", "on-site": "ONSITE", "onsite": "ONSITE"}
LEVER_INTERVAL = {
    "per-year-salary": "YEAR",
    "per-month-salary": "MONTH",
    "per-hour-wage": "HOUR",
    "per-week-salary": "WEEK",
    "per-day-wage": "DAY",
    "one-time": "PROJECT",
}


@register
class LeverConnector(Connector):
    info = ConnectorInfo(
        type="lever_postings",
        name="Lever public postings",
        category=SourceCategory.ATS_BOARD,
        collection_method=CollectionMethod.ATS_PUBLIC_API,
        description="Published postings from one employer's public Lever site (documented Postings API).",
        documentation_url="https://github.com/lever/postings-api",
        terms_url="https://www.lever.co/terms-of-service/",
        config_model=BoardConfig,
        default_schedule_seconds=3600,
        default_rate_limit_per_minute=30,
        terms_review="Public Postings API for listing an employer's published jobs.",
    )

    def collect(self, ctx: CollectContext) -> Iterator[CollectedItem]:
        cfg: Any = ctx.config
        data = _get_json(ctx, f"https://api.lever.co/v0/postings/{cfg.board}?mode=json")
        for j in data if isinstance(data, list) else []:
            ctx.check_cancel()
            parts = [
                j.get("openingPlain") or "",
                j.get("descriptionBodyPlain") or j.get("descriptionPlain") or "",
            ]
            for lst in j.get("lists") or []:
                parts.append(f"{lst.get('text', '')}\n" + html_to_text(lst.get("content", "")))
            parts.append(j.get("additionalPlain") or "")
            text = "\n\n".join(p.strip() for p in parts if p and p.strip())
            cats = j.get("categories") or {}
            sal = j.get("salaryRange") or {}
            locs = list(dict.fromkeys([cats.get("location")] + list(cats.get("allLocations") or [])))
            if not location_ok(cfg, [*locs, j.get("country"), j.get("workplaceType")]):
                continue
            structured = _common(
                title=j.get("text"),
                company=cfg.company_name,
                locations=[x for x in locs if x],
                department=cats.get("department") or cats.get("team"),
                commitment=cats.get("commitment"),
                work_arrangement=LEVER_WORKPLACE.get(str(j.get("workplaceType") or "").lower()),
                application_url=j.get("applyUrl"),
                posting_url=j.get("hostedUrl"),
                published_at=(lambda d: d.isoformat() if d else None)(_iso(j.get("createdAt"))),
                salary={
                    "min": sal.get("min"),
                    "max": sal.get("max"),
                    "currency": sal.get("currency"),
                    "period": LEVER_INTERVAL.get(sal.get("interval", "")),
                }
                if sal
                else None,
                country=j.get("country"),
                description_text=text,
            )
            yield _item(
                str(j["id"]),
                j.get("hostedUrl"),
                j.get("applyUrl"),
                j.get("text") or "",
                text,
                structured,
                _iso(j.get("createdAt")),
                None,
                j,
            )
        ctx.listing_complete = True


ASHBY_EMPLOYMENT = {
    "FullTime": "FULL_TIME",
    "PartTime": "PART_TIME",
    "Intern": "INTERNSHIP",
    "Contract": "CONTRACT",
    "Temporary": "TEMPORARY",
}
ASHBY_INTERVAL = {"1 YEAR": "YEAR", "1 MONTH": "MONTH", "1 HOUR": "HOUR", "1 WEEK": "WEEK", "1 DAY": "DAY"}


@register
class AshbyConnector(Connector):
    info = ConnectorInfo(
        type="ashby_board",
        name="Ashby public job board",
        category=SourceCategory.ATS_BOARD,
        collection_method=CollectionMethod.ATS_PUBLIC_API,
        description="Published jobs from one employer's public Ashby job board (documented Job Posting API).",
        documentation_url="https://developers.ashbyhq.com/docs/public-job-posting-api",
        terms_url="https://www.ashbyhq.com/terms",
        config_model=BoardConfig,
        default_schedule_seconds=3600,
        default_rate_limit_per_minute=30,
        terms_review="Public posting API intended for embedding an employer's job board.",
    )

    def collect(self, ctx: CollectContext) -> Iterator[CollectedItem]:
        cfg: Any = ctx.config
        data = _get_json(
            ctx, f"https://api.ashbyhq.com/posting-api/job-board/{cfg.board}?includeCompensation=true"
        )
        for j in data.get("jobs", []):
            ctx.check_cancel()
            if j.get("isListed") is False:
                continue
            text = j.get("descriptionPlain") or html_to_text(j.get("descriptionHtml") or "")
            salary = None
            comp = j.get("compensation") or {}
            for tier in comp.get("compensationTiers") or []:
                for c in tier.get("components") or []:
                    if c.get("compensationType") == "Salary" and (c.get("minValue") or c.get("maxValue")):
                        salary = {
                            "min": c.get("minValue"),
                            "max": c.get("maxValue"),
                            "currency": c.get("currencyCode"),
                            "period": ASHBY_INTERVAL.get(c.get("interval") or ""),
                        }
                        break
                if salary:
                    break
            locs = [j.get("location")] + [s.get("location") for s in j.get("secondaryLocations") or []]
            if not location_ok(cfg, [*locs, "remote" if j.get("isRemote") else None]):
                continue
            if not location_ok(cfg, [*locs, "remote" if j.get("isRemote") else None]):
                continue
            wp = str(j.get("workplaceType") or "").upper()
            structured = _common(
                title=j.get("title"),
                company=cfg.company_name,
                locations=[x for x in locs if x],
                department=j.get("department") or j.get("team"),
                employment_type=ASHBY_EMPLOYMENT.get(j.get("employmentType") or ""),
                work_arrangement={"REMOTE": "REMOTE", "HYBRID": "HYBRID", "ONSITE": "ONSITE"}.get(wp)
                or ("REMOTE" if j.get("isRemote") else None),
                application_url=j.get("applyUrl"),
                posting_url=j.get("jobUrl"),
                published_at=j.get("publishedAt"),
                salary=salary,
                compensation_summary=comp.get("compensationTierSummary")
                if j.get("shouldDisplayCompensationOnJobPostings")
                else None,
                description_text=text,
            )
            yield _item(
                str(j["id"]),
                j.get("jobUrl"),
                j.get("applyUrl"),
                j.get("title") or "",
                text,
                structured,
                _iso(j.get("publishedAt")),
                None,
                j,
            )
        ctx.listing_complete = True


SR_EMPLOYMENT = {"permanent": "FULL_TIME", "full-time": "FULL_TIME", "part-time": "PART_TIME", "contract": "CONTRACT", "intern": "INTERNSHIP", "internship": "INTERNSHIP", "temporary": "TEMPORARY"}
SR_SENIORITY = {"internship": "INTERN", "entry_level": "ENTRY", "associate": "JUNIOR", "mid_senior_level": "MID", "director": "MANAGER", "executive": "EXECUTIVE"}


@register
class SmartRecruitersConnector(Connector):
    info = ConnectorInfo(
        type="smartrecruiters",
        name="SmartRecruiters public postings",
        category=SourceCategory.ATS_BOARD,
        collection_method=CollectionMethod.ATS_PUBLIC_API,
        description="Published jobs of one employer via the documented SmartRecruiters Posting API.",
        documentation_url="https://developers.smartrecruiters.com/docs/posting-api",
        terms_url="https://www.smartrecruiters.com/legal/",
        config_model=BoardConfig,
        default_schedule_seconds=3600,
        default_rate_limit_per_minute=30,
        supports_pagination=True,
        supports_incremental=True,
        terms_review="Public Posting API intended for publishing an employer's open jobs on other sites.",
    )

    def collect(self, ctx: CollectContext) -> Iterator[CollectedItem]:
        cfg: Any = ctx.config
        base = f"https://api.smartrecruiters.com/v1/companies/{cfg.board}/postings"
        known: dict[str, str] = dict((ctx.cursor or {}).get("released", {}))
        seen: dict[str, str] = {}
        offset = 0
        while True:
            ctx.check_cancel()
            page = _get_json(ctx, f"{base}?limit=100&offset={offset}")
            content = page.get("content") or []
            for j in content:
                loc = j.get("location") or {}
                loc_text = ", ".join(x for x in [loc.get("city"), loc.get("region"), (loc.get("country") or "").upper()] if x)
                remote = bool(loc.get("remote"))
                if not location_ok(cfg, [loc_text, "indonesia" if (loc.get("country") or "").lower() == "id" else None, "remote" if remote else None]):
                    continue
                pid = str(j["id"])
                released = str(j.get("releasedDate") or "")
                seen[pid] = released
                if known.get(pid) == released:
                    # Unchanged posting: re-emit a light item so the raw store records it as seen (no detail call).
                    yield CollectedItem(native_id=pid, url=None, content_type="application/json", raw_text=json.dumps(j, sort_keys=True, default=str), title=j.get("name"), metadata={"listing_only": True})
                    continue
                detail = _get_json(ctx, f"{base}/{pid}")
                sections = (detail.get("jobAd") or {}).get("sections") or {}
                text = "\n\n".join(
                    f"{(sections.get(k) or {}).get('title') or k}\n{html_to_text((sections.get(k) or {}).get('text') or '')}"
                    for k in ("jobDescription", "qualifications", "additionalInformation", "companyDescription")
                    if (sections.get(k) or {}).get("text")
                )
                emp = ((j.get("typeOfEmployment") or {}).get("label") or "").lower()
                structured = _common(
                    title=j.get("name"),
                    company=(j.get("company") or {}).get("name") or cfg.company_name,
                    locations=[loc_text + (" (remote)" if remote else "")] if loc_text else [],
                    department=(j.get("function") or {}).get("label"),
                    employment_type=next((v for k, v in SR_EMPLOYMENT.items() if k in emp), None),
                    work_arrangement="REMOTE" if remote else None,
                    application_url=detail.get("applyUrl") or detail.get("postingUrl"),
                    posting_url=detail.get("postingUrl"),
                    published_at=j.get("releasedDate"),
                    industry=(j.get("industry") or {}).get("label"),
                    description_text=text,
                )
                yield _item(pid, detail.get("postingUrl"), detail.get("applyUrl"), j.get("name") or "", text, structured, _iso(j.get("releasedDate")), (j.get("language") or {}).get("code"), detail)
            offset += len(content)
            if not content or offset >= int(page.get("totalFound") or 0) or offset >= 1000:
                break
        ctx.listing_complete = offset < 1000
        ctx.set_cursor({"released": seen})
