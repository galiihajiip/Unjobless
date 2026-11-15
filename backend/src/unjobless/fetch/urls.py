"""URL parsing, canonicalisation and denylist matching (no network)."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "utm_id", "gclid", "fbclid",
    "mc_cid", "mc_eid", "igshid", "ref", "ref_src", "_hsenc", "_hsmi", "si", "trk", "trackingId",
}


def host_of(url: str) -> str | None:
    try:
        h = urlsplit(url.strip()).hostname
    except ValueError:
        return None
    return h.lower().rstrip(".") if h else None


def registrable_hint(host: str) -> str:
    """Display helper: strip leading www."""
    return host[4:] if host.startswith("www.") else host


def canonicalize_url(url: str) -> str:
    """Stable canonical form: lowercase scheme/host, drop fragment, default port, tracking params, trailing slash."""
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower().rstrip(".")
    port = parts.port
    netloc = host
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{host}:{port}"
    query = urlencode(sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k not in TRACKING_PARAMS))
    path = parts.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]
    return urlunsplit((scheme, netloc, path, query, ""))


def matches_exclusion(url: str, pattern: str) -> bool:
    """`pattern` is a bare domain (matches the domain and its subdomains) or a URL prefix."""
    pattern = pattern.strip().lower()
    if "://" in pattern:
        return canonicalize_url(url).lower().startswith(canonicalize_url(pattern).lower().rstrip("/"))
    host = host_of(url)
    if not host:
        return False
    pattern = pattern.lstrip(".")
    return host == pattern or host.endswith("." + pattern)
