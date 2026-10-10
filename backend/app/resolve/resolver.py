"""ItemHint -> the real place on the map, plus ranked alternatives for the review picker.

Order of evidence: an exact pin (maps link, JSON-LD geo), then a stated street address,
then a name search near home, then the venue's own website found through SearXNG.
"""
import logging
import re
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.ingest.event_page import parse_page
from app.ingest.items import ItemHint
from app.net import fetch_text
from app.resolve import candidates as cands
from app.resolve.candidates import Candidate, km
from app.resolve.scorer import AUTO_ACCEPT, name_similarity, score

log = logging.getLogger(__name__)
REGION = "Los Angeles"
SAME_SPOT_KM = 0.15


@dataclass
class Resolution:
    best: Candidate | None
    confidence: float
    method: str
    alternatives: list[Candidate] = field(default_factory=list)

    @property
    def needs_review(self) -> bool:
        return self.best is None or self.confidence < AUTO_ACCEPT


def _dedupe(found: list[Candidate]) -> list[Candidate]:
    out: list[Candidate] = []
    for c in found:
        key = (c.osm_type, c.osm_id) if c.osm_id else None
        if key and any((o.osm_type, o.osm_id) == key for o in out):
            continue
        if not key and any(km(o.lat, o.lon, c.lat, c.lon) < 0.03 and name_similarity(o.name, c.name) > 0.9 for o in out):
            continue
        out.append(c)
    return out


def _poi_near(db: Session | None, name: str, lat: float, lon: float) -> Candidate | None:
    """A named OSM place at (almost) the same spot, to attach OSM id, hours and website."""
    for c in cands.photon_search(db, name, lat, lon, limit=6, bias=0.9, zoom=17):
        if c.kind == "poi" and km(lat, lon, c.lat, c.lon) <= SAME_SPOT_KM and name_similarity(name, c.name) >= 0.7:
            return c
    return None


def _house(address: str) -> str | None:
    m = re.match(r"\s*(\d+[A-Za-z]?)\b", address)
    return m.group(1).lower() if m else None


STREET_WORDS = {"st", "street", "ave", "avenue", "blvd", "boulevard", "rd", "road", "dr", "drive", "way", "pl",
                "place", "ln", "lane", "ct", "court", "pkwy", "parkway", "hwy", "highway", "n", "s", "e", "w",
                "north", "south", "east", "west", "the"}


def _street_key(s: str | None) -> set[str]:
    words = re.findall(r"[a-z0-9]+", (s or "").lower())
    return {w for w in words if w not in STREET_WORDS and not w.isdigit()}


def _same_street(stated: str, found: str | None) -> bool:
    """'515 W 7th St' vs 'West 7th Street': same street. '1700 Lexington Rd' vs '3rd Street': not."""
    want = _street_key(re.sub(r"^\s*\d+[A-Za-z]?\s+", "", stated.split(",")[0]))
    return not want or bool(want & _street_key(found))


def _address_variants(address: str, area: str | None) -> list[str]:
    """The address as given, then with the city swapped for Los Angeles (postal city names
    like 'Beverly Hills' often differ from the real one), then with the area."""
    a = address.strip().rstrip(",")
    street = a.split(",")[0].strip()
    out = []
    if re.search(r"\b(CA|California)\b|\b9\d{4}\b", a) or a.count(",") >= 2:
        out.append(a)
    if area and not re.search(r"\b(downtown|dtla|la|los angeles)\b", area, re.I):
        out.append(f"{street}, {area}, CA")
    out.append(f"{street}, Los Angeles, CA")
    return list(dict.fromkeys(out))


def _anchor(db: Session | None, area: str | None, home: tuple[float, float]) -> tuple[float, float]:
    """Where to break ties between same-numbered addresses: the stated area, else home."""
    if area and not re.search(r"^\s*(la|los angeles|socal)\s*$", area, re.I):
        for c in cands.photon_search(db, area, *home, limit=3, bias=0.5):
            if c.kind == "area" and km(home[0], home[1], c.lat, c.lon) < 150:
                return c.lat, c.lon
    return home


def _geocode_address(db: Session | None, address: str, home: tuple[float, float],
                     area: str | None = None) -> Candidate | None:
    """Street address -> point. Exact house number from the local geocoder, else public
    Nominatim (which interpolates US house numbers), else the street alone (flagged).
    When the same address exists in several cities, the one nearest the area wins."""
    house = _house(address)
    variants = _address_variants(address, area)
    matches: list[Candidate] = []
    street_only = None
    for q in variants:
        for c in cands.photon_search(db, q, *home, limit=5, bias=0.2):
            if not c.address_text or c.kind == "area":
                continue
            c.provider, c.kind = "address", "address"
            if house and (c.housenumber or "").lower() == house and _same_street(address, c.street):
                matches.append(c)
            street_only = street_only or c
    if house and not matches:
        for q in variants[:2]:
            matches = [c for c in cands.nominatim_address(db, q)
                       if (c.housenumber or "").lower() == house and _same_street(address, c.street)]
            if matches:
                break
    if matches:
        lat, lon = _anchor(db, area, home)
        best = min(matches, key=lambda c: km(lat, lon, c.lat, c.lon))
        best.extra["house_match"] = True
        return best
    if street_only:
        street_only.extra["street_only"] = True
    return street_only


