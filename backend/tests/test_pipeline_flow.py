"""The no-database half of the import pipeline: read the link, tidy, demote offerings, age, price step.

Saved pages stand in for the web and a canned answer for the model. Modules import fetch_text and
chat_json by name, so each importing module gets its own stub.
"""
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app import browser
from app.ingest import page_images, pipeline, pricing
from app.llm import extract as llm_extract

FIX = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
JOB = SimpleNamespace(id=1, payload={})


class Db:
    def commit(self):
        pass


def saved(name: str) -> str:
    return (FIX / f"page_{name}.html").read_text(encoding="utf-8")


def source(kind: str, url: str | None = None, caption: str | None = None):
    return SimpleNamespace(kind=kind, url=url, caption=caption, raw={}, title=None, transcript=None,
                           fetched_at=None, id="s1")


class World:
    """Records what the pipeline asked the web and the model for."""
    def __init__(self):
        self.fetched: list[str] = []
        self.asked: list[str] = []
        self.priced: list[tuple] = []


@pytest.fixture
def world(monkeypatch):
    w = World()
    monkeypatch.setattr(pipeline.jobs, "set_stage", lambda *a, **k: None)
    monkeypatch.setattr(browser, "available", lambda: False)

    def no_web(url, client=None):
        w.fetched.append(url)
        raise httpx.ConnectError("offline")
    monkeypatch.setattr(pipeline, "fetch_text", no_web)
    monkeypatch.setattr(pricing, "fetch_text", no_web)

    def spy(hints, start_url, html=None):
        w.priced.append((len(hints), start_url))
        return 0
    monkeypatch.setattr(pricing, "enrich", spy)

    def no_model(system, user, schema, **kw):
        raise AssertionError("an unexpected model call")
    monkeypatch.setattr(llm_extract, "chat_json", no_model)
    monkeypatch.setattr(pricing, "chat_json", no_model)
    return w


def serve(monkeypatch, world, url: str, html: str):
    def fetch(u, client=None):
        world.fetched.append(u)
        return u, html
    monkeypatch.setattr(pipeline, "fetch_text", fetch)


def classify_as(monkeypatch, world, category: str, tags: list[str]):
    def chat(system, user, schema, **kw):
        world.asked.append(system.split("\n")[0])
        n = user.count("\n") + 1 if user.strip() else 0
        return {"items": [{"index": i, "category": category, "tags": tags} for i in range(10)][:max(n, 1)]}
    monkeypatch.setattr(llm_extract, "chat_json", chat)


def answer_with(monkeypatch, world, answer: dict):
    def chat(system, user, schema, **kw):
        world.asked.append(system.split("\n")[0])
        return answer
    monkeypatch.setattr(llm_extract, "chat_json", chat)


def read_and_prepare(src, now=NOW):
    """Read the link by kind, then tidy, demote, age, price."""
    g = pipeline.read_link(Db(), JOB, src)
    return g, pipeline.prepare(Db(), JOB, src, g, now)


def test_eventbrite_long_run_with_a_price_is_classified_and_keeps_its_dates(monkeypatch, world):
    url = "https://example.com/eventbrite"
    serve(monkeypatch, world, url, saved("eventbrite"))
    classify_as(monkeypatch, world, "live_music", ["jazz", "live music"])
    src = source("event_page", url)
    g, hints = read_and_prepare(src)
    assert len(hints) == 1
    h = hints[0]
    assert (h.kind, h.name, h.event_title) == ("event", "Bar Lis", "Jazz Eclectic LA")
    assert h.category == "live_music" and h.tags == ["jazz", "live music"]
    assert h.is_free is True and h.price_min == 0.0 and h.price_max == 0.0
    assert h.starts_at == datetime(2021, 9, 1, 3, tzinfo=timezone.utc)
    assert h.all_day and h.ends_at == datetime(2026, 12, 30, 9, tzinfo=timezone.utc)  # a long run keeps both dates
    assert h.flags == [] and h.min_age is None and h.provider == "jsonld"
    assert world.priced == []  # it already has a price, so the price step is skipped
    assert len(world.asked) == 1 and world.asked[0].startswith("For each numbered place or event")
    assert src.title == "Jazz Eclectic LA"
    assert src.raw["page"]["jsonld_items"] == 1 and src.raw["page"]["url"] == url


