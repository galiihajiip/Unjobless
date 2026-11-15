"""Connector registry: maps `connector_type` → connector class."""

from __future__ import annotations

from unjobless.core.errors import NotFound
from unjobless.sources.contract import Connector, ConnectorInfo

_REGISTRY: dict[str, type[Connector]] = {}


def register[C: type[Connector]](cls: C) -> C:
    t = cls.info.type
    if t in _REGISTRY and _REGISTRY[t] is not cls:
        raise ValueError(f"connector type {t!r} already registered")
    _REGISTRY[t] = cls
    return cls


def get_connector_class(connector_type: str) -> type[Connector]:
    _load_builtin()
    try:
        return _REGISTRY[connector_type]
    except KeyError as exc:
        raise NotFound(f"Unknown connector type {connector_type!r}") from exc


def all_connectors() -> list[ConnectorInfo]:
    _load_builtin()
    return [c.info for c in _REGISTRY.values()]


_loaded = False


def _load_builtin() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True
    # Importing registers them.
    from unjobless.sources import connectors  # noqa: F401
