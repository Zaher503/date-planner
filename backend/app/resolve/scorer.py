"""How well a candidate place matches what the post described. 0..1, with the reasons."""
import math
import re
import unicodedata

from rapidfuzz import fuzz

from app.ingest.items import ItemHint
from app.resolve.candidates import Candidate, km

AUTO_ACCEPT = 0.75
NEAR_KM = 40.0  # the default discovery radius; no distance penalty inside it

# OSM values that belong to our categories (used for agreement, not as a hard filter)
OSM_CATEGORY = {
    "restaurant": "restaurant", "fast_food": "restaurant", "food_court": "restaurant",
    "bar": "bar", "pub": "bar", "biergarten": "bar", "nightclub": "nightlife", "cafe": "cafe",
    "ice_cream": "dessert", "bakery": "dessert", "confectionery": "dessert", "museum": "museum",
    "gallery": "arts", "arts_centre": "arts", "theatre": "show", "cinema": "show", "park": "park",
    "garden": "park", "beach": "beach", "peak": "hike", "viewpoint": "viewpoint", "marketplace": "market",
    "music_venue": "live_music", "attraction": "activity", "theme_park": "activity", "zoo": "activity",
    "aquarium": "activity", "spa": "spa", "mall": "shopping", "nature_reserve": "outdoors",
}
FILLER = re.compile(r"\b(the|la|los angeles|bar|restaurant|cafe|rooftop|lounge|club|dtla|downtown)\b")


def norm(s: str | None) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9& ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def name_similarity(a: str | None, b: str | None) -> float:
    a, b = norm(a), norm(b)
    if not a or not b:
        return 0.0
    full = max(fuzz.token_set_ratio(a, b), fuzz.WRatio(a, b)) / 100
    core_a, core_b = FILLER.sub("", a).strip(), FILLER.sub("", b).strip()
    # "Perch Rooftop Bar" vs "Perch": the distinctive word matches exactly
    if core_a and core_b and (core_a == core_b or core_a in core_b.split() or core_b in core_a.split()):
        full = max(full, 0.92)
    return full


def score(c: Candidate, hint: ItemHint, home: tuple[float, float]) -> Candidate:
    why: dict[str, float] = {}
    sim = name_similarity(hint.name, c.name)
    if c.provider in ("address", "pin") and not c.name:
        sim = 0.6  # a bare address has no name to compare
    why["name"] = round(sim, 2)

    d_home = km(home[0], home[1], c.lat, c.lon)
    dist = 1.0 if d_home <= NEAR_KM else math.exp(-(d_home - NEAR_KM) / 60)
    why["distance_km"] = round(d_home, 1)

    s = 0.6 * sim + 0.2 * dist

    if hint.lat is not None and hint.lon is not None:
        d_pin = km(hint.lat, hint.lon, c.lat, c.lon)
        why["from_pin_km"] = round(d_pin, 2)
        s += 0.15 if d_pin < 0.15 else 0.05 if d_pin < 1 else -0.2

    if hint.area and c.city and (norm(hint.area) in norm(c.city) or norm(c.city) in norm(hint.area)):
        s += 0.05
        why["area"] = 1

    cat = OSM_CATEGORY.get(c.osm_value or "")
    if cat and hint.category:
        s += 0.05 if cat == hint.category else -0.03

    if c.kind == "poi":
        s += 0.1
    elif c.kind == "area":
        s -= 0.15 if "not a specific venue" not in hint.flags else -0.05

    if hint.address and c.address_text:
        num = re.match(r"\s*(\d+)", hint.address)
        if num and re.match(rf"\s*{num.group(1)}\b", c.address_text):
            s += 0.1
            why["address"] = 1

    c.score = round(max(0.0, min(1.0, s)), 3)
    c.why = why
    return c
