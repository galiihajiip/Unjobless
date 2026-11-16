"""Source connector contract.

A connector is a class that declares *what* it is (ConnectorInfo) and implements `collect`.
The core pipeline (runner → raw store → processing) never needs to change to add a connector:
register the class with `@register` and create a Source row pointing at its `type`.
"""

from __future__ import annotations

import builtins
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar, Protocol

from pydantic import BaseModel, ConfigDict

from unjobless.domain.enums import CollectionMethod, SourceCategory


class EmptyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 30.0
    max_delay_seconds: float = 3600.0


@dataclass(frozen=True)
class ConnectorInfo:
    type: str
    name: str
    category: SourceCategory
    collection_method: CollectionMethod
    description: str
    documentation_url: str | None
    terms_url: str | None
    config_model: builtins.type[BaseModel] = EmptyConfig
    auth_required: bool = False
    default_schedule_seconds: int | None = 3600
    default_rate_limit_per_minute: int = 30
    supports_discovery: bool = True
    supports_pagination: bool = False
    supports_incremental: bool = False
    max_items_per_run: int = 500
    supports_health_check: bool = True
    content_types: tuple[str, ...] = ("application/json",)
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    attribution: str = "Link to the original posting and name the source."
    freshness_strategy: str = (
        "Re-list on each run; items missing from a complete listing are marked not-seen (never closed)."
    )
    terms_review: str = "Review the source's terms before enabling."
    user_visible: bool = True


@dataclass
class CollectedItem:
    """One item as delivered by a source. Only permitted, accessible fields; never cookies or headers."""

    native_id: str | None
    url: str | None
    content_type: str
    raw_text: str
    title: str | None = None
    canonical_url: str | None = None
    application_url: str | None = None
    published_at: datetime | None = None
    language: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    structured: list[dict[str, Any]] | None = None
    extracted_text: str | None = None
    # True when the connector only confirms the item is still listed (unchanged); nothing is stored.
    listing_only: bool = False


@dataclass
class HealthResult:
    ok: bool
    message: str
    rate_limited: bool = False


class CollectionCancelled(Exception):
    pass


class SourceUnavailable(Exception):
    """Source blocked access (login, captcha, 401/403, robots). Never bypassed."""


class SourceRateLimited(Exception):
    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class Fetcher(Protocol):
    def get(self, url: str, **kw: Any) -> Any: ...


@dataclass
class CollectContext:
    config: BaseModel
    cursor: dict[str, Any]
    fetcher: Any
    get_secret: Callable[[], str | None]
    is_cancelled: Callable[[], bool] = lambda: False
    max_items: int = 500
    new_cursor: dict[str, Any] | None = None
    listing_complete: bool = False
    log: Any = None
    source_domain: str | None = None
    min_interval_seconds: float = 2.0
    # Fetch with robots.txt compliance + shared per-host rate limiting (provided by the runner).
    polite_get: Callable[..., Any] | None = None

    def check_cancel(self) -> None:
        if self.is_cancelled():
            raise CollectionCancelled()

    def set_cursor(self, cursor: dict[str, Any]) -> None:
        self.new_cursor = cursor


class Connector:
    info: ClassVar[ConnectorInfo]

    def collect(self, ctx: CollectContext) -> Iterator[CollectedItem]:  # pragma: no cover - interface
        raise NotImplementedError

    def health_check(self, ctx: CollectContext) -> HealthResult:
        return HealthResult(ok=True, message="No health check implemented; status derives from runs.")
