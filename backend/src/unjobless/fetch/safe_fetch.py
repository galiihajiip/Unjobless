"""SafeFetcher — the only code path that fetches user- or source-supplied URLs.

Defences (docs/architecture/ADRs/0003):
- http/https only; no userinfo; ports restricted to an allowlist (default 80/443);
- hostnames: reject single-label names (Docker service names like `db`), `localhost`,
  `.local`, `.internal`, `.localhost`, `.home.arpa`;
- resolve DNS and require *every* resolved address to be globally routable (blocks private,
  loopback, link-local incl. 169.254.169.254, CGNAT 100.64/10, multicast, reserved, unspecified,
  ULA incl. fd00:ec2::254, IPv4-mapped/6to4/Teredo embeddings of those);
- connect to the validated IP (pinned) with Host header + TLS SNI set to the hostname, so a DNS
  rebinding answer between check and connect cannot redirect the connection;
- manual redirects, each hop re-validated; capped count;
- connect/read/total timeouts; streamed body with a byte cap (applied after decompression, so
  compression bombs stop at the cap); content-type allowlist;
- no cookies, no auth headers, honest User-Agent;
- blocked attempts are logged with host + reason only (no query string, no headers).
"""

from __future__ import annotations

import ipaddress
import socket
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from unjobless.core.config import get_settings
from unjobless.core.errors import BlockedURL, FetchFailed
from unjobless.core.logging import get_logger

log = get_logger(__name__)

BLOCKED_SUFFIXES = (".localhost", ".local", ".internal", ".home.arpa", ".lan", ".intranet", ".corp")
BLOCKED_HOSTS = {"localhost", "metadata.google.internal", "metadata", "instance-data"}
DEFAULT_CONTENT_TYPES = (
    "text/html",
    "application/xhtml+xml",
    "text/plain",
    "application/json",
    "application/ld+json",
    "application/xml",
    "text/xml",
    "application/rss+xml",
    "application/atom+xml",
)
REDIRECT_CODES = {301, 302, 303, 307, 308}

Resolver = Callable[[str, int], list[str]]


