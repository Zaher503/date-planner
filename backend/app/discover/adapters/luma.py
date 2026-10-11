"""Luma (lu.ma / luma.com) public discover feed, no key.

The city page (luma.com/la) is backed by api.lu.ma/discover/get-paginated-events. Called with
latitude/longitude instead of a curated place id it returns every public event nearby, sorted
by start, with a cursor. About a quarter of events hide the address until you register: those
keep only the neighborhood and city, and their coordinates are deliberately fuzzed, so they are
used for the distance filter but not reported as a pin.
"""
import re
from collections.abc import Iterator
from datetime import datetime

from app.discover.base import Adapter, Area, RawEvent, in_area, in_window

URL = "https://api.lu.ma/discover/get-paginated-events"
PAGE_SIZE = 50
MAX_PAGES = 15


def _dt(v: str | None) -> datetime | None:
    return datetime.fromisoformat(v.replace("Z", "+00:00")) if v else None


def _price(ti: dict) -> tuple[float | None, float | None, str | None]:
    p = ti.get("price") or {}
    if p.get("cents") is None:
        return None, None, None
    cents = [p["cents"]]
    if p.get("min_cents") is not None:
        cents.append(p["min_cents"])
    mx = ti.get("max_price") or {}
    if mx.get("cents") is not None:
        cents.append(mx["cents"])
    return min(cents) / 100, max(cents) / 100, (p.get("currency") or "usd").upper()


def to_raw(entry: dict) -> RawEvent | None:
    """None for online-only events."""
    ev = entry["event"]
    if ev.get("location_type") not in (None, "offline"):
        return None
    geo = ev.get("geo_address_info") or {}
    co = ev.get("coordinate") or {}
    hidden = geo.get("mode") != "shown"
    lat, lon = co.get("latitude"), co.get("longitude")

    first = (geo.get("address") or "").strip()
    if hidden:
        venue = None
        address = ", ".join(p for p in (geo.get("sublocality"), geo.get("city_state")) if p) or None
    else:
        # "address" is the place name for venues and the street line otherwise
        venue = first if first and not re.match(r"\d", first) else None
        address = geo.get("full_address") or first or None

    ti = entry.get("ticket_info") or {}
    pmin, pmax, currency = _price(ti)
    free = ti.get("is_free")
    if free:
        pmin = pmax = 0.0
    tz = ev.get("timezone")
    return RawEvent(
        adapter="luma",
        external_id=ev["api_id"],
        title=(ev.get("name") or "").strip(),
        url=f"https://lu.ma/{ev['url']}" if ev.get("url") else None,
        starts_at=_dt(ev.get("start_at") or entry.get("start_at")),
        ends_at=_dt(ev.get("end_at")),
        tz=tz,
        venue_name=venue,
        address_text=address,
        lat=None if hidden or lat is None else float(lat),
        lon=None if hidden or lon is None else float(lon),
        price_min=pmin,
        price_max=pmax,
        currency=currency,
        is_free=free if isinstance(free, bool) else None,
        image_url=ev.get("cover_url"),
        categories=[],
        raw={"address_hidden": hidden,
             "approx_lat": lat if hidden else None, "approx_lon": lon if hidden else None,
             "city": geo.get("city"), "sold_out": ti.get("is_sold_out"),
             "require_approval": ti.get("require_approval")},
    )


class Luma(Adapter):
    name = "luma"
    min_interval_s = 1.0

    def fetch(self, area: Area, start: datetime, end: datetime) -> Iterator[RawEvent]:
        cursor = None
        for _ in range(MAX_PAGES):
            params = {"latitude": f"{area.lat:.4f}", "longitude": f"{area.lon:.4f}",
                      "pagination_limit": PAGE_SIZE}
            if cursor:
                params["pagination_cursor"] = cursor
            data = self.get(URL, **params).json()
            entries = data.get("entries") or []
            past_end = False
            for entry in entries:
                try:
                    e = to_raw(entry)
                except (KeyError, TypeError, ValueError):
                    continue
                if e is None:
                    continue
                if e.starts_at and e.starts_at >= end:
                    past_end = True
                    continue
                lat = e.lat if e.lat is not None else e.raw.get("approx_lat")
                lon = e.lon if e.lon is not None else e.raw.get("approx_lon")
                if in_window(e, start, end) and in_area(area, lat, lon):
                    yield e
            cursor = data.get("next_cursor")
            if past_end or not data.get("has_more") or not cursor or not entries:
                break
