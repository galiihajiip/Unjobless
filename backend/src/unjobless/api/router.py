"""Aggregates every owner-only router. All routes here require an authenticated owner session
(and a CSRF token on unsafe methods) via a router-level dependency, so a new route cannot
accidentally be public."""

from __future__ import annotations

import importlib

from fastapi import APIRouter, Depends

from unjobless.api.deps import require_owner

PRIVATE_MODULES: list[str] = [
    "unjobless.api.sources",
    "unjobless.api.ai",
]


def build_private_router() -> APIRouter:
    router = APIRouter(dependencies=[Depends(require_owner)])
    for mod in PRIVATE_MODULES:
        router.include_router(importlib.import_module(mod).router)
    return router
