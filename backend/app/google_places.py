"""Photos of a place from Google Places (New). Off until GOOGLE_PLACES_KEY is set.

Built to stay inside Google's free tiers, and its rules:
- Text Search asks for place ids only and Place Details for photos only: both are free, unlimited requests.
- Only downloading an image is billed ($7 per 1,000 after 1,000 free a month), so those are counted and stopped at
  a daily cap (GOOGLE_PHOTO_DAILY_CAP, kept in DATA_DIR so a restart does not reset it).
- Place ids may be remembered, photo names may not (Google's terms): each image looks its name up fresh."""
import json
import logging
from datetime import date

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)

SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
DETAILS_URL = "https://places.googleapis.com/v1/places/{id}"
MEDIA_URL = "https://places.googleapis.com/v1/{name}/media"
MAX_PHOTOS = 5
PHOTO_WIDTH = 1200
TIMEOUT = 10

_place_ids: dict[str, str] = {}


def enabled() -> bool:
    return bool(get_settings().google_places_key)


def _usage_file():
    return get_settings().data_dir / "google_photo_usage.json"


def used_today() -> int:
    try:
        data = json.loads(_usage_file().read_text())
    except (OSError, ValueError):
        return 0
    return int(data.get("count", 0)) if data.get("date") == date.today().isoformat() else 0


def capped() -> bool:
    return used_today() >= get_settings().google_photo_daily_cap


def _count_download() -> None:
    f = _usage_file()
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"date": date.today().isoformat(), "count": used_today() + 1}))
    except OSError as e:
        log.warning("could not record google photo usage: %s", e)


def _headers(mask: str | None = None) -> dict:
    h = {"X-Goog-Api-Key": get_settings().google_places_key}
    if mask:
        h["X-Goog-FieldMask"] = mask
    return h


def place_id(query: str) -> str | None:
    """Google's id for the best match of `query` (free request, the id may be remembered)."""
    if query in _place_ids:
        return _place_ids[query]
    try:
        r = httpx.post(SEARCH_URL, headers=_headers("places.id"), json={"textQuery": query, "maxResultCount": 1},
                       timeout=TIMEOUT)
        r.raise_for_status()
        places = r.json().get("places") or []
    except (httpx.HTTPError, ValueError) as e:
        log.warning("google place search failed: %s", e)
        return None
    if not places or not places[0].get("id"):
        return None
    _place_ids[query] = places[0]["id"]
    return _place_ids[query]


def photos_for(query: str) -> list[dict]:
    """[{name, author}] fresh from Google, at most MAX_PHOTOS. Free; nothing is kept."""
    if not enabled() or not query.strip() or capped():
        return []
    pid = place_id(query)
    if not pid:
        return []
    try:
        r = httpx.get(DETAILS_URL.format(id=pid), headers=_headers("photos"), timeout=TIMEOUT)
        r.raise_for_status()
        photos = r.json().get("photos") or []
    except (httpx.HTTPError, ValueError) as e:
        log.warning("google place photos failed: %s", e)
        return []
    return [{"name": p["name"], "author": ((p.get("authorAttributions") or [{}])[0].get("displayName"))}
            for p in photos[:MAX_PHOTOS] if p.get("name")]


def fetch_photo(name: str) -> tuple[bytes, str] | None:
    """The image itself: the one billed request, so it is counted against the daily cap."""
    if capped():
        return None
    try:
        r = httpx.get(MEDIA_URL.format(name=name), params={"maxWidthPx": PHOTO_WIDTH}, headers=_headers(),
                      timeout=TIMEOUT, follow_redirects=True)
        r.raise_for_status()
    except httpx.HTTPError as e:
        log.warning("google photo failed: %s", e)
        return None
    _count_download()
    return r.content, r.headers.get("content-type", "image/jpeg")
