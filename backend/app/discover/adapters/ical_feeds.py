"""Generic iCal feeds (city, library, parks, venue calendars) added in Settings.

Feeds live in adapter_state.config["feeds"] for the ical_feeds row, as a list of
{url, name, default_category}; run.py passes them in as feeds=[...]. Recurring events are
expanded inside the window (RRULE, RDATE, EXDATE and moved occurrences). RSS items are read
only when they carry an RSS event-module start date (ev:startdate); a plain pubDate is when
the post was published, not when the event happens. One broken feed is skipped; the adapter
only fails when every feed fails.
"""
import hashlib
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import httpx
import icalendar
import recurring_ical_events

from app.discover.base import USER_AGENT, Adapter, Area, RawEvent, in_area, in_window

DEFAULT_TZ = "America/Los_Angeles"
EV_NS = "{http://purl.org/rss/1.0/modules/event/}"


def _feed_id(feed: dict) -> str:
    return hashlib.sha1(feed["url"].encode()).hexdigest()[:8]


def _aware(v, zone: ZoneInfo) -> tuple[datetime | None, bool]:
    """(datetime, all_day) from a DTSTART/DTEND value."""
    if isinstance(v, datetime):
        return (v if v.tzinfo else v.replace(tzinfo=zone)), False
    if isinstance(v, date):
        return datetime.combine(v, time(0), zone), True
    return None, False


def _text(v) -> str | None:
    s = str(v).strip() if v is not None else ""
    return s or None


def _split_location(loc: str | None) -> tuple[str | None, str | None]:
    """"The Blue Room, 1234 Sunset Blvd, LA" -> venue "The Blue Room", address = whole text."""
    if not loc:
        return None, None
    first = loc.split(",", 1)[0].strip()
    venue = first if "," in loc and first and not re.match(r"\d", first) else None
    return venue, loc


def _categories(ev) -> list[str]:
    out: list[str] = []
    props = ev.get("CATEGORIES")
    for p in props if isinstance(props, list) else [props] if props is not None else []:
        for c in getattr(p, "cats", []) or []:
            label = str(c).strip().lower()
            if label and label not in out:
                out.append(label)
    return out


def vevent_to_raw(ev, adapter: str, feed: dict, recurring: set[str], zone: ZoneInfo) -> RawEvent | None:
    start, all_day = _aware(ev.decoded("DTSTART", None), zone)
    if start is None:
        return None
    end, _ = _aware(ev.decoded("DTEND", None), zone)
    if end is None and ev.get("DURATION") is not None:
        end = start + ev.decoded("DURATION")
    if all_day and end is not None and end - start <= timedelta(days=1):
        end = None
    uid = _text(ev.get("UID")) or f"{_text(ev.get('SUMMARY'))}@{start.isoformat()}"
    ext = f"{_feed_id(feed)}:{uid}"
    if uid in recurring:
        ext += f"/{start:%Y%m%dT%H%M}"
    venue, address = _split_location(_text(ev.get("LOCATION")))
    geo = ev.get("GEO")
    lat = float(geo.latitude) if geo is not None else None
    lon = float(geo.longitude) if geo is not None else None
    cats = [c for c in [feed.get("default_category")] if c] + _categories(ev)
    desc = _text(ev.get("DESCRIPTION"))
    return RawEvent(
        adapter=adapter,
        external_id=ext,
        title=_text(ev.get("SUMMARY")) or "",
        url=_text(ev.get("URL")),
        starts_at=start,
        ends_at=end,
        all_day=all_day,
        tz=str(start.tzinfo) if isinstance(start.tzinfo, ZoneInfo) else None,
        status="cancelled" if str(ev.get("STATUS", "")).upper() == "CANCELLED" else "scheduled",
        venue_name=venue,
        address_text=address,
        lat=lat,
        lon=lon,
        description=desc[:600] if desc else None,
        categories=list(dict.fromkeys(cats)),
        raw={"feed": feed.get("name") or feed["url"], "uid": uid},
    )


