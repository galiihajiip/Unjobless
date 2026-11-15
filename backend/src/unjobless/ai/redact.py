"""Data minimisation before sending profile data to an AI provider."""

from __future__ import annotations

import re
from typing import Any

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE = re.compile(r"(?<!\d)(?:\+?\d[\d\s().-]{7,}\d)(?!\d)")
CONTACT_KEYS = {"email", "phone", "address", "full_name", "date_of_birth", "national_id"}


def redact_text(text: str) -> str:
    return PHONE.sub("[phone]", EMAIL.sub("[email]", text))


def redact_profile(data: Any) -> Any:
    """Drop contact fields and scrub emails/phones from free text. Used for matching/tailoring tasks."""
    if isinstance(data, dict):
        return {k: redact_profile(v) for k, v in data.items() if k not in CONTACT_KEYS}
    if isinstance(data, list):
        return [redact_profile(x) for x in data]
    if isinstance(data, str):
        return redact_text(data)
    return data
