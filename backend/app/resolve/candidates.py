"""Candidate places from the local geocoder, OpenStreetMap and venue websites."""
import math
import re
from dataclasses import dataclass, field
from datetime import timedelta

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.discover.base import USER_AGENT
from app.net import cached_json

OVERPASS = "https://overpass-api.de/api/interpreter"
# A named thing people visit, versus roads, boundaries and buildings
POI_KEYS = {"amenity", "leisure", "tourism", "shop", "craft", "club", "historic", "natural", "office", "sport"}
AREA_TYPES = {"city", "district", "locality", "county", "state", "country", "suburb", "neighbourhood"}


@dataclass
class Candidate:
    provider: str  # photon, address, pin, website
    name: str
    lat: float
    lon: float
    address_text: str | None = None
    osm_type: str | None = None  # N, W, R
    osm_id: int | None = None
    osm_key: str | None = None
    osm_value: str | None = None
    city: str | None = None
    kind: str = "poi"  # poi, address, area
    extra: dict = field(default_factory=dict)  # website, opening_hours, phone ... from enrichment
    score: float = 0.0
    why: dict = field(default_factory=dict)

    def as_payload(self) -> dict:
        return {k: getattr(self, k) for k in ("provider", "name", "lat", "lon", "address_text", "osm_type",
                                               "osm_id", "osm_key", "osm_value", "city", "kind", "extra", "why")}


def km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _client() -> httpx.Client:
    return httpx.Client(timeout=15, headers={"User-Agent": USER_AGENT})


def _address(p: dict) -> str | None:
    street = " ".join(x for x in (p.get("housenumber"), p.get("street")) if x)
    parts = [street, p.get("city") or p.get("district"),
             " ".join(x for x in (p.get("state"), p.get("postcode")) if x)]
    s = ", ".join(x for x in parts if x)
    return s or None


def from_photon(feature: dict) -> Candidate:
    p = feature["properties"]
    lon, lat = feature["geometry"]["coordinates"]
    ptype = (p.get("type") or "").lower()
    if p.get("osm_key") in POI_KEYS or (p.get("name") and ptype == "house" and p.get("osm_key") not in ("place", "highway")):
        kind = "poi"
    elif ptype in AREA_TYPES or p.get("osm_key") in ("place", "boundary"):
        kind = "area"
    else:
        kind = "address"
    street = " ".join(x for x in (p.get("housenumber"), p.get("street")) if x)
    return Candidate(provider="photon", name=p.get("name") or street or "", lat=lat, lon=lon,
                     address_text=_address(p), osm_type=p.get("osm_type"), osm_id=p.get("osm_id"),
                     osm_key=p.get("osm_key"), osm_value=p.get("osm_value"),
                     city=p.get("city") or p.get("district") or p.get("county"), kind=kind)


def photon_search(db: Session | None, q: str, lat: float, lon: float, *, limit: int = 8,
                  bias: float = 0.3, zoom: int = 12) -> list[Candidate]:
    """Free-text search, biased toward (lat, lon). The geocoder is ours, so no rate limit."""
    s = get_settings()
    params = {"q": q, "lat": round(lat, 4), "lon": round(lon, 4), "limit": limit, "lang": "en",
              "location_bias_scale": bias, "zoom": zoom}
    with _client() as c:
        data = cached_json(db, c, f"{s.photon_url}/api", params, timedelta(days=30))
    return [from_photon(f) for f in data.get("features", [])]


def overpass_tags(db: Session | None, osm_type: str, osm_id: int) -> dict:
    """OSM tags for one element (hours, website, phone, cuisine). Cached 30 days: public server."""
    kind = {"N": "node", "W": "way", "R": "relation"}.get(osm_type)
    if not kind:
        return {}
    q = f"[out:json][timeout:15];{kind}({int(osm_id)});out tags;"
    try:
        with _client() as c:
            data = cached_json(db, c, OVERPASS, {"data": q}, timedelta(days=30))
    except (httpx.HTTPError, ValueError):
        return {}
    els = data.get("elements") or []
    return els[0].get("tags", {}) if els else {}


def enrich(db: Session | None, cand: Candidate) -> Candidate:
    if cand.osm_type and cand.osm_id and not cand.extra:
        t = overpass_tags(db, cand.osm_type, cand.osm_id)
        cand.extra = {k: v for k, v in {
            "website": t.get("website") or t.get("contact:website") or t.get("url"),
            "phone": t.get("phone") or t.get("contact:phone"),
            "opening_hours": t.get("opening_hours"),
            "cuisine": t.get("cuisine"),
            "instagram": t.get("contact:instagram"),
        }.items() if v}
    return cand


AGGREGATORS = re.compile(
    r"(yelp|tripadvisor|opentable|resy|tock|instagram|facebook|tiktok|google|apple|timeout|eater|"
    r"theinfatuation|infatuation|reddit|wikipedia|youtube|x\.com|twitter|ubereats|doordash|grubhub|"
    r"postmates|seamless|foursquare|mapquest|yellowpages|zomato|thrillist|lamag|laist|discoverlosangeles|"
    r"secretlosangeles|eventbrite|groupon|linkedin|pinterest|bing|duckduckgo|threads)\.", re.I)
US_ADDRESS = re.compile(
    r"\b(\d{2,6}\s+(?:[NSEW]\.?\s+)?[A-Z0-9][\w.'-]*(?:\s+[A-Z0-9][\w.'-]*){0,4}\s+"
    r"(?:St|Street|Ave|Avenue|Blvd|Boulevard|Rd|Road|Dr|Drive|Way|Pl|Place|Ln|Lane|Ct|Court|Pkwy|Hwy|Highway)\.?"
    r"(?:\s*(?:#|Ste\.?|Suite|Unit)\s*\w+)?(?:,\s*[A-Z][\w .'-]+){0,2},?\s*(?:CA|California)\.?\s*(?:9\d{4})?)")


def searx(db: Session | None, q: str) -> list[dict]:
    s = get_settings()
    try:
        with _client() as c:
            data = cached_json(db, c, f"{s.searxng_url}/search", {"q": q, "format": "json"}, timedelta(days=7))
    except (httpx.HTTPError, ValueError):
        return []
    return data.get("results", [])[:12]


def official_sites(results: list[dict]) -> list[str]:
    return [r["url"] for r in results if r.get("url") and not AGGREGATORS.search(r["url"])][:2]


def snippet_addresses(results: list[dict]) -> list[str]:
    out: list[str] = []
    for r in results:
        for m in US_ADDRESS.findall(f"{r.get('title', '')} {r.get('content', '')}"):
            m = re.sub(r"\s+", " ", m).strip(" ,")
            if m not in out:
                out.append(m)
    return out[:3]
