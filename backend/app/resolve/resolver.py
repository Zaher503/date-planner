"""ItemHint -> the real place on the map, plus ranked alternatives for the review picker.

Order of evidence: an exact pin (maps link, JSON-LD geo), then a stated street address,
then a name search near home, then the venue's own website found through SearXNG.
"""
import logging
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


def _geocode_address(db: Session | None, address: str, home: tuple[float, float]) -> Candidate | None:
    for c in cands.photon_search(db, address, *home, limit=3, bias=0.2):
        if c.kind in ("address", "poi") and c.address_text:
            c.provider, c.kind = "address", "address"
            return c
    return None


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
                c = _geocode_address(db, item.address, home)
                if not c:
                    continue
                c.provider, c.name, c.kind = "website", item.name, "poi"
            c.extra = {k: v for k, v in {"website": final, "opening_hours": item.opening_hours,
                                         "phone": item.phone, "price_level": item.price_level}.items() if v}
            found.append(c)
            break
    for addr in cands.snippet_addresses(results):
        c = _geocode_address(db, addr, home)
        if c:
            c.provider, c.name = "snippet", hint.name
            found.append(c)
    return found


def resolve(db: Session | None, hint: ItemHint, home: tuple[float, float]) -> Resolution:
    found: list[Candidate] = []
    method = "name"

    if hint.lat is not None and hint.exact_pin:
        method = "pin"
        poi = _poi_near(db, hint.name, hint.lat, hint.lon) if hint.name else None
        found.append(poi or Candidate(provider="pin", name=hint.name, lat=hint.lat, lon=hint.lon,
                                      address_text=hint.address, kind="poi"))
    elif hint.address:
        method = "address"
        addr = _geocode_address(db, f"{hint.address}" if "," in hint.address else f"{hint.address}, {hint.area or REGION}", home)
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
    ranked = sorted((score(c, hint, home) for c in found), key=lambda c: c.score, reverse=True)

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
