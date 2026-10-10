import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest

from app.discover.adapters.eventbrite_web import Blocked, EventbriteWeb, server_data, to_raw
from app.discover.base import Area

FIX = Path(__file__).parent / "fixtures"
BROWSE = (FIX / "eventbrite_browse.html").read_text(encoding="utf-8")
BROWSE_LD = (FIX / "eventbrite_browse_ld.html").read_text(encoding="utf-8")
DEST = json.loads((FIX / "eventbrite_destination.json").read_text(encoding="utf-8"))
RESULTS = server_data(BROWSE)["search_data"]["events"]["results"]
LA = ZoneInfo("America/Los_Angeles")
AREA = Area(lat=34.0461, lon=-118.3265, radius_km=40)
START = datetime(2026, 10, 10, tzinfo=LA)
END = START + timedelta(days=21)


def adapter(handler, **kw) -> EventbriteWeb:
    ad = EventbriteWeb(client=httpx.Client(transport=httpx.MockTransport(handler)), **kw)
    ad.min_interval_s = 0
    return ad


def handler_ok(seen: list | None = None):
    def handler(req: httpx.Request):
        if seen is not None:
            seen.append(req.url)
        if "/api/v3/destination/" in req.url.path:
            return httpx.Response(200, json=DEST)
        page = int(req.url.params.get("page", 1))
        return httpx.Response(200, text=BROWSE if page == 1 else BROWSE.replace('"eid": "', '"eid": "9'))
    return handler


def test_mapping_browse_event():
    e = to_raw(RESULTS[0])
    assert e.external_id == "2002815903281"
    assert e.title.startswith("FREE EVENT! E-40")
    assert e.starts_at == datetime(2026, 10, 18, 14, 0, tzinfo=LA)
    assert e.ends_at == datetime(2026, 10, 18, 23, 0, tzinfo=LA)
    assert e.venue_name == "Pershing Square"
    assert e.address_text == "532 S Olive St, Los Angeles, CA 90013"
    assert (e.lat, e.lon) == (34.0485582, -118.2532873)
    assert "music" in e.categories
    assert e.url.startswith("https://www.eventbrite.com/e/")
    assert e.price_min is None  # browse pages carry no prices


def test_street_address_venue_name_dropped():
    e = to_raw(RESULTS[2])
    assert e.venue_name is None and e.address_text


def test_fetch_adds_prices_and_dedups():
    seen = []
    ad = adapter(handler_ok(seen), pages_per_chunk=1)
    events = list(ad.fetch(AREA, START, END))
    ids = [e.external_id for e in events]
    assert len(ids) == len(set(ids))
    assert len(ids) == len(RESULTS)  # chunks 2 and 3 return the same events again
    e = next(e for e in events if e.external_id == "1998619555893")
    assert (e.price_min, e.price_max, e.currency, e.is_free) == (17.85, 71.21, "USD", False)
    browse = [u for u in seen if "/d/" in u.path]
    assert len(browse) == 3  # three weekly chunks, one page each
    assert browse[0].params["start_date"] == "2026-10-10" and browse[0].params["end_date"] == "2026-10-16"
    assert browse[-1].params["end_date"] == "2026-10-30"


def test_fetch_reads_several_pages_per_chunk():
    ad = adapter(handler_ok(), pages_per_chunk=2)
    events = list(ad.fetch(AREA, START, END))
    assert len(events) == 2 * len(RESULTS)


def test_price_failure_is_not_fatal():
    def handler(req: httpx.Request):
        if "/api/v3/destination/" in req.url.path:
            return httpx.Response(500)
        return httpx.Response(200, text=BROWSE)

    events = list(adapter(handler, pages_per_chunk=1).fetch(AREA, START, END))
    assert events and all(e.price_min is None for e in events)


def test_jsonld_fallback():
    ad = adapter(lambda req: httpx.Response(200, text=BROWSE_LD), pages_per_chunk=1)
    events = list(ad.fetch(AREA, START, END))
    assert len(events) == 3
    e = events[0]
    assert e.external_id == "2002815903281" and e.raw["source"] == "jsonld"
    assert e.all_day and e.starts_at == datetime(2026, 10, 18, tzinfo=LA)
    assert e.venue_name == "Pershing Square" and e.lat == 34.0485582


def test_blocked_page_raises_clear_error():
    ad = adapter(lambda req: httpx.Response(403, text="<title>Just a moment...</title>"))
    with pytest.raises(Blocked, match="HTTP 403"):
        list(ad.fetch(AREA, START, END))
    ad = adapter(lambda req: httpx.Response(200, text="<html>Checking your browser</html>"))
    with pytest.raises(Blocked, match="no event data"):
        list(ad.fetch(AREA, START, END))
