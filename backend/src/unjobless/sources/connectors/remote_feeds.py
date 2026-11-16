"""Public remote-job feeds, filtered to jobs open to applicants in Indonesia.

Each feed is used per its published API terms: attribution + a link back to the original listing
(the original URL is kept as the source/application link and the feed is named as the source), and
conservative polling (Remotive asks for at most 4 requests/day → 6-hour minimum schedule).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from unjobless.domain.enums import CollectionMethod, SourceCategory
from unjobless.intelligence.text import html_to_text
from unjobless.sources.connectors.ats import _get_json, _iso
from unjobless.sources.contract import CollectContext, CollectedItem, Connector, ConnectorInfo
from unjobless.sources.registry import register

OPEN_TO_INDONESIA = ["worldwide", "anywhere", "global", "indonesia", "asia", "apac", "southeast asia", "south east asia", "sea", "emea/apac", "remote"]


class RemoteFeedConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    allowed_regions: list[str] = Field(
        default_factory=lambda: list(OPEN_TO_INDONESIA), max_length=40,
        description="Keep jobs with no location restriction or whose restriction mentions one of these.",
    )
    keywords: list[str] = Field(default_factory=list, max_length=30, description="Optional: only keep jobs whose title/category contains one of these (e.g. intern, data).")
    max_items: int = Field(default=300, ge=10, le=2000)


def region_ok(cfg: Any, restrictions: list[str]) -> bool:
    restr = [r.strip().lower() for r in restrictions if r and r.strip()]
    if not restr:
        return True
    allowed = [a.lower() for a in cfg.allowed_regions]
    return any(a == r or a in r for r in restr for a in allowed)


def keyword_ok(cfg: Any, *texts: str | None) -> bool:
    kws = [k.lower() for k in cfg.keywords if k]
    if not kws:
        return True
    blob = " ".join(t for t in texts if t).lower()
    return any(k in blob for k in kws)


def _structured(provenance: str, **kw: Any) -> dict[str, Any]:
    return {"@type": "UnjoblessJob", "provenance": provenance, "work_arrangement": "REMOTE", **kw}


def _emit(native_id: str, url: str | None, apply_url: str | None, title: str, text: str, structured: dict[str, Any], published: datetime | None, raw: Any, feed: str) -> CollectedItem:
    return CollectedItem(
        native_id=native_id[:300], url=url, application_url=apply_url, content_type="application/json",
        raw_text=json.dumps(raw, ensure_ascii=False, sort_keys=True, default=str), extracted_text=text, title=title,
        published_at=published, structured=[structured], metadata={"feed": feed, "attribution": f"via {feed}"},
    )


@register
class HimalayasConnector(Connector):
    info = ConnectorInfo(
        type="himalayas_feed",
        name="Himalayas remote jobs",
        category=SourceCategory.JOB_API,
        collection_method=CollectionMethod.AGGREGATOR_API,
        description="Public Himalayas remote-jobs API, filtered to jobs open to Indonesia/Asia/worldwide.",
        documentation_url="https://himalayas.app/api",
        terms_url="https://himalayas.app/terms",
        config_model=RemoteFeedConfig,
        default_schedule_seconds=3 * 3600,
        default_rate_limit_per_minute=20,
        supports_pagination=True,
        attribution="Link back to the Himalayas listing and name Himalayas as the source.",
        terms_review="Public jobs API; attribute Himalayas and link back.",
    )

    def collect(self, ctx: CollectContext) -> Iterator[CollectedItem]:
        cfg: Any = ctx.config
        cursor: str | None = None
        kept = scanned = 0
        while kept < cfg.max_items and scanned < 5000:
            ctx.check_cancel()
            data = _get_json(ctx, "https://himalayas.app/jobs/api?limit=100" + (f"&cursor={cursor}" if cursor else ""))
            jobs = data.get("jobs") or []
            for j in jobs:
                scanned += 1
                if not region_ok(cfg, j.get("locationRestrictions") or []) or not keyword_ok(cfg, j.get("title"), " ".join(j.get("categories") or [])):
                    continue
                kept += 1
                text = html_to_text(j.get("description") or "") or j.get("excerpt") or ""
                pub = datetime.fromtimestamp(int(j["pubDate"]), tz=UTC) if j.get("pubDate") else None
                exp = datetime.fromtimestamp(int(j["expiryDate"]), tz=UTC).date().isoformat() if j.get("expiryDate") else None
                sal = {"min": j.get("minSalary"), "max": j.get("maxSalary"), "currency": j.get("currency"), "period": {"annual": "YEAR", "monthly": "MONTH", "hourly": "HOUR"}.get(str(j.get("salaryPeriod") or ""))} if j.get("minSalary") or j.get("maxSalary") else None
                regions = j.get("locationRestrictions") or ["Worldwide"]
                structured = _structured(
                    "himalayas_api", title=j.get("title"), company=j.get("companyName"), locations=[f"Remote ({', '.join(regions)})"],
                    employment_type={"Full Time": "FULL_TIME", "Part Time": "PART_TIME", "Contractor": "CONTRACT", "Intern": "INTERNSHIP", "Internship": "INTERNSHIP", "Temporary": "TEMPORARY"}.get(j.get("employmentType") or ""),
                    application_url=j.get("applicationLink"), posting_url=j.get("guid"), published_at=pub.isoformat() if pub else None,
                    salary=sal, remote_eligible_countries=[r for r in regions if len(r) > 2], description_text=text,
                )
                # Himalayas expiry is the listing's own expiry, not an employer deadline: kept as metadata only.
                item = _emit(j.get("guid") or j.get("applicationLink") or j["title"], j.get("guid"), j.get("applicationLink"), j.get("title") or "", text, structured, pub, j, "Himalayas")
                item.metadata["listing_expiry"] = exp
                yield item
                if kept >= cfg.max_items:
                    break
            cursor = data.get("nextCursor")
            if not cursor or not jobs:
                break


@register
class RemotiveConnector(Connector):
    info = ConnectorInfo(
        type="remotive_feed",
        name="Remotive remote jobs",
        category=SourceCategory.JOB_API,
        collection_method=CollectionMethod.AGGREGATOR_API,
        description="Public Remotive API (jobs delayed 24h), filtered to jobs open to Indonesia/Asia/worldwide. Max 4 calls/day.",
        documentation_url="https://remotive.com/api-documentation",
        terms_url="https://remotive.com/api-documentation",
        config_model=RemoteFeedConfig,
        default_schedule_seconds=6 * 3600,
        default_rate_limit_per_minute=1,
        attribution="Link back to the Remotive URL and mention Remotive as the source.",
        terms_review="Free API for sharing jobs with attribution + link back; at most 4 requests per day; do not resubmit to other job sites.",
    )

    def collect(self, ctx: CollectContext) -> Iterator[CollectedItem]:
        cfg: Any = ctx.config
        data = _get_json(ctx, "https://remotive.com/api/remote-jobs")
        kept = 0
        for j in data.get("jobs") or []:
            loc = j.get("candidate_required_location") or ""
            if not region_ok(cfg, [x for x in loc.replace(";", ",").split(",")]) or not keyword_ok(cfg, j.get("title"), j.get("category")):
                continue
            text = html_to_text(j.get("description") or "")
            structured = _structured(
                "remotive_api", title=j.get("title"), company=j.get("company_name"), locations=[f"Remote ({loc or 'Worldwide'})"],
                employment_type={"full_time": "FULL_TIME", "part_time": "PART_TIME", "contract": "CONTRACT", "internship": "INTERNSHIP", "freelance": "FREELANCE"}.get(j.get("job_type") or ""),
                application_url=j.get("url"), posting_url=j.get("url"), published_at=j.get("publication_date"), description_text=text,
            )
            yield _emit(str(j["id"]), j.get("url"), j.get("url"), j.get("title") or "", text, structured, _iso(j.get("publication_date")), j, "Remotive")
            kept += 1
            if kept >= cfg.max_items:
                break
        ctx.listing_complete = True


@register
class RemoteOKConnector(Connector):
    info = ConnectorInfo(
        type="remoteok_feed",
        name="Remote OK remote jobs",
        category=SourceCategory.JOB_API,
        collection_method=CollectionMethod.AGGREGATOR_API,
        description="Public Remote OK API, filtered to jobs open to Indonesia/Asia/worldwide.",
        documentation_url="https://remoteok.com/api",
        terms_url="https://remoteok.com/api",
        config_model=RemoteFeedConfig,
        default_schedule_seconds=3 * 3600,
        default_rate_limit_per_minute=2,
        attribution="Link back to the Remote OK URL and mention Remote OK as the source (do not use their logo).",
        terms_review="Public API; requires attribution and a followed link back.",
    )

    def collect(self, ctx: CollectContext) -> Iterator[CollectedItem]:
        cfg: Any = ctx.config
        data = _get_json(ctx, "https://remoteok.com/api")
        kept = 0
        for j in data[1:] if isinstance(data, list) else []:
            loc = j.get("location") or ""
            if not region_ok(cfg, [x for x in loc.replace(";", ",").split(",")]) or not keyword_ok(cfg, j.get("position"), " ".join(j.get("tags") or [])):
                continue
            text = html_to_text(j.get("description") or "")
            smin, smax = j.get("salary_min") or None, j.get("salary_max") or None
            structured = _structured(
                "remoteok_api", title=j.get("position"), company=j.get("company"), locations=[f"Remote ({loc or 'Worldwide'})"],
                application_url=j.get("apply_url") or j.get("url"), posting_url=j.get("url"), published_at=j.get("date"),
                salary={"min": smin, "max": smax, "currency": "USD", "period": "YEAR"} if smin or smax else None, description_text=text,
            )
            yield _emit(str(j.get("id")), j.get("url"), j.get("apply_url") or j.get("url"), j.get("position") or "", text, structured, _iso(j.get("date")), j, "Remote OK")
            kept += 1
            if kept >= cfg.max_items:
                break
        ctx.listing_complete = True
