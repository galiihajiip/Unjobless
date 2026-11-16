"""Jooble job-search REST API (aggregator). Requires an API key stored as the source credential.

Jooble keys are issued per country domain (e.g. id.jooble.org for Indonesia). The default quota is
100 requests/day; this connector keeps a per-day counter in its cursor and stops before the budget.
Jobs are aggregator listings → *Likely open*, never *Verified*. Links point to Jooble's job page.
Docs: https://jooble.org/api/about
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from unjobless.core.errors import BlockedURL, FetchFailed
from unjobless.domain.enums import CollectionMethod, SourceCategory
from unjobless.intelligence.text import html_to_text
from unjobless.sources.contract import (
    CollectContext,
    CollectedItem,
    Connector,
    ConnectorInfo,
    SourceRateLimited,
    SourceUnavailable,
)
from unjobless.sources.registry import register


class JoobleSearch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    keywords: str = Field(min_length=1, max_length=120)
    location: str = Field(default="", max_length=120)


class JoobleConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    country_host: Literal[
        "id.jooble.org", "jooble.org", "sg.jooble.org", "my.jooble.org", "uk.jooble.org", "au.jooble.org"
    ] = Field(
        default="id.jooble.org",
        description="The country domain your API key was issued for (Indonesia = id.jooble.org).",
    )
    searches: list[JoobleSearch] = Field(
        default_factory=lambda: [
            JoobleSearch(keywords="magang", location="Indonesia"),
            JoobleSearch(keywords="internship", location="Indonesia"),
            JoobleSearch(keywords="fresh graduate", location="Indonesia"),
            JoobleSearch(keywords="management trainee", location="Indonesia"),
            JoobleSearch(keywords="intern", location="Jakarta"),
            JoobleSearch(keywords="lulusan baru", location="Indonesia"),
        ],
        max_length=20,
    )
    pages_per_search: int = Field(default=2, ge=1, le=10)
    daily_request_budget: int = Field(
        default=90,
        ge=1,
        le=10000,
        description="Stop once this many API calls were made today (quota is 100/day by default).",
    )


@register
class JoobleConnector(Connector):
    info = ConnectorInfo(
        type="jooble_api",
        name="Jooble job search API",
        category=SourceCategory.JOB_API,
        collection_method=CollectionMethod.AGGREGATOR_API,
        description="Jooble REST API (aggregates jobs from many sites). Needs your API key for the right country (Indonesia: id.jooble.org).",
        documentation_url="https://jooble.org/api/about",
        terms_url="https://jooble.org/info/terms",
        config_model=JoobleConfig,
        auth_required=True,
        default_schedule_seconds=4 * 3600,
        default_rate_limit_per_minute=10,
        supports_pagination=True,
        terms_review="Official API with a personal key; default quota 100 requests/day. Link to Jooble's job page and name Jooble as the source.",
        attribution="Link to the Jooble job page and name Jooble as the source.",
    )

    def collect(self, ctx: CollectContext) -> Iterator[CollectedItem]:
        cfg: Any = ctx.config
        key = (ctx.get_secret() or "").strip()
        if not key:
            raise SourceUnavailable("Set your Jooble API key as this source's credential first.")
        today = datetime.now(UTC).date().isoformat()
        cur = dict(ctx.cursor or {})
        used = int(cur.get("used", 0)) if cur.get("day") == today else 0
        url = f"https://{cfg.country_host}/api/{key}"
        stopped_for_budget = False
        try:
            for search in cfg.searches:
                for page in range(1, cfg.pages_per_search + 1):
                    if used >= cfg.daily_request_budget:
                        stopped_for_budget = True
                        break
                    ctx.check_cancel()
                    used += 1
                    try:
                        res = ctx.fetcher.get(
                            url,
                            accept="application/json",
                            content_types=("application/json",),
                            json_body={
                                "keywords": search.keywords,
                                "location": search.location,
                                "page": str(page),
                            },
                        )
                    except BlockedURL as e:
                        raise SourceUnavailable(e.message) from e
                    except FetchFailed as e:
                        raise RuntimeError(e.message) from e
                    if res.status_code == 403:
                        raise SourceUnavailable(
                            f"Jooble refused the key on {cfg.country_host}. The key is probably issued for another country domain."
                        )
                    if res.status_code == 429:
                        raise SourceRateLimited("Jooble daily quota reached.", retry_after=6 * 3600)
                    if res.status_code >= 400:
                        raise RuntimeError(f"Jooble HTTP {res.status_code}")
                    import json

                    jobs = (json.loads(res.body) or {}).get("jobs") or []
                    for j in jobs:
                        native = str(
                            j.get("id")
                            or hashlib.sha256((j.get("link") or j.get("title") or "").encode()).hexdigest()[
                                :24
                            ]
                        )
                        text = html_to_text(j.get("snippet") or "")
                        structured = {
                            "@type": "UnjoblessJob",
                            "provenance": "jooble_api",
                            "title": html_to_text(j.get("title") or ""),
                            "company": j.get("company") or None,
                            "locations": [j["location"]] if j.get("location") else [],
                            "application_url": j.get("link"),
                            "posting_url": j.get("link"),
                            "published_at": j.get("updated"),
                            "description_text": "\n".join(
                                x
                                for x in [
                                    text,
                                    f"Salary: {j['salary']}" if j.get("salary") else "",
                                    f"Type: {j['type']}" if j.get("type") else "",
                                    f"Original site: {j['source']}" if j.get("source") else "",
                                ]
                                if x
                            ),
                        }
                        yield CollectedItem(
                            native_id=native,
                            url=j.get("link"),
                            application_url=j.get("link"),
                            content_type="application/json",
                            raw_text=json.dumps(j, ensure_ascii=False, sort_keys=True),
                            extracted_text=structured["description_text"],
                            title=structured["title"],
                            structured=[structured],
                            metadata={
                                "via": "jooble",
                                "original_site": j.get("source"),
                                "search": search.keywords,
                            },
                        )
                    if len(jobs) < 20:
                        break
                if stopped_for_budget:
                    break
        finally:
            ctx.set_cursor({"day": today, "used": used})
