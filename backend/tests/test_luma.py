import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from app.discover.adapters.luma import Luma, to_raw
from app.discover.base import Area

FIX = Path(__file__).parent / "fixtures"
PAGE = json.loads((FIX / "luma_events.json").read_text(encoding="utf-8"))
BY_TITLE = {e["event"]["name"]: e for e in PAGE["entries"]}
AREA = Area(lat=34.0461, lon=-118.3265, radius_km=40)
START = datetime(2026, 10, 10, tzinfo=ZoneInfo("America/Los_Angeles"))
END = START + timedelta(days=21)


def entry(prefix: str) -> dict:
    return next(v for k, v in BY_TITLE.items() if k.startswith(prefix))


def adapter(handler) -> Luma:
    ad = Luma(client=httpx.Client(transport=httpx.MockTransport(handler)))
    ad.min_interval_s = 0
    return ad


def test_mapping_named_venue_free():
    e = to_raw(entry("The Patch Party"))
    assert e.venue_name == "Diner Antonette"
    assert e.address_text == "Diner Antonette, 1213 Wilshire Blvd, Santa Monica, CA 90403, USA"
    assert e.lat is not None and e.lon is not None
    assert e.is_free and e.price_min == 0
    assert e.url == "https://lu.ma/1ryqnjle"
    assert e.starts_at == datetime(2026, 10, 10, 19, 0, tzinfo=timezone.utc)
    assert e.tz == "America/Los_Angeles"
    assert not e.raw["address_hidden"]


def test_mapping_street_address_is_not_a_venue():
    e = to_raw(entry("GLOBE365"))
    assert e.venue_name is None
    assert e.address_text == "801 S Figueroa St, Los Angeles, CA 90017, USA"


def test_mapping_hidden_address_keeps_area_text():
    e = to_raw(entry("Pitch and Chat"))
    assert e.raw["address_hidden"]
    assert e.lat is None and e.lon is None and e.raw["approx_lat"] is not None
    assert e.venue_name is None and e.address_text == "Venice, Los Angeles, CA"
    assert (e.price_min, e.price_max, e.currency, e.is_free) == (5, 10, "USD", False)


def test_mapping_online_event_skipped():
    ev = json.loads(json.dumps(entry("GLOBE365")))
    ev["event"]["location_type"] = "online"
    assert to_raw(ev) is None


def test_fetch_filters_by_distance():
    seen = []

    def handler(req: httpx.Request):
        seen.append(dict(req.url.params))
        return httpx.Response(200, json=PAGE)

    titles = [e.title for e in adapter(handler).fetch(AREA, START, END)]
    assert seen[0]["latitude"] == "34.0461" and seen[0]["pagination_limit"] == "50"
    assert not any("Irvine" in t or "Orange County" in t for t in titles)
    assert not any(t.startswith("THE AI EDGE") for t in titles)  # hidden, fuzzed pin in Irvine
    assert any(t.startswith("Great Food") for t in titles)  # hidden, inside LA
    assert len(titles) == 5


def test_fetch_follows_cursor_and_stops_past_window():
    entries = PAGE["entries"]

    def handler(req: httpx.Request):
        cur = req.url.params.get("pagination_cursor")
        if cur is None:
            return httpx.Response(200, json={"entries": entries[:4], "has_more": True, "next_cursor": "c2"})
        late = json.loads(json.dumps(entries[6]))
        late["event"]["start_at"] = "2026-12-01T00:00:00.000Z"
        return httpx.Response(200, json={"entries": [entries[4], {"bad": 1}, late],
                                         "has_more": True, "next_cursor": "c3"})

    ad = adapter(handler)
    events = list(ad.fetch(AREA, START, END))
    assert ad.calls == 2  # the late event ends paging
    assert len(events) == 3
