import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest

from app.discover.adapters.resident_advisor import ResidentAdvisor, to_raw
from app.discover.base import Area, parse_price

FIX = Path(__file__).parent / "fixtures"
PAGE = json.loads((FIX / "ra_listings.json").read_text(encoding="utf-8"))
ROWS = PAGE["data"]["eventListings"]["data"]
LA = ZoneInfo("America/Los_Angeles")
AREA = Area(lat=34.0461, lon=-118.3265, radius_km=40)
START = datetime(2026, 10, 10, tzinfo=LA)
END = START + timedelta(days=21)


def adapter(handler) -> ResidentAdvisor:
    ad = ResidentAdvisor(client=httpx.Client(transport=httpx.MockTransport(handler)))
    ad.min_interval_s = 0
    return ad


def test_enabled_without_key():
    assert ResidentAdvisor().enabled()


def test_mapping_cancelled_event():
    e = to_raw(ROWS[0]["event"])
    assert e.status == "cancelled"
    assert e.title.startswith("Marques Wyatt B2B Doc Martin")
    assert e.starts_at == datetime(2026, 10, 10, 13, 0, tzinfo=LA)
    assert e.ends_at == datetime(2026, 10, 10, 21, 0, tzinfo=LA)
    assert e.venue_name == "California Plaza"
    assert e.address_text == "340 S Grand Ave, Los Angeles, CA 90071, USA"
    assert (e.lat, e.lon) == (34.05, -118.25)
    assert (e.price_min, e.price_max, e.currency, e.is_free) == (20, 20, "USD", False)
    assert e.url == "https://ra.co/events/2457752"
    assert e.categories[:2] == ["nightlife", "live_music"] and "tech house" in e.categories
    assert e.image_url.startswith("https://images.ra.co/")


def test_mapping_overnight_and_tba_venue():
    e = to_raw(ROWS[2]["event"])
    assert e.ends_at == datetime(2026, 10, 11, 7, 0, tzinfo=LA)
    assert e.venue_name is None and e.lat is None and e.lon is None
    assert (e.price_min, e.price_max, e.price_text) == (25, 45, "25-45")
    assert e.raw["venue_tba"]


def test_mapping_missing_cost():
    e = to_raw(ROWS[4]["event"])
    assert e.price_min is None and e.price_text is None and e.is_free is None


def test_parse_price():
    assert parse_price("$25-$50") == (25, 50, False)
    assert parse_price("Free") == (0, 0, True)
    assert parse_price("15 / 20 / 25") == (15, 25, False)
    assert parse_price("0") == (None, None, None)
    assert parse_price("$1,200") == (1200, 1200, False)
    assert parse_price("") == (None, None, None)


def test_fetch_sends_query():
    seen = []

    def handler(req: httpx.Request):
        seen.append(json.loads(req.content))
        return httpx.Response(200, json=PAGE)

    ad = adapter(handler)
    events = list(ad.fetch(AREA, START, END))
    assert len(events) == 7
    # San Diego venue without coordinates is kept; the run geocodes and filters it later
    sd = next(e for e in events if e.title == "NITEHARTS DAY 2")
    assert sd.lat is None and "San Diego" in sd.address_text
    v = seen[0]["variables"]
    assert v["filters"]["areas"] == {"eq": 23}
    assert v["filters"]["listingDate"] == {"gte": "2026-10-10T00:00:00.000Z", "lte": "2026-10-30T00:00:00.000Z"}
    assert v["page"] == 1
    assert ad.calls == 1


def test_fetch_pages_dedups_and_skips_bad_rows():
    def handler(req: httpx.Request):
        page = json.loads(req.content)["variables"]["page"]
        rows = [ROWS[1], {"id": "x", "event": {"id": "999", "startTime": "not a date"}}]
        if page == 2:
            rows = [ROWS[1], ROWS[3]]  # same event listed again on another day
        return httpx.Response(200, json={"data": {"eventListings": {"data": rows, "totalResults": 150}}}
                              if page <= 2 else {"data": {"eventListings": {"data": [], "totalResults": 150}}})

    ad = adapter(handler)
    ids = [e.external_id for e in ad.fetch(AREA, START, END)]
    assert ids == [ROWS[1]["event"]["id"], ROWS[3]["event"]["id"]]
    assert ad.calls == 3


def test_fetch_drops_far_venues():
    far = json.loads(json.dumps(ROWS[1]))
    far["event"]["venue"]["location"] = {"latitude": 32.78, "longitude": -117.12}  # San Diego
    body = {"data": {"eventListings": {"data": [far, ROWS[3]], "totalResults": 2}}}
    events = list(adapter(lambda req: httpx.Response(200, json=body)).fetch(AREA, START, END))
    assert [e.title for e in events] == ["SET with Woo York [Live]"]


def test_window_excludes_outside_events():
    ad = adapter(lambda req: httpx.Response(200, json=PAGE))
    later = START + timedelta(days=1)  # drops the Oct 10 events
    events = list(ad.fetch(AREA, later, later + timedelta(days=1)))
    assert [e.title for e in events] == ["Sunday Sessions LA (Vinyl Only)"]


def test_schema_error_raises():
    ad = adapter(lambda req: httpx.Response(200, json={"errors": [{"message": "Cannot query field"}]}))
    with pytest.raises(RuntimeError, match="Cannot query field"):
        list(ad.fetch(AREA, START, END))
