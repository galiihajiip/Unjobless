"""Public Telegram channels via Telegram's own web preview (https://t.me/s/<channel>).

Many Indonesian job/internship channels (loker, magang, BUMN, developer jobs) are public broadcast
channels. Telegram publishes a read-only web preview of every *public* channel for anyone without
logging in; this connector reads that preview politely (robots.txt + per-host rate limit), newest
first, and pages back with `?before=<id>` only until it reaches posts it already has.

- Only public channels: private channels/groups have no preview and are skipped, never joined.
- Posts are social content → they go through Opportunity Signals (vacancy vs lead vs noise) and are
  never auto-verified. Posts link back to the original t.me message.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator
from selectolax.lexbor import LexborHTMLParser

from unjobless.core.errors import BlockedURL, FetchFailed
from unjobless.domain.enums import CollectionMethod, SourceCategory
from unjobless.intelligence.text import clean_text
from unjobless.sources.contract import (
    CollectContext,
    CollectedItem,
    Connector,
    ConnectorInfo,
    SourceUnavailable,
)
from unjobless.sources.registry import register

BASE = "https://t.me"
CHANNEL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{3,63}$")
DEFAULT_CHANNELS = [
    "disnakerja",
    "lokerbumncom",
    "LokerDeveloper",
    "LokerEventDeveloperProgrammerId",
    "kerjango",
    "lowkerinfo",
    "infolowongankerja",
    "lokerbandung",
]


class TelegramConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    channels: list[str] = Field(
        default_factory=lambda: list(DEFAULT_CHANNELS),
        min_length=1,
        max_length=40,
        description="Public channel usernames (without @), e.g. lokerbumncom",
    )
    pages_per_channel: int = Field(
        default=3, ge=1, le=20, description="How far back to read on the first run (≈20 posts per page)."
    )
    keywords: list[str] = Field(
        default_factory=list,
        max_length=50,
        description="Keep only posts containing one of these words (empty = keep all; Signals filters noise).",
    )
    min_chars: int = Field(default=40, ge=0, le=1000)

    @field_validator("channels")
    @classmethod
    def _channels(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        for c in v:
            c = c.strip().lstrip("@").removeprefix("https://t.me/").removeprefix("s/").strip("/")
            if not CHANNEL_RE.match(c):
                raise ValueError(f"Not a public channel username: {c!r}")
            if c.lower() not in (x.lower() for x in out):
                out.append(c)
        return out


def _text(node: Any) -> str:
    html = node.html or ""
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    return clean_text(LexborHTMLParser(html).text(deep=True, separator=""))


def parse_page(html: str, channel: str) -> list[dict[str, Any]]:
    """Messages on one preview page, oldest first."""
    tree = LexborHTMLParser(html)
    posts: list[dict[str, Any]] = []
    for m in tree.css("div.tgme_widget_message[data-post]"):
        post = m.attributes.get("data-post") or ""
        ch, _, num = post.partition("/")
        if not num.isdigit() or ch.lower() != channel.lower():
            continue
        tnode = m.css_first(".tgme_widget_message_text")
        text = _text(tnode) if tnode is not None else ""
        links: list[str] = []
        for a in ([*tnode.css("a[href]")] if tnode is not None else []) + list(
            m.css("a.tgme_widget_message_link_preview[href]")
        ):
            href = (a.attributes.get("href") or "").strip()
            if href.startswith(("http://", "https://")) and href not in links:
                links.append(href)
        when = None
        tm = m.css_first(".tgme_widget_message_date time[datetime]") or m.css_first("time[datetime]")
        if tm is not None:
            try:
                when = datetime.fromisoformat(str(tm.attributes.get("datetime")))
            except ValueError:
                when = None
        fwd = m.css_first(".tgme_widget_message_forwarded_from_name")
        posts.append(
            {
                "id": int(num),
                "channel": ch,
                "text": text,
                "links": links[:10],
                "published_at": when,
                "forwarded_from": clean_text(fwd.text()) if fwd is not None else None,
            }
        )
    return sorted(posts, key=lambda p: p["id"])


@register
class TelegramChannelConnector(Connector):
    info = ConnectorInfo(
        type="telegram_channel",
        name="Public Telegram channels (loker / magang)",
        category=SourceCategory.SOCIAL_API,
        collection_method=CollectionMethod.HTML_CRAWL,
        description=(
            "Reads public Telegram job channels through Telegram's public web preview (t.me/s/…), no login. "
            "Posts are classified by Opportunity Signals; nothing is auto-verified."
        ),
        documentation_url="https://telegram.org/faq_channels",
        terms_url="https://telegram.org/tos",
        config_model=TelegramConfig,
        default_schedule_seconds=1800,
        default_rate_limit_per_minute=20,
        supports_pagination=True,
        supports_incremental=True,
        max_items_per_run=2000,
        content_types=("text/html",),
        terms_review=(
            "Telegram's public web preview of public channels; read-only, polite rate, robots.txt respected. "
            "Private channels and groups are never accessed."
        ),
        attribution="Links to the original Telegram post and names the channel.",
    )

    def _get(self, ctx: CollectContext, url: str) -> Any:
        if ctx.polite_get is None:
            raise RuntimeError("polite fetch unavailable")
        try:
            return ctx.polite_get(url, content_types=("text/html",))
        except BlockedURL as e:
            raise SourceUnavailable(e.message) from e

    def collect(self, ctx: CollectContext) -> Iterator[CollectedItem]:
        cfg: Any = ctx.config
        cursor: dict[str, Any] = dict((ctx.cursor or {}).get("last_ids") or {})
        kws = [k.lower() for k in cfg.keywords if k.strip()]
        failed: list[str] = []
        for ch in cfg.channels:
            ctx.check_cancel()
            last = int(cursor.get(ch.lower(), 0))
            newest = last
            url = f"{BASE}/s/{ch}"
            for _ in range(cfg.pages_per_channel if not last else 20):
                try:
                    res = self._get(ctx, url)
                except FetchFailed as e:
                    ctx.log and ctx.log.warning("telegram_fetch_failed", channel=ch, error=e.message)
                    failed.append(ch)
                    break
                posts = parse_page(res.body.decode("utf-8", "replace") if res.body else "", ch)
                if res.status_code >= 400 or not posts:
                    if newest == last:
                        failed.append(ch)  # not public / no preview / renamed
                    break
                for p in posts:
                    if p["id"] <= last:
                        continue
                    newest = max(newest, p["id"])
                    text = p["text"]
                    if len(text) < cfg.min_chars:
                        continue
                    if kws and not any(k in text.lower() for k in kws):
                        continue
                    link = f"{BASE}/{p['channel']}/{p['id']}"
                    external = next((x for x in p["links"] if "t.me/" not in x), None)
                    body = text + (
                        "\n\nLinks:\n" + "\n".join(p["links"]) if p["links"] else ""
                    )
                    yield CollectedItem(
                        native_id=f"{p['channel'].lower()}/{p['id']}",
                        url=link,
                        canonical_url=link,
                        application_url=external,
                        content_type="text/plain",
                        raw_text=body,
                        extracted_text=body,
                        title=text.splitlines()[0][:200] if text else None,
                        published_at=p["published_at"],
                        metadata={
                            "via": "telegram",
                            "channel": p["channel"],
                            "links": p["links"],
                            "forwarded_from": p["forwarded_from"],
                        },
                    )
                oldest = posts[0]["id"]
                if oldest <= last + 1 or oldest <= 1:
                    break
                url = f"{BASE}/s/{ch}?before={oldest}"
            cursor[ch.lower()] = newest
        if failed and len(failed) == len(cfg.channels):
            raise SourceUnavailable(
                f"No public preview for: {', '.join(failed)}. Check the channel usernames are public."
            )
        ctx.set_cursor({"last_ids": cursor, "unavailable": failed})
