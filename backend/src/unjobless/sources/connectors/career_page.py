"""Generic policy-aware career-page crawler for explicitly enabled, permitted domains.

- Only visits URLs on the source's own domain (or subdomains) and inside configured path prefixes.
- robots.txt is honoured and per-host rate limits/crawl-delay applied via `ctx.polite_get`.
- Discovery from sitemap, RSS/Atom feeds and listing pages (CSS selector or URL regex).
- Prefers schema.org JobPosting JSON-LD; falls back to readable main content.
- Conditional requests (ETag / Last-Modified) avoid refetching unchanged pages.
- Login walls / CAPTCHAs / 401 / 403 are reported as unavailable — never bypassed.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any
from urllib.parse import urljoin, urlsplit
from xml.etree import ElementTree as ET  # noqa: S405 - parsing size-capped XML from permitted sources, no DTDs

from pydantic import BaseModel, ConfigDict, Field, field_validator
from selectolax.lexbor import LexborHTMLParser as HTMLParser

from unjobless.core.errors import BlockedURL, FetchFailed
from unjobless.domain.enums import CollectionMethod, SourceCategory
from unjobless.fetch.politeness import RateLimitWait
from unjobless.fetch.urls import canonicalize_url, host_of
from unjobless.intelligence.structured import extract_main_text, find_jobpostings, looks_like_access_wall, page_meta
from unjobless.sources.contract import (
    CollectContext,
    CollectedItem,
    Connector,
    ConnectorInfo,
    SourceRateLimited,
    SourceUnavailable,
)
from unjobless.sources.registry import register

HTML_TYPES = ("text/html", "application/xhtml+xml")
XML_TYPES = ("application/xml", "text/xml", "application/rss+xml", "application/atom+xml", "text/plain")


class CareerPageConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_urls: list[str] = Field(default_factory=list, max_length=10, description="Listing pages to discover job links from.")
    sitemap_url: str | None = None
    feed_url: str | None = Field(default=None, description="RSS or Atom feed of job posts.")
    allowed_path_prefixes: list[str] = Field(default_factory=lambda: ["/"], max_length=20)
    job_link_selector: str | None = Field(default=None, max_length=200, description="CSS selector for job links on listing pages.")
    job_url_pattern: str | None = Field(default=None, max_length=300, description="Regex a job detail URL must match.")
    content_selector: str | None = Field(default=None, max_length=200, description="CSS selector for the main job content.")
    max_pages: int = Field(default=50, ge=1, le=500)
    respect_robots: bool = Field(default=True, description="Always true in practice; kept explicit for review.")

    @field_validator("job_url_pattern")
    @classmethod
    def _regex(cls, v: str | None) -> str | None:
        if v:
            re.compile(v)
        return v

    @field_validator("respect_robots")
    @classmethod
    def _robots(cls, v: bool) -> bool:
        if not v:
            raise ValueError("robots.txt compliance cannot be disabled")
        return v


@register
class CareerPageConnector(Connector):
    info = ConnectorInfo(
        type="career_page",
        name="Career page crawler",
        category=SourceCategory.CAREER_PAGE,
        collection_method=CollectionMethod.HTML_CRAWL,
        description="Crawls a company's own careers pages on a domain you have reviewed and enabled.",
        documentation_url=None,
        terms_url=None,
        config_model=CareerPageConfig,
        default_schedule_seconds=6 * 3600,
        default_rate_limit_per_minute=10,
        supports_pagination=False,
        supports_incremental=True,
        content_types=HTML_TYPES + XML_TYPES,
        terms_review=(
            "Before enabling: read the site's terms of use and robots.txt; only enable domains that permit "
            "automated access to their public career pages."
        ),
    )

    # ------------------------------------------------------------ helpers
    def _in_scope(self, ctx: CollectContext, cfg: CareerPageConfig, url: str) -> bool:
        host = host_of(url)
        dom = (ctx.source_domain or "").lower()
        if not host or not dom or not (host == dom or host.endswith("." + dom)):
            return False
        if urlsplit(url).scheme not in ("http", "https"):
            return False
        path = urlsplit(url).path or "/"
        return any(path.startswith(p) for p in cfg.allowed_path_prefixes)

    def _get(self, ctx: CollectContext, url: str, *, types: tuple[str, ...], headers: dict[str, str] | None = None) -> Any:
        if ctx.polite_get is None:
            raise RuntimeError("polite fetch unavailable")
        try:
            return ctx.polite_get(url, content_types=types, extra_headers=headers or {})
        except RateLimitWait as e:
            raise SourceRateLimited("Host rate limit / crawl-delay", retry_after=e.seconds) from e

    def _discover(self, ctx: CollectContext, cfg: CareerPageConfig) -> Iterator[tuple[str, dict[str, Any] | None]]:
        seen: set[str] = set()
        pattern = re.compile(cfg.job_url_pattern) if cfg.job_url_pattern else None

        def accept(u: str) -> bool:
            c = canonicalize_url(u)
            if c in seen or not self._in_scope(ctx, cfg, u) or (pattern and not pattern.search(u)):
                return False
            seen.add(c)
            return True

        for feed in [cfg.sitemap_url, cfg.feed_url]:
            if not feed or not self._in_scope(ctx, cfg, feed):
                continue
            try:
                res = self._get(ctx, feed, types=XML_TYPES)
            except (BlockedURL, FetchFailed):
                continue
            if res.status_code >= 400:
                continue
            for u, extra in _parse_feed(res.body):
                if accept(u):
                    yield u, extra
        for start in cfg.start_urls:
            if not self._in_scope(ctx, cfg, start):
                continue
            try:
                res = self._get(ctx, start, types=HTML_TYPES)
            except BlockedURL as e:
                if e.code == "robots_disallow":
                    raise SourceUnavailable(f"robots.txt disallows {start}") from e
                raise SourceUnavailable(e.message) from e
            if res.status_code in (401, 403):
                raise SourceUnavailable(f"Listing page requires access (HTTP {res.status_code}); not bypassed.")
            if res.status_code >= 400:
                continue
            html = res.text
            if looks_like_access_wall(html, extract_main_text(html)):
                raise SourceUnavailable("Listing page shows a login or CAPTCHA wall; not bypassed.")
            # Listing pages may themselves embed JobPosting data
            for jp in find_jobpostings(html):
                if jp.get("posting_url") and accept(urljoin(res.url, jp["posting_url"])):
                    yield urljoin(res.url, jp["posting_url"]), None
            tree = HTMLParser(html)
            nodes = tree.css(cfg.job_link_selector) if cfg.job_link_selector else tree.css("a[href]")
            for a in nodes:
                href = a.attributes.get("href") if a.tag == "a" else (a.css_first("a[href]").attributes.get("href") if a.css_first("a[href]") else None)
                if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
                    continue
                u = urljoin(res.url, href)
                if (cfg.job_link_selector or pattern) and accept(u):
                    yield u, None

    # ------------------------------------------------------------ main
    def collect(self, ctx: CollectContext) -> Iterator[CollectedItem]:
        cfg: CareerPageConfig = ctx.config  # type: ignore[assignment]
        etags: dict[str, Any] = dict((ctx.cursor or {}).get("validators", {}))
        new_validators: dict[str, Any] = {}
        count = 0
        unchanged: list[str] = []
        for url, extra in self._discover(ctx, cfg):
            if count >= cfg.max_pages:
                break
            count += 1
            ctx.check_cancel()
            key = canonicalize_url(url)
            headers: dict[str, str] = {}
            v = etags.get(key) or {}
            if v.get("etag"):
                headers["If-None-Match"] = v["etag"]
            if v.get("last_modified"):
                headers["If-Modified-Since"] = v["last_modified"]
            try:
                res = self._get(ctx, url, types=HTML_TYPES, headers=headers)
            except BlockedURL:
                continue  # robots-disallowed detail page: skip, never bypass
            except FetchFailed:
                continue
            if res.status_code == 304:
                new_validators[key] = v
                unchanged.append(key)
                continue
            if res.status_code >= 400:
                continue
            html = res.text
            meta = page_meta(html)
            if "noindex" in (meta.get("robots") or "") and "none" not in (meta.get("robots") or ""):
                pass  # noindex concerns search indexing, not reading; still collected for the owner only
            text = extract_main_text(html, cfg.content_selector)
            if looks_like_access_wall(html, text):
                continue
            postings = find_jobpostings(html)
            canonical = meta.get("canonical")
            canonical = urljoin(res.url, canonical) if canonical and self._in_scope(ctx, cfg, urljoin(res.url, canonical)) else res.url
            structured = postings or ([extra] if extra else None)
            if structured:
                for s in structured:
                    s.setdefault("posting_url", canonical)
                    if not s.get("description_text"):
                        s["description_text"] = text
            new_validators[key] = {"etag": res.headers.get("etag"), "last_modified": res.headers.get("last-modified")}
            yield CollectedItem(
                native_id=None,
                url=res.url,
                canonical_url=canonicalize_url(canonical),
                application_url=(postings[0].get("application_url") if postings else None),
                content_type="text/html",
                raw_text=html,
                extracted_text=text,
                title=(postings[0].get("title") if postings else None) or meta.get("og:title") or meta.get("title"),
                published_at=None,
                metadata={k: v for k, v in meta.items() if k != "robots"} | {"http_status": res.status_code},
                structured=structured,
            )
        ctx.set_cursor({"validators": new_validators, "unchanged": len(unchanged)})
        ctx.listing_complete = False  # crawls are partial views; absence never implies closure


def _parse_feed(body: bytes) -> Iterator[tuple[str, dict[str, Any] | None]]:
    if b"<!DOCTYPE" in body[:2000].upper() or b"<!ENTITY" in body[:5000].upper():
        return  # refuse DTDs/entities (XML bomb protection)
    try:
        root = ET.fromstring(body)  # noqa: S314
    except ET.ParseError:
        return
    for el in root.iter():
        tag = el.tag.split("}")[-1]
        if tag == "loc" and el.text:
            yield el.text.strip(), None
        elif tag == "item":
            link = next((c.text for c in el if c.tag.split("}")[-1] == "link" and c.text), None)
            title = next((c.text for c in el if c.tag.split("}")[-1] == "title"), None)
            if link:
                yield link.strip(), {"@type": "UnjoblessJob", "provenance": "rss_item", "title": title, "posting_url": link.strip()}
        elif tag == "entry":
            link = next((c.attrib.get("href") for c in el if c.tag.split("}")[-1] == "link" and c.attrib.get("href")), None)
            title = next((c.text for c in el if c.tag.split("}")[-1] == "title"), None)
            if link:
                yield link.strip(), {"@type": "UnjoblessJob", "provenance": "atom_entry", "title": title, "posting_url": link.strip()}
