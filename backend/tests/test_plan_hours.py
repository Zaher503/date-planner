from datetime import datetime, timezone

from app.hours import intervals, is_open, is_open_between, parse

# 2026-10-12 is a Monday
MON, TUE, FRI, SAT, SUN = 12, 13, 16, 17, 18


def at(day: int, hh: int, mm: int = 0) -> datetime:
    return datetime(2026, 10, day, hh, mm)


def test_24_7():
    assert is_open("24/7", at(MON, 3)) is True
    assert is_open_between("24/7", at(FRI, 22), at(SAT, 4)) is True


def test_day_range_and_closed_days():
    spec = "Mo-Fr 09:00-17:00"
    assert is_open(spec, at(MON, 9)) is True
    assert is_open(spec, at(MON, 17)) is False
    assert is_open(spec, at(SAT, 12)) is False


def test_day_list_and_wrapping_range():
    assert is_open("Mo,We,Fr 10:00-12:00", at(TUE, 11)) is False
    assert is_open("Mo,We,Fr 10:00-12:00", at(FRI, 11)) is True
    spec = "Fr-Mo 18:00-22:00"
    assert all(is_open(spec, at(d, 19)) for d in (FRI, SAT, SUN, MON))
    assert is_open(spec, at(TUE, 19)) is False


def test_later_rule_overrides():
    spec = "Mo-Su 11:00-22:00; Su 12:00-20:00; Tu off"
    assert is_open(spec, at(SUN, 11, 30)) is False
    assert is_open(spec, at(SUN, 19)) is True
    assert is_open(spec, at(SUN, 21)) is False
    assert is_open(spec, at(TUE, 15)) is False
    assert is_open(spec, at(MON, 21)) is True


def test_additional_rule_adds():
    spec = "Mo-Fr 09:00-12:00, Sa 10:00-14:00"
    assert is_open(spec, at(SAT, 11)) is True
    assert is_open(spec, at(FRI, 11)) is True
    assert is_open(spec, at(SUN, 11)) is False


def test_split_times():
    spec = "Tu-Su 11:30-14:30,17:00-22:00"
    assert is_open(spec, at(TUE, 12)) is True
    assert is_open(spec, at(TUE, 15)) is False
    assert is_open(spec, at(TUE, 21, 59)) is True
    assert is_open(spec, at(MON, 12)) is False


def test_past_midnight():
    spec = "Mo-Th 17:00-23:00; Fr-Sa 17:00-02:00"
    assert is_open(spec, at(SAT, 1, 30)) is True  # Friday night
    assert is_open(spec, at(SUN, 1, 30)) is True  # Saturday night
    assert is_open(spec, at(FRI, 1, 30)) is False  # Thursday closed at 23:00
    assert is_open("Mo-Su 16:00-01:00", at(TUE, 0, 30)) is True
    assert is_open_between(spec, at(FRI, 22), at(SAT, 1, 45)) is True
    assert is_open_between(spec, at(FRI, 22), at(SAT, 2, 30)) is False


def test_24_00_end_and_days_without_time():
    assert is_open("Mo-Su 08:00-24:00", at(MON, 23, 59)) is True
    assert is_open("Sa-Su", at(SUN, 3)) is True
    assert is_open("Sa-Su", at(MON, 3)) is False


def test_holidays_skipped():
    spec = "Mo-Fr 09:00-17:00; PH off"
    assert is_open(spec, at(MON, 10)) is True
    assert is_open("Mo-Fr,PH 09:00-17:00", at(TUE, 10)) is True


def test_unknown_returns_none():
    for spec in (None, "", "sunrise-sunset", "Jan-Mar Mo 10:00-12:00", "Su[1] 10:00-12:00",
                 '"by appointment"', "10:00+", "Mo-Fr 9am-5pm"):
        assert parse(spec) is None, spec
        assert is_open(spec, at(MON, 10)) is None
        assert is_open_between(spec, at(MON, 10), at(MON, 11)) is None


def test_between_needs_whole_span():
    spec = "Mo-Su 11:00-14:00,17:00-22:00"
    assert is_open_between(spec, at(MON, 18), at(MON, 20)) is True
    assert is_open_between(spec, at(MON, 13), at(MON, 18)) is False
    assert is_open_between(spec, at(MON, 21), at(MON, 22)) is True
    assert is_open_between(spec, at(MON, 21), at(MON, 22, 30)) is False


def test_aware_datetimes_use_local_time():
    # 03:00 UTC Tuesday is 20:00 Monday in Los Angeles
    t = datetime(2026, 10, 13, 3, 0, tzinfo=timezone.utc)
    assert is_open("Mo 19:00-21:00", t) is True


def test_intervals_include_spill_over():
    spans = intervals("Fr 20:00-02:00", datetime(2026, 10, SAT).date())
    assert spans == [(at(FRI, 20), at(SAT, 2))]
