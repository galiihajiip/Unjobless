"""Recommended sources, verified on 2026-11-16 to have public documented job APIs with jobs in
Indonesia or remote jobs open to Indonesian applicants. Adding the pack is an explicit owner action:
a policy review recording the source's API terms is stored for each source before it is enabled."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from unjobless.db.models import Source
from unjobless.domain.enums import PolicyStatus, SourceState
from unjobless.sources import service
from unjobless.sources.registry import get_connector_class

ID_LOC = ["indonesia", "jakarta", "bandung", "surabaya", "yogyakarta", "bali", "tangerang", "remote"]

PACK: list[dict[str, Any]] = [
    {
        "key": "grab-id",
        "name": "Grab (Indonesia jobs)",
        "connector_type": "smartrecruiters",
        "config": {"board": "grab", "company_name": "Grab", "location_keywords": ID_LOC},
    },
    {
        "key": "xendit",
        "name": "Xendit",
        "connector_type": "greenhouse_board",
        "config": {"board": "xendit", "company_name": "Xendit", "location_keywords": ID_LOC},
    },
    {
        "key": "flip-id",
        "name": "Flip",
        "connector_type": "ashby_board",
        "config": {"board": "flip", "company_name": "Flip", "location_keywords": ID_LOC},
    },
    {
        "key": "kargo",
        "name": "Kargo Technologies",
        "connector_type": "greenhouse_board",
        "config": {"board": "kargo", "company_name": "Kargo Technologies", "location_keywords": ID_LOC},
    },
    {
        "key": "alodokter",
        "name": "Alodokter",
        "connector_type": "smartrecruiters",
        "config": {"board": "alodokter", "company_name": "Alodokter"},
    },
    {
        "key": "stockbit",
        "name": "Stockbit",
        "connector_type": "smartrecruiters",
        "config": {"board": "stockbit", "company_name": "Stockbit"},
    },
    {
        "key": "julo",
        "name": "JULO",
        "connector_type": "smartrecruiters",
        "config": {"board": "julo", "company_name": "JULO"},
    },
    {
        "key": "sayurbox",
        "name": "Sayurbox",
        "connector_type": "smartrecruiters",
        "config": {"board": "sayurbox", "company_name": "Sayurbox"},
    },
    {
        "key": "pahamify",
        "name": "Pahamify",
        "connector_type": "smartrecruiters",
        "config": {"board": "pahamify", "company_name": "Pahamify"},
    },
    {
        "key": "himalayas",
        "name": "Himalayas (remote, open to Indonesia/Asia)",
        "connector_type": "himalayas_feed",
        "config": {},
    },
    {
        "key": "remotive",
        "name": "Remotive (remote, open to Indonesia/Asia)",
        "connector_type": "remotive_feed",
        "config": {},
    },
    {
        "key": "remoteok",
        "name": "Remote OK (remote, open to Indonesia/Asia)",
        "connector_type": "remoteok_feed",
        "config": {},
    },
    {
        "key": "telegram-loker",
        "name": "Telegram loker & magang channels",
        "connector_type": "telegram_channel",
        "config": {},
    },
]


def describe() -> list[dict[str, Any]]:
    out = []
    for p in PACK:
        info = get_connector_class(p["connector_type"]).info
        out.append(
            {
                **p,
                "connector_name": info.name,
                "terms_review": info.terms_review,
                "documentation_url": info.documentation_url,
                "attribution": info.attribution,
            }
        )
    return out


def install(db: Session, keys: list[str]) -> list[Source]:
    created = []
    for p in PACK:
        if p["key"] not in keys:
            continue
        if db.execute(select(Source).where(Source.key == p["key"])).scalar_one_or_none():
            continue
        info = get_connector_class(p["connector_type"]).info
        src = service.create_source(
            db, key=p["key"], name=p["name"], connector_type=p["connector_type"], config=p["config"]
        )
        service.review_policy(
            db,
            src,
            decision=PolicyStatus.APPROVED,
            terms_notes=f"{info.terms_review} Attribution: {info.attribution}",
            reviewer_note="Approved by the owner via the recommended sources pack.",
        )
        service.change_state(db, src, SourceState.ENABLED)
        created.append(src)
    return created