def test_luma_event_keeps_its_exact_pin(monkeypatch, world):
    url = "https://example.com/luma"
    serve(monkeypatch, world, url, saved("luma"))
    classify_as(monkeypatch, world, "class", ["ai", "meetup"])
    g, hints = read_and_prepare(source("event_page", url))
    (h,) = hints
    assert h.event_title == "AI Safety Meet-up Los Angeles" and h.name == "Marina del Rey, California"
    assert h.exact_pin and round(h.lat, 3) == 33.981
    assert h.category == "class" and h.is_free is True
    assert h.flags == ["event already happened"]
    assert world.priced == []


def test_venue_page_stays_a_place_with_hours(monkeypatch, world):
    url = "https://www.perchla.com/"
    serve(monkeypatch, world, url, saved("perch"))
    classify_as(monkeypatch, world, "bar", ["rooftop", "cocktails"])
    g, hints = read_and_prepare(source("event_page", url))
    (h,) = hints
    assert (h.kind, h.name, h.category) == ("place", "Perch LA", "bar")
    assert h.address.startswith("448 South Hill Street")
    assert h.opening_hours.startswith("Mo 16:00-01:00; Tu 16:00-01:00")
    assert h.flags == [] and h.min_age is None
    assert world.priced == []  # no events, so nothing to price


def test_group_page_prices_every_event_and_attaches_images_once(monkeypatch, world):
    url = "https://www.meetup.com/la-hiking/events/"
    serve(monkeypatch, world, url, saved("meetup"))
    classify_as(monkeypatch, world, "hike", ["hiking"])
    attached = []
    monkeypatch.setattr(page_images, "attach", lambda hints, html, base: attached.append((len(hints), base)))
    g, hints = read_and_prepare(source("event_page", url))
    assert [h.kind for h in hints] == ["event"] * 4
    assert hints[0].event_title == "Mt. Waterman Trail Maintenance"
    assert hints[0].category == "hike" and hints[0].tags == ["hiking"]
    assert attached == [(4, url)]
    assert world.priced == [(4, url)]  # none had a price: the price step ran on the listing page
    assert all(h.min_age is None for h in hints)  # several events share the text, so no age is set


def test_page_with_no_structured_data_goes_through_the_model(monkeypatch, world):
    url = "https://example.com/plain"
    html = ("<html><head><title>Rooftop night</title></head><body><main><p>Join us on the roof at Perch LA, "
            "448 South Hill Street, Los Angeles on 2026-10-31 at 20:00. Ages 21+ only. Tickets $25.</p>"
            "</main></body></html>")
    serve(monkeypatch, world, url, html)
    attached = []
    monkeypatch.setattr(page_images, "attach", lambda hints, html, base: attached.append((len(hints), base)))
    answer_with(monkeypatch, world, {"is_list": False, "items": [{
        "kind": "event", "name": "Perch LA", "event_title": "Rooftop night", "specific": True,
        "address": "448 South Hill Street", "area": "Los Angeles", "inside": None, "category": "nightlife",
        "description": "A night on the roof.", "start_date": "2026-10-31", "start_time": "20:00",
        "end_date": None, "end_time": None, "recurrence": None, "price_text": None, "price_min": 25,
        "price_max": 25, "is_free": None, "tags": ["rooftop"]}]})
    g, hints = read_and_prepare(source("event_page", url))
    (h,) = hints
    assert (h.kind, h.name, h.event_title, h.provider) == ("event", "Perch LA", "Rooftop night", "llm")
    assert h.starts_at == datetime(2026, 10, 31, 20, tzinfo=h.starts_at.tzinfo) and h.starts_at.utcoffset().total_seconds() == -7 * 3600
    assert h.price_min == 25.0 and h.price_max == 25.0 and h.flags == []
    assert h.min_age == 21  # the age step read "Ages 21+" in the page text
    assert attached == [(1, url)]
    assert world.priced == []  # the price is there
    assert world.asked[0].startswith("You read social media posts")


def test_page_without_text_is_unprocessable(monkeypatch, world):
    url = "https://example.com/empty"
    serve(monkeypatch, world, url, "<html><head><title>x</title></head><body></body></html>")
    with pytest.raises(pipeline.Unprocessable):
        read_and_prepare(source("event_page", url))


@pytest.mark.parametrize("status,words", [(403, "blocks automated readers"), (404, "has no page there"),
                                          (451, "refused the page")])
def test_page_errors_are_permanent(monkeypatch, world, status, words):
    def fetch(u, client=None):
        raise httpx.HTTPStatusError("x", request=httpx.Request("GET", u), response=httpx.Response(status))
    monkeypatch.setattr(pipeline, "fetch_text", fetch)
    with pytest.raises(pipeline.Unprocessable, match=words):
        read_and_prepare(source("event_page", "https://example.com/x"))


