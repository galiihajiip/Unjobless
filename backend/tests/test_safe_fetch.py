"""SSRF and fetch-safety tests. No live network: DNS and HTTP are faked."""

import gzip

import httpx
import pytest

from unjobless.core.errors import BlockedURL, FetchFailed
from unjobless.fetch.safe_fetch import SafeFetcher, ip_is_public, validate_url

PUBLIC = "93.184.215.14"


def resolver_map(mapping):
    def resolve(host, port):
        if host not in mapping:
            raise OSError("NXDOMAIN")
        v = mapping[host]
        return v if isinstance(v, list) else [v]

    return resolve


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1", "10.0.0.5", "172.16.3.4", "192.168.1.1", "169.254.169.254", "100.64.0.1", "100.100.100.200",
        "0.0.0.0", "224.0.0.1", "240.0.0.1", "255.255.255.255", "::1", "fe80::1", "fd00:ec2::254", "fc00::1",
        "::ffff:127.0.0.1", "::ffff:10.0.0.1", "2002:7f00:1::", "64:ff9b::a00:1", "198.18.0.1",
    ],
)
def test_non_public_ips_rejected(ip):
    assert ip_is_public(ip) is False


@pytest.mark.parametrize("ip", ["93.184.215.14", "1.1.1.1", "2606:4700:4700::1111"])
def test_public_ips_allowed(ip):
    assert ip_is_public(ip) is True


@pytest.mark.parametrize(
    "url,code",
    [
        ("ftp://example.com/x", "scheme_not_allowed"),
        ("file:///etc/passwd", "scheme_not_allowed"),
        ("gopher://example.com", "scheme_not_allowed"),
        ("javascript:alert(1)", "scheme_not_allowed"),
        ("http://user:pass@example.com/", "credentials_in_url"),
        ("http://127.0.0.1/", "private_address"),
        ("http://[::1]/", "private_address"),
        ("http://169.254.169.254/latest/meta-data/", "private_address"),
        ("http://localhost/", "internal_host"),
        ("http://db/", "internal_host"),
        ("http://redis:6379/", "port_not_allowed"),
        ("http://api.internal/", "internal_host"),
        ("http://printer.local/", "internal_host"),
        ("http://example.com:8080/", "port_not_allowed"),
        ("http://example.com:22/", "port_not_allowed"),
        ("http://2130706433/", "internal_host"),
    ],
)
def test_static_url_rejections(url, code):
    with pytest.raises(BlockedURL) as e:
        validate_url(url, resolver=resolver_map({"example.com": PUBLIC}), allowed_ports=[80, 443])
    assert e.value.code == code


def test_dns_resolving_to_private_is_blocked():
    with pytest.raises(BlockedURL) as e:
        validate_url("https://evil.example/", resolver=resolver_map({"evil.example": ["93.184.215.14", "10.0.0.1"]}), allowed_ports=[443])
    assert e.value.code == "private_address"


def test_unresolvable_host_blocked():
    with pytest.raises(BlockedURL) as e:
        validate_url("https://nope.example/", resolver=resolver_map({}), allowed_ports=[443])
    assert e.value.code == "dns_failed"


def make_fetcher(handler, mapping=None, **kw):
    return SafeFetcher(resolver=resolver_map(mapping or {"jobs.example": PUBLIC}), transport=httpx.MockTransport(handler), **kw)


def test_connects_to_pinned_ip_with_host_header():
    seen = {}

    def handler(request):
        seen["host"] = request.url.host
        seen["host_header"] = request.headers["host"]
        seen["cookie"] = request.headers.get("cookie")
        return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, text="<h1>Hi</h1>")

    with make_fetcher(handler) as f:
        r = f.get("https://jobs.example/post/1")
    assert seen == {"host": PUBLIC, "host_header": "jobs.example", "cookie": None}
    assert r.text == "<h1>Hi</h1>"
    assert r.url == "https://jobs.example/post/1"


def test_redirect_to_private_ip_is_blocked():
    def handler(request):
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data/"})

    with make_fetcher(handler) as f, pytest.raises(BlockedURL) as e:
        f.get("https://jobs.example/r")
    assert e.value.code == "private_address"


def test_redirect_to_internal_hostname_is_blocked():
    def handler(request):
        return httpx.Response(301, headers={"location": "http://db:5432/"})

    with make_fetcher(handler) as f, pytest.raises(BlockedURL):
        f.get("https://jobs.example/r")


def test_dns_rebinding_between_hops_is_revalidated():
    """First resolution is public, the redirect target's host resolves to loopback."""

    def handler(request):
        if request.headers["host"] == "jobs.example":
            return httpx.Response(302, headers={"location": "https://rebind.example/x"})
        return httpx.Response(200, text="should never be reached")

    with make_fetcher(handler, {"jobs.example": PUBLIC, "rebind.example": "127.0.0.1"}) as f, pytest.raises(BlockedURL):
        f.get("https://jobs.example/start")


def test_too_many_redirects():
    def handler(request):
        return httpx.Response(302, headers={"location": "https://jobs.example/loop"})

    with make_fetcher(handler, max_redirects=3) as f, pytest.raises(BlockedURL) as e:
        f.get("https://jobs.example/loop")
    assert e.value.code == "too_many_redirects"


def test_body_capped_and_flagged_truncated():
    def handler(request):
        return httpx.Response(200, headers={"content-type": "text/plain"}, content=b"a" * 10_000)

    with make_fetcher(handler, max_bytes=1000) as f:
        r = f.get("https://jobs.example/big")
    assert len(r.body) == 1000 and r.truncated


def test_decompression_bomb_capped():
    bomb = gzip.compress(b"0" * 5_000_000)

    def handler(request):
        return httpx.Response(200, headers={"content-type": "text/plain", "content-encoding": "gzip"}, content=bomb)

    with make_fetcher(handler, max_bytes=10_000) as f:
        r = f.get("https://jobs.example/bomb")
    assert len(r.body) == 10_000 and r.truncated


def test_unsafe_content_type_rejected():
    def handler(request):
        return httpx.Response(200, headers={"content-type": "application/x-msdownload"}, content=b"MZ")

    with make_fetcher(handler) as f, pytest.raises(BlockedURL) as e:
        f.get("https://jobs.example/setup.exe")
    assert e.value.code == "content_type_not_allowed"


def test_timeout_reported():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    with make_fetcher(handler) as f, pytest.raises(FetchFailed) as e:
        f.get("https://jobs.example/slow")
    assert e.value.code == "timeout"


def test_sensitive_request_headers_not_forwarded():
    seen = {}

    def handler(request):
        seen.update(request.headers)
        return httpx.Response(200, headers={"content-type": "text/html", "set-cookie": "a=b"}, text="ok")

    with make_fetcher(handler) as f:
        r = f.get("https://jobs.example/", extra_headers={"Authorization": "Bearer x", "Cookie": "s=1", "If-None-Match": "abc"})
    assert "authorization" not in seen and "cookie" not in seen
    assert seen["if-none-match"] == "abc"
    assert "set-cookie" not in r.headers


def test_blocked_events_reported_without_query_string():
    events = []

    def handler(request):
        return httpx.Response(200, text="x")

    f = SafeFetcher(resolver=resolver_map({}), transport=httpx.MockTransport(handler), on_event=lambda *a: events.append(a))
    with pytest.raises(BlockedURL):
        f.get("http://127.0.0.1/admin?token=secret")
    assert events and "secret" not in repr(events)
