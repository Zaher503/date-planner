from datetime import datetime, timezone

from sqlalchemy.dialects import postgresql

from app.api.filters import archived, event_conditions, event_ended, parse_filters

NOW = datetime(2026, 10, 23, 12, tzinfo=timezone.utc)


def ended(**kw):
    base = dict(status="scheduled", starts_at=None, ends_at=None, duration_min=None, all_day=False,
                is_recurring=False, now=NOW)
    return event_ended(**{**base, **kw})


def test_past_one_off_is_archived():
    assert ended(starts_at=datetime(2025, 11, 8, 21, 30, tzinfo=timezone.utc),
                 ends_at=datetime(2025, 11, 9, 2, tzinfo=timezone.utc))


def test_future_and_running_events_are_not():
    assert not ended(starts_at=datetime(2026, 11, 8, 21, tzinfo=timezone.utc))
    # No end given: three hours after the start still counts as running
    assert not ended(starts_at=datetime(2026, 10, 23, 10, tzinfo=timezone.utc))
    assert ended(starts_at=datetime(2026, 10, 23, 8, tzinfo=timezone.utc))


def test_duration_and_all_day_ends():
    start = datetime(2026, 10, 22, 20, tzinfo=timezone.utc)
    assert ended(starts_at=start, duration_min=60)
    assert not ended(starts_at=datetime(2026, 10, 22, 20, tzinfo=timezone.utc), all_day=True)  # a day long


def test_recurring_undated_and_manual_archive():
    old = datetime(2024, 1, 1, tzinfo=timezone.utc)
    assert not ended(starts_at=old, is_recurring=True)
    assert not ended(starts_at=None)
    assert not ended(starts_at=None, ends_at=datetime(2027, 2, 28, tzinfo=timezone.utc))
    assert ended(starts_at=None, status="archived")
    assert ended(starts_at=datetime(2030, 1, 1, tzinfo=timezone.utc), status="archived")


def test_exhibition_with_only_a_closing_date_ages_out():
    assert ended(starts_at=None, ends_at=datetime(2026, 10, 18, tzinfo=timezone.utc), all_day=True)
    assert not ended(starts_at=None, ends_at=datetime(2026, 10, 18, tzinfo=timezone.utc), is_recurring=True)


def test_naive_times_do_not_crash():
    assert ended(starts_at=datetime(2025, 1, 1, 20), ends_at=datetime(2025, 1, 1, 23))


def sql(f):
    return str(postgresql.dialect().statement_compiler(postgresql.dialect(), None)
               .process(__import__("sqlalchemy").and_(*event_conditions(f)))) if event_conditions(f) else ""


def test_filters_pick_the_archive():
    default = parse_filters(now=NOW)
    past = parse_filters(past="1", now=NOW)
    only = parse_filters(archive="1", types="place", now=NOW)
    assert only.archive and only.types == ("event",)  # the Archive is events only
    assert len(event_conditions(default)) == 1 and not event_conditions(past)
    assert sql(default).startswith("NOT (") and not sql(only).startswith("NOT")
    assert "events.status" in sql(only)
