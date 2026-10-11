"""Resident Advisor (ra.co) public GraphQL, no key.

Undocumented first-party API, so the query shape can change without notice: a schema error
surfaces as RuntimeError and the run records it. Listings are keyed by RA area id, not by
coordinates (Los Angeles is 23), so events are also filtered by distance from the area center.
Times are local to the RA area; one event can be listed on several days and is yielded once.
"""
import re
from collections.abc import Iterator
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.discover.base import Adapter, Area, RawEvent, in_area, in_window, parse_price

URL = "https://ra.co/graphql"
LA_AREA = 23
LA_TZ = "America/Los_Angeles"
PAGE_SIZE = 50
MAX_PAGES = 10
CANCELLED = re.compile(r"^\s*\[?(cancelled|canceled)\]?\s*[:\-]?\s*", re.I)

QUERY = """query GET_EVENT_LISTINGS($filters: FilterInputDtoInput, $page: Int, $pageSize: Int) {
  eventListings(filters: $filters, pageSize: $pageSize, page: $page, sort: {listingDate: {order: ASCENDING}}) {
    data {
      id
      listingDate
      event {
        id title date startTime endTime cost contentUrl isTicketed attending minimumAge
        images { filename type }
        genres { name }
        venue { id name address tba location { latitude longitude } }
        area { ianaTimeZone }
      }
    }
    totalResults
  }
}"""


def _local(v: str | None, zone: ZoneInfo) -> datetime | None:
    if not v:
        return None
    return datetime.fromisoformat(v.replace("Z", "")).replace(tzinfo=zone)


def to_raw(ev: dict) -> RawEvent:
    tz = ((ev.get("area") or {}).get("ianaTimeZone")) or LA_TZ
    zone = ZoneInfo(tz)
    start = _local(ev.get("startTime"), zone)
    all_day = False
    if start is None:
        start, all_day = _local(ev.get("date"), zone), True
    end = _local(ev.get("endTime"), zone)
    if end is not None and start is not None and end <= start:
        end += timedelta(days=1)  # "22:00 to 02:00" stored on the same date

    title = (ev.get("title") or "").strip()
    status = "scheduled"
    if CANCELLED.match(title):
        status = "cancelled"
        title = CANCELLED.sub("", title).strip()

    venue = ev.get("venue") or {}
    loc = venue.get("location") or {}
    lat, lon = loc.get("latitude"), loc.get("longitude")
    if venue.get("tba") or not lat or not lon:
        lat = lon = None  # TBA venues report 0,0
    venue_name = None if venue.get("tba") else (venue.get("name") or None)

    cost = (ev.get("cost") or "").strip() or None
    pmin, pmax, free = parse_price(cost)
    images = ev.get("images") or []
    image = next((i["filename"] for i in images if i.get("type") == "FLYERFRONT"), None)
    genres = [g["name"].lower() for g in ev.get("genres") or [] if g.get("name")]
    eid = str(ev["id"])
    return RawEvent(
        adapter="resident_advisor",
        external_id=eid,
        title=title,
        url=f"https://ra.co/events/{eid}",
        starts_at=start,
        ends_at=end,
        all_day=all_day,
        tz=tz,
        status=status,
        venue_name=venue_name,
        address_text=(venue.get("address") or "").strip() or None,
        lat=float(lat) if lat is not None else None,
        lon=float(lon) if lon is not None else None,
        price_min=pmin,
        price_max=pmax,
        currency="USD" if pmin is not None and tz.startswith("America/") else None,
        is_free=free,
        price_text=cost,
        image_url=image,
        categories=["nightlife", "live_music", *genres[:3]],
        raw={"venue_tba": bool(venue.get("tba")), "venue_id": venue.get("id"),
             "attending": ev.get("attending"), "minimum_age": ev.get("minimumAge"),
             "ticketed": ev.get("isTicketed")},
    )


class ResidentAdvisor(Adapter):
    name = "resident_advisor"
    min_interval_s = 1.0

    def __init__(self, *args, area_id: int = LA_AREA, tz: str = LA_TZ, **kwargs):
        super().__init__(*args, **kwargs)
        self.area_id = area_id
        self.tz = ZoneInfo(tz)

    def _page(self, start: datetime, end: datetime, page: int) -> dict:
        fmt = "%Y-%m-%dT00:00:00.000Z"  # RA reads these as local dates
        last = (end - timedelta(microseconds=1)).astimezone(self.tz)
        body = {"operationName": "GET_EVENT_LISTINGS", "query": QUERY, "variables": {
            "filters": {"areas": {"eq": self.area_id},
                        "listingDate": {"gte": start.astimezone(self.tz).strftime(fmt),
                                        "lte": last.strftime(fmt)}},
            "page": page, "pageSize": PAGE_SIZE}}
        data = self.post(URL, json=body, headers={"Referer": "https://ra.co/events"}).json()
        if data.get("errors") and not (data.get("data") or {}).get("eventListings"):
            raise RuntimeError(f"RA GraphQL error: {data['errors'][0].get('message')}")
        return (data.get("data") or {}).get("eventListings") or {}

    def fetch(self, area: Area, start: datetime, end: datetime) -> Iterator[RawEvent]:
        seen: set[str] = set()
        page = 1
        while page <= MAX_PAGES:
            listing = self._page(start, end, page)
            rows = listing.get("data") or []
            for row in rows:
                ev = row.get("event") or {}
                if not ev.get("id") or str(ev["id"]) in seen:
                    continue
                seen.add(str(ev["id"]))
                try:
                    e = to_raw(ev)
                except (KeyError, TypeError, ValueError):
                    continue
                if not in_window(e, start, end) or not in_area(area, e.lat, e.lon):
                    continue
                yield e
            total = listing.get("totalResults") or 0
            if not rows or page * PAGE_SIZE >= total:
                break
            page += 1
