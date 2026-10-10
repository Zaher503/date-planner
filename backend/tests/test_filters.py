from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException

from app.api.common import event_price_label, image_url, place_price_label
from app.api.filters import parse_filters, time_window

LA = ZoneInfo("America/Los_Angeles")


def at(*args) -> datetime:
    return datetime(*args, tzinfo=LA)


def window(when: str, now: datetime, **kw):
    return time_window(when, now, LA, **kw)


def test_today_and_tomorrow_are_local_days():
    now = at(2026, 10, 10, 23, 30)  # Saturday night in LA, already Sunday in UTC
    assert window("today", now) == (at(2026, 10, 10), at(2026, 10, 11))
    assert window("tomorrow", now) == (at(2026, 10, 11), at(2026, 10, 12))


def test_today_from_utc_now():
    now = datetime(2026, 10, 11, 5, 0, tzinfo=ZoneInfo("UTC"))  # 22:00 Saturday in LA
    assert window("today", now) == (at(2026, 10, 10), at(2026, 10, 11))


@pytest.mark.parametrize("now", [at(2026, 10, 5, 9), at(2026, 10, 8, 23, 59)])  # Monday, Thursday
def test_weekend_midweek_is_coming_friday(now):
    assert window("weekend", now) == (at(2026, 10, 9, 17), at(2026, 10, 12))


@pytest.mark.parametrize("now", [at(2026, 10, 9, 8), at(2026, 10, 9, 20), at(2026, 10, 10, 12),
                                 at(2026, 10, 11, 23, 30)])  # Friday morning and night, Saturday, Sunday
def test_weekend_during_weekend_is_current(now):
    assert window("weekend", now) == (at(2026, 10, 9, 17), at(2026, 10, 12))


def test_weekend_on_monday_moves_on():
    assert window("weekend", at(2026, 10, 12, 0, 5)) == (at(2026, 10, 16, 17), at(2026, 10, 19))


def test_weekend_across_dst_end():
    # DST ends Sunday 2026-11-01; the window still ends at local Monday midnight
    start, end = window("weekend", at(2026, 10, 29, 12))
    assert start == at(2026, 10, 30, 17) and end == at(2026, 11, 2)
    assert end.utcoffset() == timedelta(hours=-8)


def test_week_and_month_are_relative_to_now():
    now = at(2026, 10, 10, 15)
    assert window("week", now) == (now, now + timedelta(days=7))
    assert window("month", now) == (now, now + timedelta(days=31))


def test_range_is_inclusive_days():
    assert window("range", at(2026, 10, 10), start=date(2026, 10, 12), end=date(2026, 10, 13)) == \
        (at(2026, 10, 12), at(2026, 10, 14))
    assert window("range", at(2026, 10, 10), start=date(2026, 10, 12)) == (at(2026, 10, 12), at(2026, 10, 13))


@pytest.mark.parametrize("kw", [{}, {"start": date(2026, 10, 12), "end": date(2026, 10, 11)}])
def test_range_errors(kw):
    with pytest.raises(HTTPException):
        window("range", at(2026, 10, 10), **kw)


def test_parse_full():
    f = parse_filters(bbox="-118.5,33.9,-118.1,34.2", types="event", when="weekend", open_now="1",
                      price="free,2", tags="rooftop, views", cats="food", status="want,review",
                      near="34.05,-118.25", dist_km="12.5", q="  jazz  ", past="0", now=at(2026, 10, 7, 12))
    assert f.bbox == (-118.5, 33.9, -118.1, 34.2)
    assert f.types == ("event",)
    assert f.window == (at(2026, 10, 9, 17), at(2026, 10, 12))
    assert f.open_now and not f.past
    assert f.price == {"free", "2"} and f.tags == ["rooftop", "views"] and f.cats == ["food"]
    assert f.status == {"want", "review"}
    assert f.near == (34.05, -118.25) and f.dist_km == 12.5 and f.q == "jazz"


def test_parse_defaults():
    f = parse_filters(now=at(2026, 10, 7, 12))
    assert f.types == ("place", "event") and f.window is None and f.bbox is None
    assert not f.price and not f.status and f.q is None


def test_parse_range_dates():
    f = parse_filters(when="range", from_="2026-10-20", to="2026-10-21", now=at(2026, 10, 7, 12))
    assert f.window == (at(2026, 10, 20), at(2026, 10, 22))


@pytest.mark.parametrize("kw", [
    {"bbox": "1,2,3"}, {"bbox": "a,b,c,d"}, {"types": "venue"}, {"when": "soon"}, {"price": "4"},
    {"status": "maybe"}, {"near": "34"}, {"dist_km": "-1"}, {"when": "range", "from_": "10/20/2026"},
])
def test_parse_rejects(kw):
    with pytest.raises(HTTPException) as e:
        parse_filters(now=at(2026, 10, 7, 12), **kw)
    assert e.value.status_code == 400


@pytest.mark.parametrize("args,label", [
    ((True, None, None, None), "Free"),
    ((None, 0, None, None), "Free"),
    ((None, 15, None, None), "$15"),
    ((None, 15, 30, None), "$15-30"),
    ((None, 15, 15, None), "$15"),
    ((None, 12.5, None, None), "$12.50"),
    ((None, None, 40, None), "Up to $40"),
    ((None, None, None, "Donation"), "Donation"),
    ((None, None, None, "Tickets from twenty five dollars"), None),
    ((None, None, None, None), None),
])
def test_event_price_label(args, label):
    assert event_price_label(*args) == label


def test_event_price_label_other_currency():
    assert event_price_label(None, 20, None, None, "EUR") == "€20"
    assert event_price_label(None, 20, None, None, "MXN") == "20 MXN"


def test_place_price_label():
    assert [place_price_label(x) for x in (None, 0, 1, 2, 4)] == [None, "Free", "$", "$$", "$$$$"]


def test_image_url():
    assert image_url({"tiktok": {"thumbnail_url": "https://p16.tiktokcdn.com/x.jpg"}}) == "https://p16.tiktokcdn.com/x.jpg"
    assert image_url({"page": {"image": "https://example.com/a.png"}}) == "https://example.com/a.png"
    assert image_url({"page": {"image": None}, "tiktok": {}}) is None
    assert image_url({"page": {"image": "/relative.png"}}) is None
    assert image_url(None) is None
