from datetime import datetime

import pytest

from app.hours import is_open, parse

# 2026-10-05 is a Monday
MON, TUE, WED, THU, FRI, SAT, SUN = (datetime(2026, 10, d) for d in range(5, 12))


def at(day: datetime, hhmm: str) -> datetime:
    h, m = map(int, hhmm.split(":"))
    return day.replace(hour=h, minute=m)


def test_always_open():
    assert is_open("24/7", at(SUN, "03:00")) is True


@pytest.mark.parametrize("spec", [None, "", "   ", "sunrise-sunset", "Jan-Mar 10:00-18:00", "Mo-Fr 9am-5pm",
                                  "Monday-Friday 09:00-17:00", "Mo-Fr 25:00-26:00", "PH off", "Mo-Fr 10:00+",
                                  "week 1-20 Mo 10:00-12:00"])
def test_unknown(spec):
    assert is_open(spec, at(MON, "12:00")) is None


def test_weekday_range():
    spec = "Mo-Fr 09:00-17:00"
    assert is_open(spec, at(WED, "09:00")) is True
    assert is_open(spec, at(WED, "16:59")) is True
    assert is_open(spec, at(WED, "17:00")) is False
    assert is_open(spec, at(WED, "08:59")) is False
    assert is_open(spec, at(SAT, "12:00")) is False


def test_day_list_and_several_rules():
    spec = "Mo-Fr 11:00-22:00; Sa,Su 10:00-23:00"
    assert is_open(spec, at(SAT, "10:30")) is True
    assert is_open(spec, at(SUN, "22:30")) is True
    assert is_open(spec, at(MON, "10:30")) is False


def test_later_rule_overrides_same_day():
    spec = "Mo-Su 10:00-20:00; We off"
    assert is_open(spec, at(WED, "12:00")) is False
    assert is_open(spec, at(THU, "12:00")) is True
    assert is_open("Mo-Su 10:00-20:00; Fr 12:00-14:00", at(FRI, "11:00")) is False
    assert is_open("Mo-Su 10:00-20:00; Fr closed", at(FRI, "11:00")) is False


def test_mixed_list_with_ranges():
    spec = "Mo off; Tu-We,Fr 11:00-17:00; Th 11:00-20:00; Sa-Su 11:00-18:00"
    assert is_open(spec, at(MON, "12:00")) is False
    assert is_open(spec, at(TUE, "12:00")) is True
    assert is_open(spec, at(FRI, "16:00")) is True
    assert is_open(spec, at(THU, "19:30")) is True
    assert is_open(spec, at(FRI, "19:30")) is False


def test_split_shifts():
    spec = "Mo-Fr 11:30-14:30,17:30-22:00"
    assert is_open(spec, at(TUE, "12:00")) is True
    assert is_open(spec, at(TUE, "15:00")) is False
    assert is_open(spec, at(TUE, "18:00")) is True


def test_past_midnight():
    spec = "Mo 16:00-01:00; Tu 16:00-01:00; We 16:00-01:00; Th 16:00-01:00; Fr 16:00-01:30; Sa 10:00-01:30; Su 10:00-01:00"
    assert is_open(spec, at(TUE, "00:30")) is True   # Monday's late night
    assert is_open(spec, at(TUE, "01:00")) is False
    assert is_open(spec, at(SAT, "01:15")) is True   # Friday until 01:30
    assert is_open(spec, at(MON, "00:45")) is True   # Sunday until 01:00
    assert is_open(spec, at(MON, "12:00")) is False
    assert is_open("Fr-Sa 18:00-02:00", at(SUN, "01:00")) is True
    assert is_open("Fr-Sa 18:00-02:00", at(MON, "01:00")) is False


def test_spill_over_survives_next_day_off():
    spec = "Sa 20:00-03:00; Su off"
    assert is_open(spec, at(SUN, "02:00")) is True
    assert is_open(spec, at(SUN, "12:00")) is False


def test_holiday_rules_ignored():
    spec = "Mo-Fr 09:00-17:00; PH off"
    assert is_open(spec, at(MON, "10:00")) is True
    assert is_open("Mo-Fr,PH 09:00-17:00", at(TUE, "10:00")) is True
    assert is_open("Mo-Sa 10:00-18:00; SH Mo-Fr 10:00-14:00", at(TUE, "16:00")) in (True, None)


def test_additional_rule_after_comma():
    spec = "Mo-Fr 08:00-12:00, We 14:00-18:00"
    assert is_open(spec, at(WED, "15:00")) is True
    assert is_open(spec, at(WED, "10:00")) is True
    assert is_open(spec, at(TUE, "15:00")) is False


def test_no_day_selector_means_every_day():
    assert is_open("10:00-22:00", at(SUN, "21:00")) is True
    assert is_open("10:00-22:00", at(SUN, "23:00")) is False


def test_wrapping_day_range_and_whitespace():
    spec = "Fr-Mo 12:00 - 18:00"
    assert is_open(spec, at(SUN, "13:00")) is True
    assert is_open(spec, at(MON, "13:00")) is True
    assert is_open(spec, at(TUE, "13:00")) is False


def test_day_only_rule_and_24h():
    assert is_open("Sa-Su", at(SAT, "03:00")) is True
    assert is_open("Mo-Fr 00:00-24:00", at(THU, "23:59")) is True
    assert is_open("Mo-Fr 00:00-24:00", at(SAT, "00:01")) is False


def test_comment_is_ignored():
    assert is_open('Mo-Fr 10:00-16:00 "by appointment"', at(MON, "11:00")) is True
