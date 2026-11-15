"""robots.txt compliance and per-host / per-source rate limiting, shared across workers via Postgres."""

from __future__ import annotations

import time
from datetime import timedelta
from urllib import robotparser
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from unjobless.core.errors import BlockedURL, FetchFailed
from unjobless.core.time import utcnow
from unjobless.db.models import FetchLog, HostRateState
from unjobless.fetch.safe_fetch import FetchResult, SafeFetcher

ROBOTS_TTL = timedelta(hours=24)
MAX_INLINE_WAIT_SECONDS = 20.0


class RateLimitWait(Exception):
    """The host or source is not ready; retry after `seconds`."""

    def __init__(self, seconds: float):
        super().__init__(f"rate limited for {seconds:.1f}s")
        self.seconds = seconds


def _host_row(db: Session, host: str) -> HostRateState:
    db.execute(insert(HostRateState).values(host=host).on_conflict_do_nothing(index_elements=["host"]))
    row = db.execute(select(HostRateState).where(HostRateState.host == host).with_for_update()).scalar_one()
    return row


def reserve_slot(db: Session, host: str, min_interval_seconds: float, *, max_wait: float = MAX_INLINE_WAIT_SECONDS) -> None:
    """Reserve the next request slot for `host`. Sleeps briefly or raises RateLimitWait.

    Uses a row lock so concurrent workers serialise per host.
    """
    row = _host_row(db, host)
    now = utcnow()
    interval = max(min_interval_seconds, row.crawl_delay_seconds or 0.0)
    wait = (row.next_allowed_at - now).total_seconds() if row.next_allowed_at > now else 0.0
    if wait > max_wait:
        db.commit()
        raise RateLimitWait(wait)
    start = max(now, row.next_allowed_at)
    row.next_allowed_at = start + timedelta(seconds=interval)
    db.commit()  # release the lock before sleeping
    if wait > 0:
        time.sleep(wait)


def robots_for(db: Session, fetcher: SafeFetcher, url: str) -> robotparser.RobotFileParser:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    row = _host_row(db, host)
    if row.robots_fetched_at is None or utcnow() - row.robots_fetched_at > ROBOTS_TTL:
        robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
        text = ""
        try:
            res = fetcher.get(robots_url, accept="text/plain", content_types=("text/plain", "text/html"), max_bytes=512 * 1024)
            if res.status_code in (401, 403):
                text = "User-agent: *\nDisallow: /"  # RFC 9309: unauthorised → treat as full disallow
            elif res.status_code < 400:
                text = res.text
            elif res.status_code >= 500:
                text = "User-agent: *\nDisallow: /"  # server error → assume disallow (RFC 9309 §2.3.1.4)
        except (BlockedURL, FetchFailed):
            text = "User-agent: *\nDisallow: /"
        row.robots_txt = text
        row.robots_fetched_at = utcnow()
        rp = robotparser.RobotFileParser()
        rp.parse(text.splitlines())
        delay = rp.crawl_delay(fetcher.user_agent) or rp.crawl_delay("*")
        row.crawl_delay_seconds = float(delay) if delay else None
        db.commit()
    rp = robotparser.RobotFileParser()
    rp.parse((row.robots_txt or "").splitlines())
    return rp


def robots_allows(db: Session, fetcher: SafeFetcher, url: str) -> bool:
    rp = robots_for(db, fetcher, url)
    return rp.can_fetch(fetcher.user_agent, url)


def log_fetch(db: Session, outcome: str, host: str | None, reason: str | None, status: int | None = None, size: int | None = None) -> None:
    db.add(FetchLog(host=host, outcome=outcome, reason=(reason or "")[:300], status_code=status, bytes=size))


def polite_get(
    db: Session,
    fetcher: SafeFetcher,
    url: str,
    *,
    min_interval_seconds: float = 2.0,
    respect_robots: bool = True,
    **kw: object,
) -> FetchResult:
    """Fetch with robots.txt compliance and host rate limiting (used by crawlers)."""
    host = urlsplit(url).hostname
    if respect_robots and not robots_allows(db, fetcher, url):
        log_fetch(db, "blocked", host, "robots_disallow")
        raise BlockedURL("robots.txt does not allow fetching this page.", code="robots_disallow")
    reserve_slot(db, (host or "").lower(), min_interval_seconds)
    return fetcher.get(url, **kw)  # type: ignore[arg-type]
