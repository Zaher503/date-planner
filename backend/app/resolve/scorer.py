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
# Words that say what kind of place it is, not which one
GENERIC = {"the", "a", "an", "of", "and", "at", "on", "in", "by", "la", "los", "angeles", "dtla", "downtown",
           "bar", "restaurant", "cafe", "coffee", "rooftop", "lounge", "club", "kitchen", "grill", "house",
           "co", "company", "inc", "llc", "shop", "eatery", "ca", "california", "museum", "gallery",
           "theater", "theatre", "hotel", "center", "centre", "hall", "venue"}
# Without an exact address or pin, auto-accepting needs at least this name match
STRONG_NAME = 0.8
FAR_KM = 200.0


def norm(s: str | None) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    s = s.replace("&", " and ")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _core(tokens: list[str]) -> list[str]:
    return [t for t in tokens if t not in GENERIC] or tokens


def _cover(xs: list[str], ys: list[str]) -> float:
    """Share of tokens in xs found in ys (close spelling, or inside a run-together word)."""
    if not xs:
        return 0.0
    joined = "".join(ys)
    hits = sum(1 for x in xs if any(fuzz.ratio(x, y) >= 88 for y in ys) or (len(x) >= 4 and x in joined))
    return hits / len(xs)


def name_similarity(a: str | None, b: str | None) -> float:
    """Strict: every distinctive word on both sides has to match.
    'Perch Rooftop Bar' ~ 'Perch' high; 'Melrose Trading Post' ~ 'Trading Post' and 'Zaya' ~ 'Zara' low."""
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return 0.0
    if na.replace(" ", "") == nb.replace(" ", ""):
        return 1.0
    ca, cb = _core(na.split()), _core(nb.split())
    tok = min(_cover(ca, cb), _cover(cb, ca))
    seq = fuzz.token_sort_ratio(na, nb) / 100
    sim = 0.65 * tok + 0.35 * seq
    # Short distinctive names must match exactly ("Zaya" is not "Zara")
    ja, jb = "".join(ca), "".join(cb)
    if min(len(ja), len(jb)) <= 5 and ja != jb and not (ja in jb.split() or jb in ja.split()):
        sim = min(sim, 0.5)
    return round(sim, 3)


def score(c: Candidate, hint: ItemHint, home: tuple[float, float]) -> Candidate:
    why: dict[str, float] = {}
    sim = name_similarity(hint.name, c.name)
    if c.provider == "address":
        # A stated street address that geocoded to the exact house number is as good as a name
        sim = 0.95 if c.extra.get("house_match") else 0.6
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

    vague = "not a specific venue" in hint.flags
    if c.kind == "poi":
        s += 0.0 if vague else 0.1
    elif c.kind == "area":
        s += 0.15 if vague else -0.15

    if hint.address and c.address_text:
        num = re.match(r"\s*(\d+)", hint.address)
        if num and re.match(rf"\s*{num.group(1)}\b", c.address_text):
            s += 0.1
            why["address"] = 1

    located = bool(why.get("address")) or c.extra.get("house_match") or why.get("from_pin_km", 99) < 0.15
    if sim < STRONG_NAME and not located:
        s = min(s, AUTO_ACCEPT - 0.05)  # e.g. "K Bella Pizza" vs "Pizza Bella": ask, don't guess

    if d_home > FAR_KM and not (hint.lat is not None and why.get("from_pin_km", 99) < 1):
        s = min(s, 0.45)  # a namesake in another state

    c.score = round(max(0.0, min(1.0, s)), 3)
    c.why = why
    return c
