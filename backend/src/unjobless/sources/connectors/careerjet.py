"""Careerjet job-search API v4 (aggregator). Docs: https://www.careerjet.com/partners/api/

- Auth: HTTP Basic, username = API key (stored encrypted as the source credential), empty password.
- Careerjet only accepts calls from IP addresses declared in the publisher dashboard
  ("Server IP addresses"); a 403 "Unauthorized access from IP x" means the IP must be declared.
- `user_ip` / `user_agent` are required: we send the declared server IP and our honest User-Agent.
Jobs are aggregator listings → *Likely open*.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
from collections.abc import Iterator
from typing import Any, Literal
from urllib.parse import urlencode

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

ENDPOINT = "https://search.api.careerjet.net/v4/query"
SALARY_PERIOD = {"Y": "YEAR", "M": "MONTH", "W": "WEEK", "D": "DAY", "H": "HOUR"}
CONTRACT = {"i": "INTERNSHIP", "p": "FULL_TIME", "c": "CONTRACT", "t": "TEMPORARY", "v": "VOLUNTEER"}


class CareerjetSearch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    keywords: str = Field(default="", max_length=120)
    location: str = Field(default="", max_length=120)
    contract_type: Literal["", "p", "c", "t", "i", "v"] = Field(
        default="",
        description="i = internship/training, p = permanent, c = contract, t = temporary, v = volunteering",
    )
    pages: int | None = Field(default=None, ge=1, le=10, description="Overrides pages_per_search.")


class CareerjetConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    locale_code: str = Field(default="id_ID", pattern=r"^[a-z]{2}_[A-Z]{2}$", description="Indonesia = id_ID")
    referer_url: str = Field(
        default="https://unjobless-id.vercel.app/",
        max_length=300,
        description="The website registered in your Careerjet publisher account (sent as the Referer header).",
    )
    declared_ip: str = Field(
        min_length=3,
        max_length=45,
        description="The server IP you declared in Careerjet's dashboard (sent as user_ip).",
    )
    searches: list[CareerjetSearch] = Field(
        default_factory=lambda: [
            CareerjetSearch(keywords="", contract_type="i", pages=10),
            CareerjetSearch(keywords="internship", pages=8),
            CareerjetSearch(keywords="intern", pages=4),
            CareerjetSearch(keywords="magang", pages=2),
            CareerjetSearch(keywords="fresh graduate", pages=4),
            CareerjetSearch(keywords="management trainee", pages=2),
            CareerjetSearch(keywords="entry level", pages=2),
            CareerjetSearch(keywords="junior", pages=3),
        ],
        max_length=20,
    )
    pages_per_search: int = Field(default=3, ge=1, le=10)
    page_size: int = Field(default=100, ge=1, le=100)


@register
class CareerjetConnector(Connector):
    info = ConnectorInfo(
        type="careerjet_api",
        name="Careerjet job search API",
        category=SourceCategory.JOB_API,
        collection_method=CollectionMethod.AGGREGATOR_API,
        description="Careerjet API v4 (aggregates jobs from many Indonesian sites). Needs your publisher API key and a declared server IP.",
        documentation_url="https://www.careerjet.com/partners/api/",
        terms_url="https://www.careerjet.com/partners/",
        config_model=CareerjetConfig,
        auth_required=True,
        default_schedule_seconds=2 * 3600,
        default_rate_limit_per_minute=10,
        supports_pagination=True,
        terms_review="Official publisher API with your key; requests only from your declared server IP; link to Careerjet's job URL.",
        attribution="Link to the Careerjet job URL and name Careerjet as the source.",
    )

    def collect(self, ctx: CollectContext) -> Iterator[CollectedItem]:
        cfg: Any = ctx.config
        key = (ctx.get_secret() or "").strip()
        if not key:
            raise SourceUnavailable("Set your Careerjet API key as this source's credential first.")
        ua = getattr(ctx.fetcher, "user_agent", "UnjoblessBot")
        for search in cfg.searches:
            for page in range(1, (search.pages or cfg.pages_per_search) + 1):
                ctx.check_cancel()
                params = {
                    "locale_code": cfg.locale_code,
                    "keywords": search.keywords,
                    "location": search.location,
                    "sort": "date",
                    "page": page,
                    "page_size": cfg.page_size,
                    "fragment_size": 400,
                    "user_ip": cfg.declared_ip,
                    "user_agent": ua,
                }
                if search.contract_type:
                    params["contract_type"] = search.contract_type
                try:
                    res = ctx.fetcher.get(
                        f"{ENDPOINT}?{urlencode(params)}",
                        accept="application/json",
                        content_types=("application/json",),
                        basic_auth=(key, ""),
                        extra_headers={"Referer": cfg.referer_url},
                    )
                except BlockedURL as e:
                    raise SourceUnavailable(e.message) from e
                except FetchFailed as e:
                    raise RuntimeError(e.message) from e
                body: dict[str, Any] = {}
                with contextlib.suppress(json.JSONDecodeError):
                    body = json.loads(res.body or b"{}")
                if res.status_code in (401, 403):
                    msg = str(body.get("error") or body.get("message") or f"HTTP {res.status_code}")
                    hint = (
                        " Declare this IP under 'Server IP addresses' in your Careerjet publisher account."
                        if "IP" in msg
                        else ""
                    )
                    raise SourceUnavailable(f"Careerjet refused the request: {msg}.{hint}")
                if res.status_code == 429:
                    raise SourceRateLimited("Careerjet rate limit reached.", retry_after=3600)
                if res.status_code == 400:
                    raise SourceUnavailable(
                        f"Careerjet rejected the request: {body.get('error') or body.get('message') or 'bad request'} (check locale_code)."
                    )
                if res.status_code >= 400:
                    raise RuntimeError(f"Careerjet HTTP {res.status_code}")
                if body.get("type") != "JOBS":
                    break  # LOCATIONS / no results
                jobs = body.get("jobs") or []
                for j in jobs:
                    url = j.get("url")
                    native = hashlib.sha256(
                        (url or f"{j.get('title')}|{j.get('company')}|{j.get('date')}").encode()
                    ).hexdigest()[:32]
                    text = html_to_text(j.get("description") or "")
                    sal = None
                    if j.get("salary_min") or j.get("salary_max"):
                        sal = {
                            "min": j.get("salary_min"),
                            "max": j.get("salary_max"),
                            "currency": j.get("salary_currency_code"),
                            "period": SALARY_PERIOD.get(j.get("salary_type") or ""),
                        }
                    structured = {
                        "@type": "UnjoblessJob",
                        "provenance": "careerjet_api",
                        "title": html_to_text(j.get("title") or ""),
                        "company": j.get("company") or None,
                        "locations": [
                            x.strip() for x in str(j.get("locations") or "").split(",") if x.strip()
                        ][:5],
                        "employment_type": CONTRACT.get(search.contract_type)
                        if search.contract_type
                        else None,
                        "application_url": url,
                        "posting_url": url,
                        "published_at": j.get("date"),
                        "salary": sal,
                        "description_text": "\n".join(
                            x for x in [text, f"Salary: {j['salary']}" if j.get("salary") else ""] if x
                        ),
                    }
                    yield CollectedItem(
                        native_id=native,
                        url=url,
                        application_url=url,
                        content_type="application/json",
                        raw_text=json.dumps(j, ensure_ascii=False, sort_keys=True),
                        extracted_text=structured["description_text"],
                        title=structured["title"],
                        structured=[structured],
                        metadata={"via": "careerjet", "search": search.keywords or search.contract_type},
                    )
                if page >= int(body.get("pages") or 1) or len(jobs) < cfg.page_size:
                    break
