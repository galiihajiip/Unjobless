"""Deterministic mock connector for tests and demos. Emits items from its config; no network."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from unjobless.domain.enums import CollectionMethod, SourceCategory
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


class MockItem(BaseModel):
    id: str
    title: str
    body: str = ""
    url: str | None = None


class MockConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[MockItem] = Field(default_factory=list, max_length=200)
    page_size: int = Field(default=50, ge=1, le=200)
    fail_with: str | None = Field(default=None, description="test hook: 'error' | 'unavailable' | 'rate_limited'")


@register
class MockConnector(Connector):
    info = ConnectorInfo(
        type="mock",
        name="Mock connector (testing)",
        category=SourceCategory.JOB_API,
        collection_method=CollectionMethod.OFFICIAL_API,
        description="Emits configured items without network access. For tests and local demos.",
        documentation_url=None,
        terms_url=None,
        config_model=MockConfig,
        default_schedule_seconds=3600,
        supports_pagination=True,
        supports_incremental=True,
        terms_review="No external source; safe to enable.",
    )

    def collect(self, ctx: CollectContext) -> Iterator[CollectedItem]:
        cfg: Any = ctx.config
        if cfg.fail_with == "error":
            raise RuntimeError("mock failure")
        if cfg.fail_with == "unavailable":
            raise SourceUnavailable("mock source requires login")
        if cfg.fail_with == "rate_limited":
            raise SourceRateLimited("mock quota exceeded", retry_after=120)
        start = int(ctx.cursor.get("offset", 0)) if ctx.cursor else 0
        items = cfg.items
        for i in range(0, len(items), cfg.page_size):
            ctx.check_cancel()
            for it in items[i : i + cfg.page_size]:
                yield CollectedItem(
                    native_id=it.id,
                    url=it.url or f"https://mock.invalid/jobs/{it.id}",
                    content_type="application/json",
                    raw_text=f"{it.title}\n\n{it.body}",
                    title=it.title,
                    metadata={"mock": True},
                )
        ctx.listing_complete = True
        ctx.set_cursor({"offset": start, "seen": len(items)})

    def health_check(self, ctx: CollectContext) -> HealthResult:
        cfg: Any = ctx.config
        return HealthResult(ok=cfg.fail_with is None, message="mock" if cfg.fail_with is None else cfg.fail_with)
