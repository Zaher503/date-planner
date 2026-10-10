"""Ticketmaster Discovery API v2 (free key: 5000 calls/day; we stay at 2 req/s).

Terms we follow: personal and non-commercial, cache only for a reasonable period
(events are purged 30 days after they end), always link back to the Ticketmaster page.
Deep paging stops at 1000 results per query, so busy windows are split in half.
"""
from collections.abc import Iterator
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.discover.base import Adapter, Area, RawEvent

BASE = "https://app.ticketmaster.com/discovery/v2/events.json"
PAGE_SIZE = 200
DEEP_LIMIT = 1000
MIN_SPLIT = timedelta(hours=6)
SKIP_CLASS = {"undefined", "miscellaneous", "other", ""}


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_start(d: dict, tz: str | None) -> tuple[datetime | None, bool]:
    """Returns (start, all_day). Time-TBA events become all-day on their local date."""
    if d.get("dateTime") and not d.get("timeTBA") and not d.get("noSpecificTime"):
        return datetime.fromisoformat(d["dateTime"].replace("Z", "+00:00")), False
    if d.get("localDate"):
        day = datetime.fromisoformat(d["localDate"]).date()
        zone = ZoneInfo(tz) if tz else timezone.utc
        if d.get("localTime") and not d.get("timeTBA"):
            return datetime.combine(day, time.fromisoformat(d["localTime"]), zone), False
        return datetime.combine(day, time(0), zone), True
    return None, False


def to_raw(ev: dict) -> RawEvent:
    venue = ((ev.get("_embedded") or {}).get("venues") or [{}])[0]
    dates = ev.get("dates") or {}
    tz = dates.get("timezone") or venue.get("timezone")
    start, all_day = _parse_start(dates.get("start") or {}, tz)
    end, _ = _parse_start(dates.get("end") or {}, tz)

    addr = venue.get("address") or {}
    parts = [addr.get("line1"), (venue.get("city") or {}).get("name"),
             (venue.get("state") or {}).get("stateCode"), venue.get("postalCode")]
    loc = venue.get("location") or {}

    prices = ev.get("priceRanges") or []
    mins = [p["min"] for p in prices if p.get("min") is not None]
    maxs = [p["max"] for p in prices if p.get("max") is not None]

    cats: list[str] = []
    for c in ev.get("classifications") or []:
        for k in ("segment", "genre", "subGenre"):
            name = ((c.get(k) or {}).get("name") or "").strip()
            if name.lower() not in SKIP_CLASS and name.lower() not in cats:
                cats.append(name.lower())

    images = sorted(ev.get("images") or [], key=lambda i: i.get("width") or 0, reverse=True)
    image = next((i["url"] for i in images if i.get("ratio") == "16_9"), images[0]["url"] if images else None)

    status = (dates.get("status") or {}).get("code", "")
    return RawEvent(
        adapter="ticketmaster",
        external_id=ev["id"],
        title=ev.get("name", "").strip(),
        url=ev.get("url"),
        starts_at=start,
        ends_at=end,
        all_day=all_day,
        tz=tz,
        status="cancelled" if status in ("cancelled", "canceled") else "scheduled",
        venue_name=venue.get("name"),
        address_text=", ".join(p for p in parts if p) or None,
        lat=float(loc["latitude"]) if loc.get("latitude") else None,
        lon=float(loc["longitude"]) if loc.get("longitude") else None,
        price_min=min(mins) if mins else None,
        price_max=max(maxs) if maxs else None,
        currency=(prices[0].get("currency") if prices else None),
        price_text=None,
        description=ev.get("info") or ev.get("pleaseNote"),
        image_url=image,
        categories=cats,
        raw={"status": status, "url": ev.get("url")},
    )


class Ticketmaster(Adapter):
    name = "ticketmaster"
    key_setting = "ticketmaster_key"
    min_interval_s = 0.6
    daily_quota = 4000  # under the 5000 default to leave headroom

    def _query(self, area: Area, start: datetime, end: datetime, page: int) -> dict:
        return self.get(BASE, apikey=self.key, latlong=f"{area.lat:.4f},{area.lon:.4f}",
                        radius=max(1, round(area.radius_km)), unit="km",
                        startDateTime=_iso(start), endDateTime=_iso(end),
                        size=PAGE_SIZE, page=page, sort="date,asc", locale="*").json()

    def fetch(self, area: Area, start: datetime, end: datetime) -> Iterator[RawEvent]:
        first = self._query(area, start, end, 0)
        total = (first.get("page") or {}).get("totalElements", 0)
        if total > DEEP_LIMIT and end - start > MIN_SPLIT:
            mid = start + (end - start) / 2
            yield from self.fetch(area, start, mid)
            yield from self.fetch(area, mid, end)
            return
        pages = (first.get("page") or {}).get("totalPages", 0)
        data, page = first, 0
        while True:
            for ev in (data.get("_embedded") or {}).get("events", []):
                yield to_raw(ev)
            page += 1
            if page >= pages or page * PAGE_SIZE >= DEEP_LIMIT:
                break
            data = self._query(area, start, end, page)
