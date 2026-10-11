"""Eventbrite city browse pages (no public search API since 2020).

Each page embeds window.__SERVER_DATA__ with 20 events: local start/end, time zone, venue,
address and coordinates, but no prices. Prices come from the same keyless destination
endpoint the page itself calls (one call per page of ids); if that fails, events are still
yielded without prices. If __SERVER_DATA__ disappears, the page's JSON-LD ItemList is used.
LA lists over a thousand events a day ranked by relevance, so the window is split into weeks
and only the first few pages of each are read.
"""
import json
import re
from collections.abc import Iterator
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import httpx

from app.discover.base import Adapter, Area, RawEvent, in_area, in_window
from app.discover.jsonld import event_nodes, raw_from_jsonld

BROWSE = "https://www.eventbrite.com/d/{slug}/all-events/"
DESTINATION = "https://www.eventbrite.com/api/v3/destination/events/"
LA_SLUG = "ca--los-angeles"
LA_TZ = "America/Los_Angeles"
PAGES_PER_CHUNK = 3
CHUNK = timedelta(days=7)
EID = re.compile(r"-(\d{6,})/?(?:\?|$)")


class Blocked(RuntimeError):
    pass


def server_data(html: str) -> dict | None:
    at = html.find("window.__SERVER_DATA__")
    if at < 0:
        return None
    try:
        data, _ = json.JSONDecoder().raw_decode(html, html.index("{", at))
    except (ValueError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _local(d: str | None, t: str | None, zone: ZoneInfo) -> datetime | None:
    if not d:
        return None
    return datetime.combine(date.fromisoformat(d), time.fromisoformat(t) if t else time(0), zone)


def to_raw(ev: dict) -> RawEvent | None:
    """None for online events."""
    if ev.get("is_online_event"):
        return None
    tz = ev.get("timezone") or LA_TZ
    zone = ZoneInfo(tz)
    all_day = not ev.get("start_time")
    start = _local(ev.get("start_date"), ev.get("start_time"), zone)
    end = None if all_day else _local(ev.get("end_date"), ev.get("end_time"), zone)

    venue = ev.get("primary_venue") or {}
    addr = venue.get("address") or {}
    name = (venue.get("name") or "").strip()
    lat, lon = addr.get("latitude"), addr.get("longitude")

    cats: list[str] = []
    for t in ev.get("tags") or []:
        if t.get("prefix") in ("EventbriteCategory", "EventbriteFormat", "EventbriteSubCategory"):
            label = (t.get("display_name") or "").strip().lower()
            if label and label not in cats:
                cats.append(label)
    image = (ev.get("image") or {}).get("url")
    eid = str(ev.get("eid") or ev["id"])
    return RawEvent(
        adapter="eventbrite_web",
        external_id=eid,
        title=(ev.get("name") or "").strip(),
        url=ev.get("url"),
        starts_at=start,
        ends_at=end,
        all_day=all_day,
        tz=tz,
        status="cancelled" if ev.get("is_cancelled") else "scheduled",
        # Some organizers type the street address as the venue name
        venue_name=name if name and not re.match(r"\d", name) else None,
        address_text=addr.get("localized_address_display") or None,
        lat=float(lat) if lat else None,
        lon=float(lon) if lon else None,
        description=(ev.get("summary") or "").strip() or None,
        image_url=image,
        categories=cats,
        raw={"organizer_id": ev.get("primary_organizer_id"), "series_id": ev.get("series_id"),
             "tickets_by": ev.get("tickets_by")},
    )


def apply_prices(e: RawEvent, ta: dict | None) -> None:
    if not ta:
        return
    lo = (ta.get("minimum_ticket_price") or {}).get("major_value")
    hi = (ta.get("maximum_ticket_price") or {}).get("major_value")
    try:
        lo_f = float(lo) if lo is not None else None
        hi_f = float(hi) if hi is not None else lo_f
    except ValueError:
        return
    if lo_f is None:
        return
    e.price_min, e.price_max = lo_f, hi_f
    e.currency = (ta.get("minimum_ticket_price") or {}).get("currency")
    e.is_free = bool(ta.get("is_free")) or hi_f == 0
    if ta.get("is_sold_out"):
        e.raw["sold_out"] = True


class EventbriteWeb(Adapter):
    name = "eventbrite_web"
    min_interval_s = 2.0

    def __init__(self, *args, location_slug: str = LA_SLUG, tz: str = LA_TZ,
                 pages_per_chunk: int = PAGES_PER_CHUNK, **kwargs):
        super().__init__(*args, **kwargs)
        self.slug = location_slug
        self.tz = tz
        self.pages_per_chunk = pages_per_chunk

    def _page(self, day0: date, day1: date, page: int) -> tuple[list[RawEvent], int]:
        """Events on one browse page and the page count."""
        url = BROWSE.format(slug=self.slug)
        try:
            r = self.get(url, page=page, start_date=day0.isoformat(), end_date=day1.isoformat())
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (403, 429, 503):
                raise Blocked(f"eventbrite refused the browse page (HTTP {e.response.status_code}); "
                              "likely bot protection, not bypassed") from e
            raise
        html = r.text
        data = server_data(html)
        events = ((data or {}).get("search_data") or {}).get("events") or {}
        if events.get("results") is not None:
            out = []
            for ev in events["results"]:
                try:
                    e = to_raw(ev)
                except (KeyError, TypeError, ValueError):
                    continue
                if e is not None:
                    out.append(e)
            return out, (events.get("pagination") or {}).get("page_count") or 1
        nodes = event_nodes(html)
        if not nodes:
            raise Blocked("eventbrite page has no event data (challenge page or new layout)")
        out = []
        for n in nodes:
            link = str(n.get("url") or "")
            m = EID.search(link)
            try:
                e = raw_from_jsonld(n, self.name, m.group(1) if m else link, link or url, self.tz)
            except (KeyError, TypeError, ValueError):
                continue
            if e is not None:
                out.append(e)
        return out, page + 1 if len(nodes) >= 20 else page

    def _prices(self, events: list[RawEvent]) -> None:
        if not events:
            return
        try:
            data = self.get(DESTINATION, event_ids=",".join(e.external_id for e in events),
                            expand="ticket_availability", page_size=len(events)).json()
        except (httpx.HTTPError, ValueError, RuntimeError):
            return
        by_id = {str(d.get("id")): d for d in data.get("events") or []}
        for e in events:
            d = by_id.get(e.external_id)
            if d:
                apply_prices(e, d.get("ticket_availability"))
                if d.get("is_cancelled"):
                    e.status = "cancelled"

    def fetch(self, area: Area, start: datetime, end: datetime) -> Iterator[RawEvent]:
        zone = ZoneInfo(self.tz)
        seen: set[str] = set()
        chunk0 = start
        while chunk0 < end:
            chunk1 = min(end, chunk0 + CHUNK)
            day0 = chunk0.astimezone(zone).date()
            day1 = (chunk1 - timedelta(microseconds=1)).astimezone(zone).date()
            page, pages = 1, 1
            while page <= min(pages, self.pages_per_chunk):
                found, pages = self._page(day0, day1, page)
                fresh = [e for e in found if e.external_id not in seen
                         and in_window(e, start, end) and in_area(area, e.lat, e.lon)]
                seen.update(e.external_id for e in found)
                self._prices([e for e in fresh if e.raw.get("source") != "jsonld"])
                yield from fresh
                if not found:
                    break
                page += 1
            chunk0 = chunk1
