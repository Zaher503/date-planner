import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest

from app.discover.adapters.ticketmaster import Ticketmaster, to_raw
from app.discover.base import Area

FIX = Path(__file__).parent / "fixtures"
PAGE0 = json.loads((FIX / "ticketmaster_page0.json").read_text())
AREA = Area(lat=34.0461, lon=-118.3265, radius_km=40)
START = datetime(2026, 10, 10, tzinfo=timezone.utc)
END = START + timedelta(days=21)


def adapter(handler) -> Ticketmaster:
    ad = Ticketmaster(client=httpx.Client(transport=httpx.MockTransport(handler)), key="k")
    ad.min_interval_s = 0
    return ad


def test_disabled_without_key():
    assert not Ticketmaster(key="").enabled()
    assert Ticketmaster(key="abc").enabled()


def test_mapping_full_event():
    e = to_raw(PAGE0["_embedded"]["events"][0])
    assert e.external_id == "vvG1zZ9abc123"
    assert e.title == "Jazz Under the Stars"
    assert e.starts_at == datetime(2026, 10, 18, 3, 0, tzinfo=timezone.utc)
    assert not e.all_day
    assert e.venue_name == "Hollywood Bowl"
    assert e.address_text == "2301 N Highland Ave, Los Angeles, CA, 90068"
    assert (e.lat, e.lon) == (34.11265, -118.33895)
    assert (e.price_min, e.price_max, e.currency) == (25.0, 65.5, "USD")
    assert e.categories == ["music", "jazz"]  # "Undefined" dropped
    assert e.image_url.endswith("wide.jpg")  # largest 16:9
    assert e.url == "https://www.ticketmaster.com/event/abc123"
    assert e.status == "scheduled"


def test_mapping_time_tba_and_cancelled():
    e = to_raw(PAGE0["_embedded"]["events"][1])
    assert e.all_day
    assert e.starts_at == datetime(2026, 10, 20, tzinfo=ZoneInfo("America/Los_Angeles"))
    assert e.status == "cancelled"
    assert e.lat is None and e.price_min is None and e.image_url is None
    assert e.categories == ["arts & theatre", "comedy"]  # duplicate subGenre dropped


def test_fetch_sends_expected_query():
    seen = []

    def handler(req: httpx.Request):
        seen.append(dict(req.url.params))
        return httpx.Response(200, json=PAGE0)

    events = list(adapter(handler).fetch(AREA, START, END))
    assert len(events) == 2
    q = seen[0]
    assert q["apikey"] == "k" and q["unit"] == "km" and q["radius"] == "40"
    assert q["latlong"] == "34.0461,-118.3265"
    assert q["startDateTime"] == "2026-10-10T00:00:00Z"
    assert q["endDateTime"] == "2026-10-31T00:00:00Z"
    assert q["size"] == "200" and q["page"] == "0"


def test_fetch_pages_until_done():
    def handler(req: httpx.Request):
        page = int(req.url.params["page"])
        body = {"_embedded": {"events": [dict(PAGE0["_embedded"]["events"][0], id=f"e{page}")]},
                "page": {"totalElements": 450, "totalPages": 3, "number": page}}
        return httpx.Response(200, json=body)

    ad = adapter(handler)
    ids = [e.external_id for e in ad.fetch(AREA, START, END)]
    assert ids == ["e0", "e1", "e2"]
    assert ad.calls == 3


def test_fetch_splits_window_past_deep_paging_limit():
    windows = []

    def handler(req: httpx.Request):
        s = req.url.params["startDateTime"]
        e = req.url.params["endDateTime"]
        span = datetime.fromisoformat(e.replace("Z", "+00:00")) - datetime.fromisoformat(s.replace("Z", "+00:00"))
        if req.url.params["page"] == "0":
            windows.append(span)
        total = 1500 if span > timedelta(days=6) else 10
        return httpx.Response(200, json={"_embedded": {"events": []},
                                         "page": {"totalElements": total, "totalPages": 1, "number": 0}})

    list(adapter(handler).fetch(AREA, START, END))
    assert windows[0] == timedelta(days=21)
    assert all(w <= timedelta(days=21) for w in windows) and len(windows) > 3


def test_quota_enforced():
    ad = adapter(lambda req: httpx.Response(200, json=PAGE0))
    ad.daily_quota = 0
    with pytest.raises(RuntimeError, match="quota"):
        list(ad.fetch(AREA, START, END))


def test_http_error_raises():
    ad = adapter(lambda req: httpx.Response(401, json={"fault": {"faultstring": "Invalid ApiKey"}}))
    with pytest.raises(httpx.HTTPStatusError):
        list(ad.fetch(AREA, START, END))
