"""Photos of a place from Google Places (New). Off until GOOGLE_PLACES_KEY is set.

Google's terms do not allow keeping its photos, so nothing is stored: the photo names are remembered in
memory for a few hours and the image bytes are fetched on each view (the browser caches them briefly)."""
import logging
import time

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)

SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
MEDIA_URL = "https://places.googleapis.com/v1/{name}/media"
MAX_PHOTOS = 10
PHOTO_WIDTH = 1200
NAMES_TTL = 6 * 3600
TIMEOUT = 10

_names: dict[str, tuple[float, list[dict]]] = {}


def enabled() -> bool:
    return bool(get_settings().google_places_key)


def photos_for(query: str) -> list[dict]:
    """[{name, author}] for the best match of `query` (a venue name and address), newest lookup cached."""
    if not enabled() or not query.strip():
        return []
    hit = _names.get(query)
    if hit and time.time() - hit[0] < NAMES_TTL:
        return hit[1]
    headers = {"X-Goog-Api-Key": get_settings().google_places_key,
               "X-Goog-FieldMask": "places.id,places.photos"}
    try:
        r = httpx.post(SEARCH_URL, headers=headers, json={"textQuery": query, "maxResultCount": 1}, timeout=TIMEOUT)
        r.raise_for_status()
        places = r.json().get("places") or []
    except (httpx.HTTPError, ValueError) as e:
        log.warning("google places lookup failed: %s", e)
        return []
    out = [{"name": p["name"], "author": ((p.get("authorAttributions") or [{}])[0].get("displayName"))}
           for p in (places[0].get("photos") or [])[:MAX_PHOTOS] if p.get("name")] if places else []
    _names[query] = (time.time(), out)
    return out


def fetch_photo(name: str) -> tuple[bytes, str] | None:
    headers = {"X-Goog-Api-Key": get_settings().google_places_key}
    try:
        r = httpx.get(MEDIA_URL.format(name=name), params={"maxWidthPx": PHOTO_WIDTH}, headers=headers,
                      timeout=TIMEOUT, follow_redirects=True)
        r.raise_for_status()
    except httpx.HTTPError as e:
        log.warning("google photo failed: %s", e)
        return None
    return r.content, r.headers.get("content-type", "image/jpeg")
