"""Shared test helpers: fake fetcher returning fixture bodies, approved sources."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from unjobless.domain.enums import PolicyStatus, SourceState
from unjobless.fetch.safe_fetch import FetchResult
from unjobless.sources import service

FIX = Path(__file__).parent / "fixtures"


class FakeFetcher:
    """Maps URL → (status, content_type, body). Unknown URLs return 404."""

    user_agent = "test"

    def __init__(self, routes: dict[str, tuple[int, str, bytes | str]] | None = None):
        self.routes = routes or {}
        self.calls: list[str] = []

    def get(self, url: str, **kw: Any) -> FetchResult:
        self.calls.append(url)
        status, ctype, body = self.routes.get(url, (404, "text/plain", b""))
        b = body.encode() if isinstance(body, str) else body
        return FetchResult(
            url=url,
            requested_url=url,
            status_code=status,
            content_type=ctype,
            charset="utf-8",
            body=b,
            truncated=False,
            headers={},
        )

    def close(self) -> None:
        pass


def fixture_json(name: str) -> bytes:
    return (FIX / "ats" / name).read_bytes()


def approved_source(db, *, key: str, connector_type: str, config: dict[str, Any], domain: str | None = None):
    s = service.create_source(
        db, key=key, name=key, connector_type=connector_type, config=config, domain=domain
    )
    service.review_policy(db, s, decision=PolicyStatus.APPROVED, terms_notes="test")
    service.change_state(db, s, SourceState.ENABLED)
    return s


def load(name: str) -> Any:
    return json.loads((FIX / name).read_text())