def _from_website(db: Session | None, hint: ItemHint, home: tuple[float, float]) -> list[Candidate]:
    """Find the venue's site (or an address in search snippets) and geocode what it says."""
    q = f"{hint.name} {hint.area or REGION}"
    results = cands.searx(db, q)
    found: list[Candidate] = []
    for url in cands.official_sites(results):
        try:
            final, html = fetch_text(url)
        except Exception as e:  # sites fail in many ways; this is a best-effort source
            log.info("venue site %s failed: %s", url, e)
            continue
        for item in parse_page(final, html).items:
            if item.kind != "place" or not (item.address or item.lat is not None):
                continue
            if item.lat is not None:
                c = Candidate(provider="website", name=item.name, lat=item.lat, lon=item.lon,
                              address_text=item.address, kind="poi")
            else:
                c = _geocode_address(db, item.address, home, hint.area)
                if not c or c.extra.get("street_only"):
                    continue
                c.provider, c.name, c.kind = "website", item.name, "poi"
            c.extra = {k: v for k, v in {"website": final, "opening_hours": item.opening_hours,
                                         "phone": item.phone, "price_level": item.price_level}.items() if v}
            found.append(c)
            break
    for addr in cands.snippet_addresses(results, hint.name):
        c = _geocode_address(db, addr, home, hint.area)
        if c and not c.extra.get("street_only"):
            c.provider, c.name = "snippet", hint.name
            found.append(c)
    return found


def _resolve_inside(db: Session | None, hint: ItemHint, home: tuple[float, float]) -> Resolution | None:
    """A venue inside another one: pin it where the host is, under its own name."""
    host = resolve(db, ItemHint(kind="place", name=hint.inside, area=hint.area, category=hint.category), home)
    if host.best is None or host.needs_review:
        return None
    c = host.best
    c.extra = {k: v for k, v in c.extra.items() if k in ("enriched",)}  # host's website and hours are not ours
    c.extra["inside"] = hint.inside
    c.provider, c.name, c.osm_type, c.osm_id = "inside", hint.name, None, None
    return Resolution(best=c, confidence=host.confidence, method="inside", alternatives=host.alternatives)


def resolve(db: Session | None, hint: ItemHint, home: tuple[float, float]) -> Resolution:
    found: list[Candidate] = []
    method = "name"
    addr_point: tuple[float, float] | None = None

    if hint.inside and not hint.address and hint.lat is None:
        own = resolve(db, ItemHint(kind=hint.kind, name=hint.name, area=hint.area, category=hint.category,
                                   flags=hint.flags), home)
        if own.best and not own.needs_review:
            return own  # the place is mapped on its own
        inside = _resolve_inside(db, hint, home)
        if inside:
            return inside
        return own

    if hint.lat is not None and hint.exact_pin:
        method = "pin"
        poi = _poi_near(db, hint.name, hint.lat, hint.lon) if hint.name else None
        found.append(poi or Candidate(provider="pin", name=hint.name, lat=hint.lat, lon=hint.lon,
                                      address_text=hint.address, kind="poi"))
    elif hint.address:
        method = "address"
        addr = _geocode_address(db, hint.address, home, hint.area)
        if addr and addr.extra.get("house_match"):
            addr_point = (addr.lat, addr.lon)
        if addr:
            poi = _poi_near(db, hint.name, addr.lat, addr.lon) if hint.name else None
            if poi:
                found.append(poi)
            addr.name = hint.name
            found.append(addr)

    if hint.name:
        queries = [f"{hint.name} {hint.area}" if hint.area else None, hint.name]
        for q in dict.fromkeys(q for q in queries if q):
            found += cands.photon_search(db, q, *home, limit=8)

    found = _dedupe(found)
    ranked = [score(c, hint, home) for c in found]
    if addr_point is not None:
        # A stated address that geocoded exactly outranks a same-named place across town
        for c in ranked:
            if km(addr_point[0], addr_point[1], c.lat, c.lon) > 0.3:
                c.score = round(max(0.0, c.score - 0.3), 3)
                c.why["far_from_stated_address"] = 1
    ranked.sort(key=lambda c: c.score, reverse=True)

    if hint.name and (not ranked or ranked[0].score < AUTO_ACCEPT):
        web = [score(c, hint, home) for c in _from_website(db, hint, home)]
        if web:
            # The venue's own site is strong evidence when its name matches
            for c in web:
                if c.provider == "website" and c.why.get("name", 0) >= 0.8:
                    c.score = min(1.0, c.score + 0.1)
            ranked = sorted(_dedupe(web + ranked), key=lambda c: c.score, reverse=True)
            method = "website" if ranked and ranked[0].provider in ("website", "snippet") else method

    if not ranked:
        return Resolution(best=None, confidence=0.0, method=method)
    best = cands.enrich(db, ranked[0])
    return Resolution(best=best, confidence=best.score, method=method, alternatives=ranked[1:6])
