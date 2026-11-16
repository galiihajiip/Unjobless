"""Job-alert mailbox connector (IMAP).

Job platforms that block bots (Glints, LinkedIn, JobStreet, Kalibrr, Indeed…) offer e-mail job alerts
to their users. The owner subscribes to alerts with a dedicated mailbox; this connector reads that
mailbox read-only (it never marks messages as read or deletes them) and turns every job link in an
alert from an allowed sender into a collected item. Job pages themselves are NOT fetched.

Security:
- the IMAP password/app-password is stored encrypted (source secret), never in config;
- the IMAP host must resolve to public addresses only (no internal hosts), TLS on port 993;
- only messages from configured sender domains are processed; content is untrusted data.
"""

from __future__ import annotations

import email
import email.policy
import imaplib
import re
import socket
import ssl
from collections.abc import Iterator
from email.message import EmailMessage
from email.utils import parseaddr, parsedate_to_datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator
from selectolax.lexbor import LexborHTMLParser

from unjobless.core.errors import BlockedURL
from unjobless.domain.enums import CollectionMethod, SourceCategory
from unjobless.fetch.safe_fetch import ip_is_public, validate_url
from unjobless.intelligence.text import clean_text, html_to_text
from unjobless.sources.contract import CollectContext, CollectedItem, Connector, ConnectorInfo, HealthResult, SourceUnavailable
from unjobless.sources.registry import register

DEFAULT_SENDERS = [
    "glints.com", "linkedin.com", "jobstreet.com", "jobstreet.co.id", "seek.com", "kalibrr.com", "indeed.com",
    "karir.com", "jobs.id", "kitalulus.com", "dealls.com", "topkarir.com", "ekrut.com",
]
JOB_LINK = re.compile(r"(/jobs?/|/opportunities/|/lowongan|/loker|/career|/vacanc|/job-detail|/viewjob|/comm/jobs/view|jobid=|/j/)", re.I)
SKIP_LINK = re.compile(r"(unsubscribe|preferences|settings|privacy|terms|help|login|signin|sign-in|app\.|apps\.apple|play\.google|/search\?|alert|manage)", re.I)
TRACKING = re.compile(r"^(utm_|trk|tracking|ref|refId|trackingId|lipi|midToken|midSig|eid|otpToken|ssid|sid|src|source|mc_)", re.I)
FETCH_LIMIT = 200


class EmailAlertsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    imap_host: str = Field(default="imap.gmail.com", max_length=253, description="IMAP server (TLS, port 993).")
    username: str = Field(min_length=3, max_length=254, description="Mailbox login, e.g. your-alerts@gmail.com")
    folder: str = Field(default="INBOX", max_length=200)
    sender_domains: list[str] = Field(default_factory=lambda: list(DEFAULT_SENDERS), max_length=50, description="Only alerts from these sender domains are read.")
    lookback_days: int = Field(default=14, ge=1, le=90, description="On the first run, read alerts from this many days back.")

    @field_validator("imap_host")
    @classmethod
    def _host(cls, v: str) -> str:
        v = v.strip().lower()
        try:
            validate_url(f"https://{v}/", resolve=False)
        except BlockedURL as e:
            raise ValueError(f"IMAP host not allowed: {e.message}") from e
        return v


def _check_host_public(host: str) -> None:
    try:
        infos = socket.getaddrinfo(host, 993, type=socket.SOCK_STREAM)
    except OSError as e:
        raise SourceUnavailable(f"IMAP host {host} could not be resolved.") from e
    if not infos or any(not ip_is_public(str(i[4][0])) for i in infos):
        raise SourceUnavailable("IMAP host resolves to a private or reserved address.")