def test_text_note_is_read_by_the_model_then_dateless_event_becomes_a_place(monkeypatch, world):
    caption = "Try Graveline Tours in Los Angeles, a haunted walk. Must be 21 or older."
    answer_with(monkeypatch, world, {"is_list": False, "items": [{
        "kind": "event", "name": "Graveline Tours", "event_title": None, "specific": True, "address": None,
        "area": "Los Angeles", "inside": None, "category": "activity", "description": "A haunted walk.",
        "start_date": None, "start_time": None, "end_date": None, "end_time": None, "recurrence": None,
        "price_text": None, "price_min": None, "price_max": None, "is_free": None, "tags": ["haunted"]}]})
    src = source("text", caption=caption)
    g, hints = read_and_prepare(src)
    (h,) = hints
    assert (h.kind, h.name) == ("place", "Graveline Tours")  # no date, so it is a place
    assert "event with no date" not in h.flags
    assert src.title == caption[:140]
    assert world.priced == []  # no event left to price


def test_demote_runs_on_a_home_page(monkeypatch, world):
    url = "https://museum.example.com/"
    html = ("<html><head><title>Museum</title></head><body><main><p>The museum offers cup candle making and "
            "film editing workshops all year round at its Wilshire building.</p></main></body></html>")
    serve(monkeypatch, world, url, html)

    def item(title):
        return {"kind": "event", "name": "Academy Museum", "event_title": title, "specific": True, "address": None,
                "area": "Los Angeles", "inside": None, "category": "class", "description": None, "start_date": None,
                "start_time": None, "end_date": None, "end_time": None, "recurrence": None, "price_text": None,
                "price_min": None, "price_max": None, "is_free": None, "tags": []}
    answer_with(monkeypatch, world, {"is_list": True, "items": [item("Cup Candle Making"), item("Film Editing")]})
    monkeypatch.setattr(page_images, "attach", lambda *a: None)
    g, hints = read_and_prepare(source("event_page", url))
    assert [(h.kind, h.name) for h in hints] == [("place", "Academy Museum")]
    assert hints[0].description == "Offers: Cup Candle Making; Film Editing"


def test_maps_link_becomes_a_place_and_is_classified(monkeypatch, world):
    from app.ingest import maps_links
    hint = maps_links.MapsHint(name="Perch LA", address="448 S Hill St", lat=34.05, lon=-118.25, exact_pin=True)
    monkeypatch.setattr(maps_links, "expand_and_parse", lambda url: ("https://maps.example/final", hint))
    classify_as(monkeypatch, world, "bar", ["rooftop"])
    src = source("gmaps", "https://maps.app.goo.gl/x")
    g, hints = read_and_prepare(src)
    (h,) = hints
    assert (h.kind, h.name, h.provider, h.exact_pin) == ("place", "Perch LA", "maps_link", True)
    assert h.category == "bar" and h.tags == ["rooftop"]
    assert src.raw["maps_url"] == "https://maps.example/final" and src.title == "Perch LA"


def test_browser_rendered_page_with_several_items_gets_page_images_too(monkeypatch, world):
    url = "https://www.meetup.com/la-hiking/events/"
    serve(monkeypatch, world, url, "<html><head><title>Hiking</title></head><body></body></html>")
    rendered = saved("meetup")
    monkeypatch.setattr(browser, "available", lambda: True)
    monkeypatch.setattr(browser, "render", lambda u: (u + "?rendered", rendered))
    classify_as(monkeypatch, world, "hike", ["hiking"])
    seen = []
    monkeypatch.setattr(page_images, "attach", lambda hints, html, base: seen.append((len(hints), html, base)))
    g, hints = read_and_prepare(source("event_page", url))
    assert [h.kind for h in hints] == ["event"] * 4 and hints[0].category == "hike"
    assert seen == [(4, rendered, url + "?rendered")]  # the rendered html and its url, as for a plain page


def test_browser_rendered_page_with_one_item_attaches_nothing(monkeypatch, world):
    url = "https://example.com/eventbrite"
    serve(monkeypatch, world, url, "<html><head><title>Jazz</title></head><body></body></html>")
    monkeypatch.setattr(browser, "available", lambda: True)
    monkeypatch.setattr(browser, "render", lambda u: (u, saved("eventbrite")))
    classify_as(monkeypatch, world, "live_music", ["jazz"])
    monkeypatch.setattr(page_images, "attach", lambda *a: pytest.fail("one item has no neighbors to match"))
    g, hints = read_and_prepare(source("event_page", url))
    assert [(h.kind, h.event_title) for h in hints] == [("event", "Jazz Eclectic LA")]
