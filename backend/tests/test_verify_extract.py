from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.llm import verify
from app.llm.extract import to_hint

LA = "America/Los_Angeles"


def test_time_supported():
    assert verify.time_supported("20:00", "Doors at 8pm, show at 9")
    assert verify.time_supported("20:00", "starts 8 PM")
    assert verify.time_supported("20:30", "from 8:30 until late")
    assert verify.time_supported("12:00", "brunch from noon")
    assert not verify.time_supported("21:00", "Doors at 8pm")
    assert not verify.time_supported("20:00", "top 8 rooftops")  # bare number is not a time


def test_date_supported():
    d = date(2026, 10, 17)  # a Saturday
    assert verify.date_supported(d, "Oct 17th at the Bowl")
    assert verify.date_supported(d, "on 10/17")
    assert verify.date_supported(d, "this Saturday only")
    assert verify.date_supported(d, "17 October")
    assert not verify.date_supported(d, "every week, great vibes")
    assert verify.date_supported(date(2026, 9, 18), "runs Sept. 18 through Nov. 1")
    assert verify.date_supported(date(2026, 9, 18), "from 18 Sept")


def test_prices_must_appear():
    nums = verify.numbers_in("Tickets $25-$40, students 15.50")
    assert verify.price_supported(25, nums) and verify.price_supported(15.5, nums)
    assert not verify.price_supported(30, nums)


def raw(**kw):
    base = dict(kind="place", name="", event_title=None, specific=True, address=None, area=None,
                category="bar", description=None, start_date=None, start_time=None, end_date=None,
                end_time=None, recurrence=None, price_text=None, price_min=None, price_max=None,
                is_free=None, tags=[])
    base.update(kw)
    return base


def test_to_hint_strips_invented_numbers():
    text = "Jazz at Zaya this Saturday at 8pm, $20 cover. 515 W 7th St"
    h = to_hint(raw(kind="event", name="Zaya", event_title="Jazz night", start_date="2026-10-17",
                    start_time="20:00", price_min=20, price_max=35, tags=["#Jazz", "LA", "speakeasy"]), text, LA)
    assert h.starts_at == datetime(2026, 10, 17, 20, 0, tzinfo=ZoneInfo(LA))
    assert h.price_min == 20 and h.price_max is None
    assert "removed unverified price max" in h.flags
    assert h.tags == ["jazz", "speakeasy"]


def test_to_hint_overnight_end_and_unverified_date():
    h = to_hint(raw(kind="event", name="Bar", start_date="2026-10-17", start_time="20:00",
                    end_time="01:00"), "Saturday 8pm to 1am", LA)
    assert h.ends_at.day == 18 and h.ends_at.hour == 1
    h2 = to_hint(raw(kind="event", name="Bar", start_date="2026-10-17"), "great party", LA)
    assert h2.starts_at is None and "removed unverified date" in h2.flags and "event with no date" in h2.flags


def test_to_hint_activity_without_venue():
    h = to_hint(raw(name="", area="Venice", specific=False, category="activity"), "bike by the beach in Venice", LA)
    assert h.name == "Venice" and "not a specific venue" in h.flags
    assert to_hint(raw(name="", area=None), "x", LA) is None
    assert to_hint(raw(name="null", area="none"), "x", LA) is None


def test_to_hint_ignores_model_specific_flag_for_named_venue():
    h = to_hint(raw(name="El Matador Beach", specific=False, is_free=False), "10. El Matador Beach", LA)
    assert "not a specific venue" not in h.flags
    assert h.is_free is None  # no price in the text, so unknown


def test_address_must_come_from_text():
    assert verify.address_supported("515 W 7th St", "Zaya | 515 W 7th St, Los Angeles")
    assert not verify.address_supported("2375 Glendale Blvd", "7. La Cha Cha Cha - a rooftop in the Arts District")
    assert not verify.address_supported("812 Sunset Blvd", "812 E 3rd St")  # number right, street wrong
    assert verify.address_supported("Sunset Blvd", "anything")
    h = to_hint(raw(name="La Cha Cha Cha", address="2375 Glendale Blvd"), "La Cha Cha Cha rooftop", LA)
    assert h.address is None and "removed unverified address" in h.flags