def clean_link(url: str) -> str:
    p = urlsplit(url)
    q = urlencode([(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not TRACKING.match(k)])
    return urlunsplit((p.scheme, p.netloc.lower(), p.path.rstrip("/") or "/", q, ""))


def _sender_ok(addr: str, allowed: list[str]) -> bool:
    dom = addr.rsplit("@", 1)[-1].lower()
    return any(dom == a or dom.endswith("." + a) for a in (x.lower().lstrip("@.") for x in allowed))


def parse_alert(msg: EmailMessage) -> list[dict[str, Any]]:
    """Extract job entries (title, link, surrounding text) from one alert e-mail."""
    html_part = msg.get_body(preferencelist=("html",))
    text_part = msg.get_body(preferencelist=("plain",))
    jobs: list[dict[str, Any]] = []
    seen: set[str] = set()
    if html_part is not None:
        tree = LexborHTMLParser(html_part.get_content())
        for a in tree.css("a[href]"):
            href = (a.attributes.get("href") or "").strip()
            title = clean_text(a.text(deep=True, separator=" "))
            if not href.startswith(("http://", "https://")) or not JOB_LINK.search(href) or SKIP_LINK.search(href):
                continue
            if len(title) < 4 or len(title) > 160 or title.lower() in {"view job", "apply", "apply now", "lihat lowongan", "lamar", "see all jobs", "view all"}:
                continue
            link = clean_link(href)
            if link in seen:
                continue
            seen.add(link)
            # Surrounding text: climb to the nearest block that contains more than the title (company, location, salary).
            node, context = a, title
            for _ in range(5):
                node = node.parent
                if node is None:
                    break
                t = clean_text(node.text(deep=True, separator="\n"))
                if len(t) > len(title) + 15:
                    context = t[:1500]
                    break
            jobs.append({"title": title, "url": link, "context": context})
    if not jobs and text_part is not None:
        body = text_part.get_content()
        lines = body.splitlines()
        for i, ln in enumerate(lines):
            for m in re.finditer(r"https?://\S+", ln):
                href = m.group(0).rstrip(").,>")
                if JOB_LINK.search(href) and not SKIP_LINK.search(href):
                    link = clean_link(href)
                    if link in seen:
                        continue
                    seen.add(link)
                    block = [x.strip() for x in lines[max(0, i - 3) : i] if x.strip() and "http" not in x]
                    title = block[0] if block else "Job from alert"
                    jobs.append({"title": title[:160], "url": link, "context": clean_text("\n".join(block))[:1500]})
    return jobs


class _Mailbox:
    """Thin read-only IMAP wrapper (separated so tests can substitute it)."""

    def __init__(self, host: str, username: str, password: str):
        _check_host_public(host)
        ctx = ssl.create_default_context()
        try:
            self.m = imaplib.IMAP4_SSL(host, 993, ssl_context=ctx, timeout=30)
            self.m.login(username, password)
        except imaplib.IMAP4.error as e:
            raise SourceUnavailable("IMAP login failed. Check the username and app password.") from e
        except OSError as e:
            raise RuntimeError(f"IMAP connection failed: {type(e).__name__}") from e

    def fetch_since(self, folder: str, last_uid: int, since_days: int) -> Iterator[tuple[int, bytes]]:
        typ, _ = self.m.select(f'"{folder}"', readonly=True)
        if typ != "OK":
            raise SourceUnavailable(f"Folder {folder!r} not found.")
        if last_uid:
            typ, data = self.m.uid("search", None, f"UID {last_uid + 1}:*")
        else:
            from datetime import date, timedelta

            since = (date.today() - timedelta(days=since_days)).strftime("%d-%b-%Y")
            typ, data = self.m.uid("search", None, f"SINCE {since}")
        uids = sorted(int(u) for u in (data[0] or b"").split() if int(u) > last_uid)[:FETCH_LIMIT]
        for uid in uids:
            typ, parts = self.m.uid("fetch", str(uid), "(BODY.PEEK[])")  # PEEK: never sets \\Seen
            raw = next((p[1] for p in parts if isinstance(p, tuple)), None)
            if raw:
                yield uid, raw

    def close(self) -> None:
        try:
            self.m.logout()
        except Exception:  # noqa: S110
            pass


MAILBOX_FACTORY = _Mailbox  # test hook


@register
class EmailAlertsConnector(Connector):
    info = ConnectorInfo(
        type="email_job_alerts",
        name="Job-alert mailbox (Glints, LinkedIn, JobStreet…)",
        category=SourceCategory.USER_DOCUMENT,
        collection_method=CollectionMethod.OFFICIAL_API,
        description=(
            "Reads job-alert e-mails that job sites send to your own mailbox (read-only, IMAP) and imports every job in them. "
            "Works for platforms that block bots. Subscribe to alerts on each site with this mailbox."
        ),
        documentation_url="https://support.google.com/mail/answer/185833",
        terms_url=None,
        config_model=EmailAlertsConfig,
        auth_required=True,
        default_schedule_seconds=900,
        default_rate_limit_per_minute=30,
        supports_incremental=True,
        content_types=("message/rfc822",),
        terms_review="Your own mailbox and the alerts you subscribed to. Use a dedicated mailbox and an app password.",
        attribution="Links to the original job page on the platform that sent the alert.",
    )

    def collect(self, ctx: CollectContext) -> Iterator[CollectedItem]:
        cfg: Any = ctx.config
        password = ctx.get_secret()
        if not password:
            raise SourceUnavailable("Set the mailbox app password for this source first.")
        last_uid = int((ctx.cursor or {}).get("last_uid", 0))
        mb = MAILBOX_FACTORY(cfg.imap_host, cfg.username, password)
        max_uid = last_uid
        try:
            for uid, raw in mb.fetch_since(cfg.folder, last_uid, cfg.lookback_days):
                ctx.check_cancel()
                max_uid = max(max_uid, uid)
                msg = email.message_from_bytes(raw, policy=email.policy.default)
                assert isinstance(msg, EmailMessage)
                sender = parseaddr(str(msg.get("From", "")))[1]
                if not _sender_ok(sender, cfg.sender_domains):
                    continue
                try:
                    published = parsedate_to_datetime(str(msg.get("Date")))
                except (TypeError, ValueError):
                    published = None
                platform = sender.rsplit("@", 1)[-1]
                for job in parse_alert(msg):
                    yield CollectedItem(
                        native_id=job["url"][:300],
                        url=job["url"],
                        canonical_url=job["url"],
                        application_url=job["url"],
                        content_type="text/plain",
                        raw_text=f"{job['title']}\n\n{job['context']}\n\nSource link: {job['url']}",
                        title=job["title"],
                        published_at=published,
                        metadata={"via": "email_alert", "platform": platform, "alert_subject": str(msg.get("Subject", ""))[:300]},
                        extracted_text=f"{job['title']}\n{job['context']}\nApply: {job['url']}",
                        structured=[{
                            "@type": "UnjoblessJob", "provenance": "email_job_alert", "title": job["title"],
                            "posting_url": job["url"], "application_url": job["url"], "description_text": job["context"],
                        }],
                    )
        finally:
            mb.close()
        ctx.set_cursor({"last_uid": max_uid})

    def health_check(self, ctx: CollectContext) -> HealthResult:
        cfg: Any = ctx.config
        pw = ctx.get_secret()
        if not pw:
            return HealthResult(ok=False, message="No app password set.")
        try:
            MAILBOX_FACTORY(cfg.imap_host, cfg.username, pw).close()
            return HealthResult(ok=True, message="Mailbox login OK.")
        except Exception as e:
            return HealthResult(ok=False, message=str(e)[:200])


def html_preview(msg: EmailMessage) -> str:
    part = msg.get_body(preferencelist=("html", "plain"))
    return html_to_text(part.get_content()) if part else ""