def parse_ical(text: str, adapter: str, feed: dict, start: datetime, end: datetime,
               tz: str = DEFAULT_TZ) -> list[RawEvent]:
    cal = icalendar.Calendar.from_ical(text)
    zone = ZoneInfo(str(cal.get("X-WR-TIMEZONE") or tz))
    recurring = {str(e.get("UID")) for e in cal.walk("VEVENT") if e.get("RRULE") or e.get("RDATE")}
    out: list[RawEvent] = []
    for ev in recurring_ical_events.of(cal).between(start, end):
        try:
            e = vevent_to_raw(ev, adapter, feed, recurring, zone)
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
        if e is not None and e.title:
            out.append(e)
    return out


def parse_rss(text: str, adapter: str, feed: dict, tz: str = DEFAULT_TZ) -> list[RawEvent]:
    """RSS 2.0 items with ev:startdate (RSS 1.0 event module)."""
    root = ET.fromstring(text)
    zone = ZoneInfo(tz)
    out: list[RawEvent] = []
    for item in root.iter("item"):
        try:
            s = item.findtext(f"{EV_NS}startdate")
            if not s:
                continue
            start, all_day = _aware(datetime.fromisoformat(s.strip().replace("Z", "+00:00")), zone)
            e_txt = item.findtext(f"{EV_NS}enddate")
            end = datetime.fromisoformat(e_txt.strip().replace("Z", "+00:00")) if e_txt else None
            link = (item.findtext("link") or "").strip() or None
            guid = (item.findtext("guid") or link or item.findtext("title") or "").strip()
            venue, address = _split_location((item.findtext(f"{EV_NS}location") or "").strip() or None)
            out.append(RawEvent(
                adapter=adapter,
                external_id=f"{_feed_id(feed)}:{guid}",
                title=(item.findtext("title") or "").strip(),
                url=link,
                starts_at=start,
                ends_at=end if end is None or end.tzinfo else end.replace(tzinfo=zone),
                all_day=all_day,
                venue_name=venue,
                address_text=address,
                categories=[c for c in [feed.get("default_category")] if c],
                raw={"feed": feed.get("name") or feed["url"]},
            ))
        except (TypeError, ValueError):
            continue
    return [e for e in out if e.title]


def guarded_client() -> httpx.Client:
    """Feed URLs come from Settings, so every hop is SSRF-checked like a shared link."""
    from app.net import public_client

    c = public_client(timeout=20, browser=False)
    c.headers["User-Agent"] = USER_AGENT
    return c


class IcalFeeds(Adapter):
    name = "ical_feeds"
    min_interval_s = 1.0
    config_kwargs = ("feeds",)

    def __init__(self, client: httpx.Client | None = None, key: str | None = None,
                 feeds: list[dict] | None = None, tz: str = DEFAULT_TZ):
        super().__init__(client=client or guarded_client(), key=key)
        self.feeds = [f for f in feeds or [] if isinstance(f, dict) and f.get("url")]
        self.tz = tz
        self.errors: dict[str, str] = {}

    def enabled(self) -> bool:
        return bool(self.feeds)

    def _read(self, feed: dict, start: datetime, end: datetime) -> list[RawEvent]:
        url = re.sub(r"^webcal://", "https://", feed["url"].strip(), flags=re.I)
        text = self.get(url).text
        head = text.lstrip()[:200]
        if "BEGIN:VCALENDAR" in head:
            return parse_ical(text, self.name, feed, start, end, self.tz)
        if head.startswith("<") and ("<rss" in text[:2000] or "<channel" in text[:4000]):
            return parse_rss(text, self.name, feed, self.tz)
        raise ValueError("not an iCal or RSS feed")

    def fetch(self, area: Area, start: datetime, end: datetime) -> Iterator[RawEvent]:
        self.errors = {}
        for feed in self.feeds:
            try:
                events = self._read(feed, start, end)
            except Exception as e:  # one broken feed never stops the others
                self.errors[feed["url"]] = f"{type(e).__name__}: {e}"[:300]
                continue
            for e in events:
                if in_window(e, start, end) and in_area(area, e.lat, e.lon):
                    yield e
        if self.feeds and len(self.errors) == len(self.feeds):
            raise RuntimeError(f"all {len(self.feeds)} feeds failed: " + "; ".join(self.errors.values()))
