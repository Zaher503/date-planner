"""Find, normalize and classify shared links. Pure functions, no network."""
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

URL_RE = re.compile(r"https?://[^\s<>\"'()\[\]{}]+", re.I)
TRAILING = ".,;:!?)]}'\""

# Query parameters that never change what a link points to
TRACKING = re.compile(
    r"^(utm_.*|fbclid|gclid|dclid|msclkid|igshid|igsh|si|_r|_t|is_from_webapp|sender_device|"
    r"sender_web_id|share_.*|tt_from|u_code|checksum|sec_user_id|ref|ref_src|mc_.*|t|"
    r"entry|g_ep|g_st|pli|hl|gl|aff|aff_.*)$", re.I)

# Hosts where some of the "tracking" names above are meaningful and must stay
KEEP_PARAMS = {
    "maps.apple.com": {"q", "ll", "address", "sll", "z", "t", "auid", "place-id", "name"},
    "www.google.com": {"q", "query", "cid", "ftid", "api", "query_place_id"},
    "google.com": {"q", "query", "cid", "ftid", "api", "query_place_id"},
    "maps.google.com": {"q", "query", "cid", "ftid", "ll"},
    "www.youtube.com": {"v"},
    "youtube.com": {"v"},
    "m.youtube.com": {"v"},
}

KINDS = (
    ("tiktok", ("tiktok.com",)),
    ("youtube", ("youtube.com", "youtu.be")),
    ("gmaps", ("maps.app.goo.gl", "goo.gl", "maps.google.com", "g.co")),
    ("applemaps", ("maps.apple.com", "maps.apple")),
    ("instagram", ("instagram.com", "instagr.am")),
)


def first_url(text: str) -> str | None:
    m = URL_RE.search(text or "")
    return m.group(0).rstrip(TRAILING) if m else None


def _host_is(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)


def classify(url: str) -> str:
    p = urlsplit(url)
    host = (p.hostname or "").lower()
    if _host_is(host, "google.com") and p.path.startswith("/maps"):
        return "gmaps"
    for kind, domains in KINDS:
        if any(_host_is(host, d) for d in domains):
            return kind
    return "event_page"


def normalize(url: str) -> str:
    """Stable form used for duplicate detection."""
    p = urlsplit(url.strip())
    scheme = "https" if p.scheme in ("http", "https") else p.scheme
    host = (p.hostname or "").lower()
    if p.port and p.port not in (80, 443):
        host = f"{host}:{p.port}"
    keep = KEEP_PARAMS.get(host, set())
    query = sorted((k, v) for k, v in parse_qsl(p.query, keep_blank_values=False)
                   if k in keep or not TRACKING.match(k))
    path = re.sub(r"/{2,}", "/", p.path) or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    # TikTok: the canonical form is the bare video path
    if _host_is(host, "tiktok.com"):
        host = "www.tiktok.com" if host in ("tiktok.com", "m.tiktok.com") else host
        query = []
    return urlunsplit((scheme, host, path, urlencode(query), ""))


# Share links that redirect to the real page; each share gets a fresh code
SHORT_HOSTS = ("vm.tiktok.com", "vt.tiktok.com", "youtu.be", "maps.app.goo.gl", "goo.gl", "g.co")
TIKTOK_VIDEO_RE = re.compile(r"/video/(\d+)")


def is_short_link(url: str) -> bool:
    p = urlsplit(url)
    host = (p.hostname or "").lower()
    if _host_is(host, "tiktok.com") and p.path.startswith("/t/"):
        return True
    return any(_host_is(host, h) for h in SHORT_HOSTS)


def identity_of(url: str) -> str | None:
    """Stable id of the page a link points to (None when the link does not carry one)."""
    p = urlsplit(url)
    host = (p.hostname or "").lower()
    if _host_is(host, "tiktok.com"):
        m = TIKTOK_VIDEO_RE.search(p.path)
        return f"tiktok:{m.group(1)}" if m else None
    return normalize(url)
