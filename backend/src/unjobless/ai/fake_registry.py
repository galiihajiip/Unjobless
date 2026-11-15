"""Handler used by the `fake` provider kind (tests/demos). Set HANDLER to a callable(system, user, schema) -> dict."""

from collections.abc import Callable
from typing import Any

HANDLER: Callable[[str, str, dict[str, Any]], dict[str, Any]] | None = None
