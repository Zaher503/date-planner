from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.auth import current_user
from app.db.models import AdapterState
from app.db.session import get_db
from app.discover import run
from app.discover.adapters import ADAPTERS
from app.discover.adapters.ical_feeds import IcalFeeds
from app.discover.base import Area
from app.main import app

SAMPLE = (Path(__file__).parent / "fixtures" / "feed_sample.ics").read_text(encoding="utf-8")
LA = ZoneInfo("America/Los_Angeles")
AREA = Area(lat=34.05, lon=-118.25, radius_km=40)
START = datetime(2026, 10, 1, tzinfo=LA)
END = datetime(2026, 12, 15, tzinfo=LA)
FEED = {"url": "https://example.org/cal.ics", "name": "Example Venue", "default_category": "music"}


def adapter(feeds, handler=None) -> IcalFeeds:
    handler = handler or (lambda req: httpx.Response(200, text=SAMPLE))
    ad = IcalFeeds(client=httpx.Client(transport=httpx.MockTransport(handler)), feeds=feeds)
    ad.min_interval_s = 0
    return ad


def test_registered_with_the_other_adapters():
    assert ADAPTERS["ical_feeds"] is IcalFeeds
    assert IcalFeeds.config_kwargs == ("feeds",)


def test_build_passes_stored_feeds_in():
    ad = run.build("ical_feeds", config={"feeds": [FEED]})
    assert ad.enabled() and ad.feeds == [FEED]
    assert not run.build("ical_feeds", config={}).enabled()  # no feeds: skipped, not an error


def test_sample_feed_expands_and_filters():
    events = list(adapter([FEED]).fetch(AREA, START, END))
    titles = [e.title for e in events]
    jazz = [e for e in events if e.title == "Wednesday Jazz Night"]
    assert len(jazz) == 7  # 8 Wednesdays minus the EXDATE
    assert len({e.external_id for e in jazz}) == 7
    assert jazz[0].venue_name == "The Blue Room" and jazz[0].lat == pytest.approx(34.0777)
    assert "music" in jazz[0].categories and "jazz" in jazz[0].categories
    assert "Autumn Night Market" in titles
    market = next(e for e in events if e.title == "Autumn Night Market")
    assert market.all_day
    assert "San Diego Show" not in titles  # outside the area
    assert "Old Event" not in titles  # outside the window
    cancelled = [e for e in events if e.title == "Poetry Reading"]
    assert cancelled and cancelled[0].status == "cancelled"


def test_webcal_url_is_fetched_as_https():
    seen = []

    def handler(req):
        seen.append(str(req.url))
        return httpx.Response(200, text=SAMPLE)

    list(adapter([{"url": "webcal://example.org/cal.ics"}], handler).fetch(AREA, START, END))
    assert seen == ["https://example.org/cal.ics"]


def test_one_broken_feed_is_skipped_but_all_broken_fails():
    def handler(req):
        return httpx.Response(200, text="<html>nope</html>") if "bad" in str(req.url) else httpx.Response(200, text=SAMPLE)

    good, bad = FEED, {"url": "https://example.org/bad.ics"}
    ad = adapter([bad, good], handler)
    assert list(ad.fetch(AREA, START, END)) and list(ad.errors) == [bad["url"]]
    with pytest.raises(RuntimeError, match="all 1 feeds failed"):
        list(adapter([bad], handler).fetch(AREA, START, END))


class FakeDB:
    def __init__(self):
        self.row = None

    def get(self, _model, key):
        return self.row if self.row and self.row.adapter == key else None

    def add(self, row):
        self.row = row

    def commit(self): ...


@pytest.fixture
def api():
    db = FakeDB()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[current_user] = lambda: SimpleNamespace(id=1, username="zaher", display_name="Zaher")
    yield TestClient(app), db
    app.dependency_overrides.clear()


def test_feeds_api_roundtrip(api):
    c, db = api
    assert c.get("/api/discover/feeds").json()["feeds"] == []
    body = {"feeds": [
        {"url": " webcal://example.org/a.ics ", "name": " Library ", "default_category": ""},
        {"url": "https://example.org/b.ics"},
        {"url": "WEBCAL://EXAMPLE.org/a.ics"},  # same feed again: dropped
    ]}
    r = c.put("/api/discover/feeds", json=body)
    assert r.status_code == 200
    assert r.json()["feeds"] == [
        {"url": "webcal://example.org/a.ics", "name": "Library", "default_category": None},
        {"url": "https://example.org/b.ics", "name": None, "default_category": None},
    ]
    assert isinstance(db.row, AdapterState) and db.row.adapter == "ical_feeds"
    # What is stored is exactly what the adapter is built from
    assert run.build("ical_feeds", config=db.row.config).feeds == r.json()["feeds"]
    assert c.get("/api/discover/feeds").json()["feeds"] == r.json()["feeds"]


def test_feeds_api_keeps_other_config_and_rejects_bad_urls(api):
    c, db = api
    db.row = AdapterState(adapter="ical_feeds", enabled=True, config={"note": "keep"})
    assert c.put("/api/discover/feeds", json={"feeds": []}).status_code == 200
    assert db.row.config == {"note": "keep", "feeds": []}
    for bad in ("ftp://example.org/a.ics", "file:///etc/passwd", "not a url", "https://"):
        assert c.put("/api/discover/feeds", json={"feeds": [{"url": bad}]}).status_code == 422
    too_many = [{"url": f"https://example.org/{i}.ics"} for i in range(31)]
    assert c.put("/api/discover/feeds", json={"feeds": too_many}).status_code == 422