def system_resolver(host: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return sorted({str(info[4][0]) for info in infos})


def ip_is_public(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip.split("%")[0])
    except ValueError:
        return False
    if isinstance(addr, ipaddress.IPv6Address):
        for embedded in (addr.ipv4_mapped, addr.sixtofour, addr.teredo[1] if addr.teredo else None):
            if embedded is not None and not ip_is_public(str(embedded)):
                return False
        if addr in ipaddress.ip_network("64:ff9b::/96"):  # NAT64 well-known prefix
            return ip_is_public(str(ipaddress.IPv4Address(int(addr) & 0xFFFFFFFF)))
    return bool(
        addr.is_global
        and not addr.is_multicast
        and not addr.is_private
        and not addr.is_loopback
        and not addr.is_link_local
        and not addr.is_reserved
        and not addr.is_unspecified
    )


@dataclass
class ValidatedTarget:
    url: str
    scheme: str
    host: str
    port: int
    ips: list[str]


def validate_url(
    url: str, *, resolver: Resolver | None = None, allowed_ports: Iterable[int] | None = None
) -> ValidatedTarget:
    """Static + DNS validation. Raises BlockedURL with a user-presentable reason."""
    if not isinstance(url, str) or len(url) > 2048:
        raise BlockedURL("URL is missing or too long.", code="invalid_url")
    try:
        parts = urlsplit(url.strip())
        port_raw = parts.port
    except ValueError as exc:
        raise BlockedURL("URL could not be parsed.", code="invalid_url") from exc
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise BlockedURL("Only http and https URLs are allowed.", code="scheme_not_allowed")
    if parts.username or parts.password or "@" in parts.netloc:
        raise BlockedURL("URLs with embedded credentials are not allowed.", code="credentials_in_url")
    host = (parts.hostname or "").lower().rstrip(".")
    if not host:
        raise BlockedURL("URL has no host.", code="invalid_url")
    port = port_raw or (443 if scheme == "https" else 80)
    ports = set(allowed_ports if allowed_ports is not None else get_settings().fetch_allowed_ports)
    if port not in ports:
        raise BlockedURL(f"Port {port} is not allowed.", code="port_not_allowed")

    try:
        literal = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        literal = None
    if literal is not None:
        if not ip_is_public(str(literal)):
            raise BlockedURL("This address points to a private or reserved network.", code="private_address")
        return ValidatedTarget(url, scheme, host, port, [str(literal)])

    if host in BLOCKED_HOSTS or host.endswith(BLOCKED_SUFFIXES) or "." not in host:
        raise BlockedURL("This host name refers to a local or internal network.", code="internal_host")
    if any(c for c in host if not (c.isalnum() or c in "-.")):
        raise BlockedURL("Host name contains invalid characters.", code="invalid_url")
    if not resolve:  # static checks only (used for instant feedback; DNS is re-checked at fetch time)
        return ValidatedTarget(url, scheme, host, port, [])
    try:
        ips = (resolver or system_resolver)(host, port)
    except (OSError, UnicodeError) as exc:
        raise BlockedURL("The host name could not be resolved.", code="dns_failed") from exc
    if not ips:
        raise BlockedURL("The host name could not be resolved.", code="dns_failed")
    bad = [ip for ip in ips if not ip_is_public(ip)]
    if bad:
        raise BlockedURL(
            "This host resolves to a private or reserved network address.", code="private_address"
        )
    return ValidatedTarget(url, scheme, host, port, ips)


@dataclass
class FetchResult:
    url: str  # final URL after redirects
    requested_url: str
    status_code: int
    content_type: str
    charset: str | None
    body: bytes
    truncated: bool
    redirects: list[str] = field(default_factory=list)
    headers: dict[str, str] = field(default_factory=dict)  # allowlisted, non-sensitive headers only
    elapsed_ms: int = 0

    @property
    def text(self) -> str:
        return self.body.decode(self.charset or "utf-8", errors="replace")


SAFE_RESPONSE_HEADERS = {"etag", "last-modified", "content-language", "retry-after", "x-robots-tag", "link"}


class SafeFetcher:
    def __init__(
        self,
        *,
        resolver: Resolver | None = None,
        transport: httpx.BaseTransport | None = None,
        max_bytes: int | None = None,
        max_redirects: int | None = None,
        user_agent: str | None = None,
        allowed_ports: Iterable[int] | None = None,
        on_event: Callable[[str, str | None, str, int | None], None] | None = None,
    ):
        s = get_settings()
        self.resolver = resolver or system_resolver
        self.max_bytes = max_bytes or s.fetch_max_bytes
        self.max_redirects = s.fetch_max_redirects if max_redirects is None else max_redirects
        self.user_agent = user_agent or s.user_agent
        self.allowed_ports = list(allowed_ports) if allowed_ports is not None else s.fetch_allowed_ports
        self.timeout = httpx.Timeout(s.fetch_read_timeout, connect=s.fetch_connect_timeout)
        self.total_timeout = s.fetch_total_timeout
        self.on_event = on_event
        self._client = httpx.Client(
            transport=transport,
            timeout=self.timeout,
            follow_redirects=False,
            trust_env=False,  # never pick up proxy env vars or netrc credentials
            headers={"User-Agent": self.user_agent, "Accept-Encoding": "gzip, deflate"},
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> SafeFetcher:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _event(self, outcome: str, host: str | None, reason: str, status: int | None = None) -> None:
        log.info("fetch_event", outcome=outcome, host=host, reason=reason, status=status)
        if self.on_event:
            self.on_event(outcome, host, reason, status)

    def get(
        self,
        url: str,
        *,
        accept: str = "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.5",
        content_types: Iterable[str] = DEFAULT_CONTENT_TYPES,
        extra_headers: dict[str, str] | None = None,
        max_bytes: int | None = None,
    ) -> FetchResult:
        allowed_types = tuple(content_types)
        cap = max_bytes or self.max_bytes
        started = time.monotonic()
        current = url
        redirects: list[str] = []
        safe_extra = {
            k: v
            for k, v in (extra_headers or {}).items()
            if k.lower() in {"if-none-match", "if-modified-since", "accept-language"}
        }
        for _hop in range(self.max_redirects + 1):
            try:
                target = validate_url(current, resolver=self.resolver, allowed_ports=self.allowed_ports)
            except BlockedURL as exc:
                self._event("blocked", urlsplit(current).hostname, exc.code)
                raise
            pinned_ip = target.ips[0]
            parts = urlsplit(current)
            ip_host = f"[{pinned_ip}]" if ":" in pinned_ip else pinned_ip
            default_port = 443 if target.scheme == "https" else 80
            netloc = ip_host if target.port == default_port else f"{ip_host}:{target.port}"
            pinned_url = urlunsplit((target.scheme, netloc, parts.path or "/", parts.query, ""))
            host_header = target.host if target.port == default_port else f"{target.host}:{target.port}"
            headers = {"Host": host_header, "Accept": accept, **safe_extra}
            extensions = {"sni_hostname": target.host} if target.scheme == "https" else {}
            remaining = self.total_timeout - (time.monotonic() - started)
            if remaining <= 0:
                self._event("timeout", target.host, "total_timeout")
                raise FetchFailed("The page took too long to respond.", code="timeout")
            try:
                req = self._client.build_request("GET", pinned_url, headers=headers, extensions=extensions)
                resp = self._client.send(req, stream=True)
            except httpx.TimeoutException as exc:
                self._event("timeout", target.host, "timeout")
                raise FetchFailed("The page took too long to respond.", code="timeout") from exc
            except httpx.HTTPError as exc:
                self._event("error", target.host, type(exc).__name__)
                raise FetchFailed("Could not connect to the site.", code="connect_failed") from exc
            try:
                if resp.status_code in REDIRECT_CODES:
                    loc = resp.headers.get("location")
                    if not loc:
                        raise FetchFailed("Redirect without a location.", code="bad_redirect")
                    nxt = urljoin(current, loc)
                    redirects.append(nxt)
                    current = nxt
                    continue
                ctype_full = resp.headers.get("content-type", "")
                ctype = ctype_full.split(";")[0].strip().lower()
                charset = resp.charset_encoding
                if resp.status_code < 400 and ctype and not _type_allowed(ctype, allowed_types):
                    self._event("blocked", target.host, f"content_type:{ctype}", resp.status_code)
                    raise BlockedURL(f"Unsupported content type: {ctype}.", code="content_type_not_allowed")
                declared = resp.headers.get("content-length")
                if declared and declared.isdigit() and int(declared) > cap * 4:
                    self._event("blocked", target.host, "too_large", resp.status_code)
                    raise BlockedURL("The response is too large to import.", code="too_large")
                body = bytearray()
                truncated = False
                for chunk in resp.iter_bytes():
                    body.extend(chunk)
                    if len(body) > cap:
                        del body[cap:]
                        truncated = True
                        break
                    if time.monotonic() - started > self.total_timeout:
                        raise FetchFailed("The page took too long to respond.", code="timeout")
                result = FetchResult(
                    url=current,
                    requested_url=url,
                    status_code=resp.status_code,
                    content_type=ctype or "application/octet-stream",
                    charset=charset,
                    body=bytes(body),
                    truncated=truncated,
                    redirects=redirects,
                    headers={
                        k.lower(): v for k, v in resp.headers.items() if k.lower() in SAFE_RESPONSE_HEADERS
                    },
                    elapsed_ms=int((time.monotonic() - started) * 1000),
                )
                if resp.status_code >= 400:
                    self._event("http_error", target.host, f"status_{resp.status_code}", resp.status_code)
                return result
            finally:
                resp.close()
        self._event("blocked", urlsplit(current).hostname, "too_many_redirects")
        raise BlockedURL("Too many redirects.", code="too_many_redirects")


def _type_allowed(ctype: str, allowed: tuple[str, ...]) -> bool:
    for a in allowed:
        if a.endswith("/*") and ctype.startswith(a[:-1]):
            return True
        if ctype == a:
            return True
    return False
