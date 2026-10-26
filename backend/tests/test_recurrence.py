from datetime import datetime, time, timezone

import pytest

from app import recurrence

LA = "America/Los_Angeles"


@pytest.mark.parametrize("text,rule,when", [
    ("Every Tuesday", "FREQ=WEEKLY;BYDAY=TU", None),
    ("every Tuesday at 6pm", "FREQ=WEEKLY;BYDAY=TU", time(18)),
    ("Weekly on Tuesdays and Thursdays, 7:30 PM", "FREQ=WEEKLY;BYDAY=TU,TH", time(19, 30)),
    ("Fridays 8pm", "FREQ=WEEKLY;BYDAY=FR", time(20)),
    ("Every Other Saturday, 8 PM", "FREQ=WEEKLY;INTERVAL=2;BYDAY=SA", time(20)),
    ("third Friday of every month", "FREQ=MONTHLY;BYDAY=3FR", None),
    ("first Friday of the month at 7pm", "FREQ=MONTHLY;BYDAY=1FR", time(19)),
    ("last Sunday of every month", "FREQ=MONTHLY;BYDAY=-1SU", None),
    ("Every weekday", "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR", None),
    ("Daily 10am", "FREQ=DAILY", time(10)),
    ("Every 12 pm", None, None),
])
def test_parse(text, rule, when):
    got = recurrence.parse(text)
    if rule is None:
        assert got is None
    else:
        assert (got.rrule, got.start_time) == (rule, when)


@pytest.mark.parametrize("text", ["Weekly", "Biweekly", "Monthly", "ongoing until 2027-03-21", "Doors open Friday 8pm",
                                  "Sunset ranch rides", "", None, "Varies by date"])
def test_vague_wording_is_not_guessed(text):
    assert recurrence.parse(text) is None


def test_every_rule_it_writes_is_valid():
    for t in ("every tuesday", "every other saturday", "third friday of every month", "daily", "every weekday"):
        assert recurrence.valid(recurrence.parse(t).rrule)


def test_first_start_is_the_next_matching_day_at_that_time():
    now = datetime(2026, 10, 26, 18, 0, tzinfo=timezone.utc)  # Monday 11am in LA
    got = recurrence.first_start("FREQ=WEEKLY;BYDAY=TU", time(18), LA, now)
    assert (got.year, got.month, got.day, got.hour) == (2026, 10, 27, 18)
    same_day = recurrence.first_start("FREQ=WEEKLY;BYDAY=MO", time(20), LA, now)
    assert (same_day.day, same_day.hour) == (26, 20)


def test_expand_covers_the_horizon_and_keeps_local_time_across_dst():
    anchor = datetime(2026, 10, 27, 18, 0, tzinfo=recurrence.ZoneInfo(LA))
    now = datetime(2026, 10, 26, 20, 0, tzinfo=timezone.utc)
    dates = recurrence.expand("FREQ=WEEKLY;BYDAY=TU", anchor, LA, now=now, days=120)
    assert dates[0].day == 27 and 17 <= len(dates) <= 18
    assert {d.hour for d in dates} == {18}  # 6 pm local before and after the November clock change
    assert dates[0].utcoffset() != dates[-1].utcoffset()


def test_monthly_ordinal_expands_to_the_right_weekday():
    anchor = datetime(2026, 11, 20, 19, 0, tzinfo=recurrence.ZoneInfo(LA))
    now = datetime(2026, 10, 26, 20, 0, tzinfo=timezone.utc)
    dates = recurrence.expand("FREQ=MONTHLY;BYDAY=3FR", anchor, LA, now=now)
    assert [d.day for d in dates] == [20, 18, 15, 19] and all(d.weekday() == 4 for d in dates)
