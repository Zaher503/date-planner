"""Outbound HTTP for user-supplied links.

Every request, including each redirect hop, is checked so a shared link can never
reach the LAN or the stack's internal services (SSRF). Third-party API responses
can be cached in http_cache to keep request counts low on free public services.
"""
import hashlib
import ipaddress
import json
import logging
import socket
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

import httpx
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import HttpCache

BROWSER_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/126.0 Safari/537.36")
MAX_BYTES = 8_000_000
log = logging.getLogger(__name__)


class BlockedURL(ValueError):
    pass


def check_url(url: str) -> str:
    """Reject non-http(s) links and anything that resolves to a private address."""
    p = urlsplit(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise BlockedURL("only http(s) links are accepted")
    try:
        infos = socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == "https" else 80))
    except socket.gaierror as e:
        raise BlockedURL(f"cannot resolve {p.hostname}") from e
    for *_, sa in infos:
        ip = ipaddress.ip_address(sa[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise BlockedURL("link resolves to a private address")
    return url


def _guard(request: httpx.Request) -> None:
    check_url(str(request.url))


def public_client(timeout: float = 20, browser: bool = True) -> httpx.Client:
    """Client for arbitrary public URLs (shared links, venue sites)."""
    headers = {"Accept-Language": "en-US,en;q=0.9"}
    if browser:
        headers["User-Agent"] = BROWSER_UA
    return httpx.Client(timeout=timeout, follow_redirects=True, max_redirects=8, headers=headers,
                        event_hooks={"request": [_guard]})


BLOCKED_STATUS = {403, 429, 503}


def _fetch_impersonated(url: str) -> tuple[str, str]:
    """Second try for sites that turn away plain HTTP clients by their TLS fingerprint: curl_cffi
    speaks TLS and HTTP/2 like Chrome. Redirects are followed by hand so each hop is checked."""
    from curl_cffi import requests as cr

    for _ in range(8):
        check_url(url)
        r = cr.get(url, impersonate="chrome", timeout=25, allow_redirects=False, headers={"Accept-Language": "en-US,en;q=0.9"})
        if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
            url = str(httpx.URL(url).join(r.headers["location"]))
            continue
        if r.status_code >= 400:
            raise httpx.HTTPStatusError(f"HTTP {r.status_code}", request=httpx.Request("GET", url),
                                        response=httpx.Response(r.status_code))
        return url, r.content[:MAX_BYTES].decode(r.encoding or "utf-8", "replace")
    raise httpx.TooManyRedirects("too many redirects")


def fetch_text(url: str, client: httpx.Client | None = None) -> tuple[str, str]:
    """GET a public page, retrying as a Chrome look-alike when the site refuses the plain client.
    Returns (final_url, text). Raises httpx errors on failure."""
    try:
        return _fetch_plain(url, client)
    except httpx.HTTPStatusError as e:
        if e.response.status_code not in BLOCKED_STATUS:
            raise
    except (httpx.TimeoutException, httpx.ConnectError):
        pass
    try:
        return _fetch_impersonated(url)
    except ImportError:
        pass
    except httpx.HTTPError as e:
        if not _is_block(e):
            raise
        return _fetch_browser(url, e)
    return _fetch_plain(url, client)


def _is_block(e: httpx.HTTPError) -> bool:
    return isinstance(e, (httpx.TimeoutException, httpx.ConnectError)) or (
        isinstance(e, httpx.HTTPStatusError) and e.response.status_code in BLOCKED_STATUS)


def _fetch_browser(url: str, original: httpx.HTTPError) -> tuple[str, str]:
    """Last resort: render the page in a real browser, when one is configured."""
    from app import browser

    if not browser.available():
        raise original
    try:
        return browser.render(url)
    except Exception as e:  # unreachable browser, bot check, timeout: report the original refusal
        log.info("browser fetch of %s failed: %s", url, e)
        raise original from None


def _fetch_plain(url: str, client: httpx.Client | None = None) -> tuple[str, str]:
    own = client is None
    client = client or public_client()
    try:
        with client.stream("GET", url) as r:
            r.raise_for_status()
            chunks, size = [], 0
            for chunk in r.iter_bytes():
                chunks.append(chunk)
                size += len(chunk)
                if size > MAX_BYTES:
                    break
            body = b"".join(chunks)
            enc = r.encoding or "utf-8"
            return str(r.url), body.decode(enc, "replace")
    finally:
        if own:
            client.close()


def resolve_redirects(url: str, timeout: float = 15) -> str:
    """Final URL after redirects, without downloading big bodies."""
    with public_client(timeout=timeout) as c:
        with c.stream("GET", url) as r:
            return str(r.url)


def _key(url: str, params: dict | None) -> str:
    raw = url + "?" + json.dumps(params or {}, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def cached_json(db: Session | None, client: httpx.Client, url: str, params: dict | None,
                ttl: timedelta) -> dict | list:
    """GET JSON through the http_cache table (internal or third-party APIs, not user links)."""
    key = _key(url, params)
    now = datetime.now(timezone.utc)
    if db is not None:
        hit = db.get(HttpCache, key)
        if hit and hit.expires_at > now:
            return json.loads(hit.body)
    r = client.get(url, params=params)
    r.raise_for_status()
    data = r.json()
    if db is not None:
        stmt = insert(HttpCache).values(key=key, url=url, status=r.status_code, body=r.content,
                                        fetched_at=now, expires_at=now + ttl)
        db.execute(stmt.on_conflict_do_update(index_elements=["key"], set_={
            "body": stmt.excluded.body, "status": stmt.excluded.status,
            "fetched_at": stmt.excluded.fetched_at, "expires_at": stmt.excluded.expires_at}))
        db.commit()
    return data
