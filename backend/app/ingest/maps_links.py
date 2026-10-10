"""Google and Apple Maps share links -> name, address and coordinates, from the URL alone.

Short links (maps.app.goo.gl, maps.apple/p/...) are expanded by following redirects;
the place details are then read from the long URL, so no map page is loaded.
"""
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, unquote_plus, urlsplit

from app.net import resolve_redirects

LATLON = re.compile(r"^\s*(-?\d{1,2}\.\d+)\s*,\s*(-?\d{1,3}\.\d+)\s*$")
PIN = re.compile(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)")
VIEWPORT = re.compile(r"/@(-?\d+\.\d+),(-?\d+\.\d+)")
SHORT_HOSTS = ("maps.app.goo.gl", "goo.gl", "g.co", "maps.apple")


@dataclass
class MapsHint:
    name: str | None = None
    address: str | None = None
    lat: float | None = None
    lon: float | None = None
    exact_pin: bool = False  # coordinates are the place itself, not a map viewport

    @property
    def usable(self) -> bool:
        return bool(self.name or self.address or self.lat is not None)


def _latlon(s: str | None) -> tuple[float, float] | None:
    m = LATLON.match(s or "")
    if m:
        lat, lon = float(m.group(1)), float(m.group(2))
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            return lat, lon
    return None


def _split_name_address(q: str) -> tuple[str | None, str | None]:
    """'Bestia, 2121 E 7th Pl, Los Angeles, CA' -> ('Bestia', '2121 E 7th Pl, Los Angeles, CA')."""
    parts = [p.strip() for p in q.split(",") if p.strip()]
    if len(parts) >= 2 and not re.match(r"^\d", parts[0]) and re.match(r"^\d", parts[1]):
        return parts[0], ", ".join(parts[1:])
    if parts and re.match(r"^\d+\s+\w", parts[0]):
        return None, ", ".join(parts)
    return q.strip() or None, None


def parse_google(url: str) -> MapsHint:
    p = urlsplit(url)
    path = unquote_plus(p.path)
    qs = {k: v[0] for k, v in parse_qs(p.query).items()}
    hint = MapsHint()

    m = re.search(r"/maps/place/([^/]+)", path)
    if m:
        name, addr = _split_name_address(m.group(1))
        coords = _latlon(m.group(1))
        if coords:
            hint.lat, hint.lon, hint.exact_pin = *coords, True
        else:
            hint.name, hint.address = name, addr
    for key in ("q", "query", "destination"):
        if qs.get(key) and not (hint.name or hint.address):
            coords = _latlon(qs[key])
            if coords:
                hint.lat, hint.lon, hint.exact_pin = *coords, True
            else:
                hint.name, hint.address = _split_name_address(qs[key])
    if hint.lat is None:
        m = PIN.search(url)
        if m:
            hint.lat, hint.lon, hint.exact_pin = float(m.group(1)), float(m.group(2)), True
    if hint.lat is None:
        m = VIEWPORT.search(path) or VIEWPORT.search(url)
        if m:
            hint.lat, hint.lon = float(m.group(1)), float(m.group(2))
        elif coords := _latlon(qs.get("ll")):
            hint.lat, hint.lon = coords
    return hint


def parse_apple(url: str) -> MapsHint:
    qs = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
    hint = MapsHint(name=qs.get("name") or qs.get("q"), address=qs.get("address"))
    coords = _latlon(qs.get("coordinate")) or _latlon(qs.get("ll")) or _latlon(qs.get("sll"))
    if coords:
        hint.lat, hint.lon = coords
        hint.exact_pin = bool(qs.get("coordinate") or qs.get("ll"))
    if hint.name and _latlon(hint.name):
        hint.name = None
    if hint.name and hint.address and hint.name.strip() == hint.address.strip():
        hint.name = None
    return hint


def parse(url: str) -> MapsHint:
    host = (urlsplit(url).hostname or "").lower()
    if "apple" in host:
        return parse_apple(url)
    return parse_google(url)


def expand_and_parse(url: str) -> tuple[str, MapsHint]:
    host = (urlsplit(url).hostname or "").lower()
    final = resolve_redirects(url) if any(host == h or host.endswith("." + h) for h in SHORT_HOSTS) else url
    return final, parse(final)
