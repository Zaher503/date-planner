from datetime import datetime, timezone

from sqlalchemy.dialects import postgresql

from app.api.filters import event_conditions, event_ended, parse_filters

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


def test_seasonal_run_with_until_archives_after_it_closes():
    rule = "FREQ=DAILY;UNTIL=20261018T235959"
    assert ended(starts_at=datetime(2026, 10, 25, tzinfo=timezone.utc), is_recurring=True, rrule=rule)
    assert not ended(starts_at=datetime(2026, 10, 25, tzinfo=timezone.utc), is_recurring=True,
                     rrule="FREQ=DAILY;UNTIL=20261031T235959")
    assert not ended(starts_at=datetime(2026, 10, 25, tzinfo=timezone.utc), is_recurring=True, rrule="FREQ=DAILY")


def test_world_sized_bbox_skips_the_geography_prefilter():
    from sqlalchemy import and_, func

    from app.api.filters import common_conditions
    from app.db.models import Place

    def where(bbox):
        f = parse_filters(bbox=bbox, now=NOW)
        conds = common_conditions(Place, f, func.ST_X(Place.geom), func.ST_Y(Place.geom), None)
        return str(and_(*conds).compile(dialect=postgresql.dialect()))

    assert "&&" in where("-118.5,33.9,-118.1,34.2")
    assert "&&" not in where("-180,-85,180,85")


# Runs that are on now (an exhibition that opened last year) sort and show as "on now", not by opening date

def test_exhibition_that_opened_long_ago_is_on_now():
    from app.lifecycle import event_ongoing
    assert event_ongoing(start=datetime(2025, 3, 23, 7, tzinfo=timezone.utc),
                         end=datetime(2027, 10, 25, 6, 59, tzinfo=timezone.utc), now=NOW)
    assert event_ongoing(start=None, end=datetime(2027, 1, 10, tzinfo=timezone.utc), now=NOW)  # closing date only


def test_short_running_closed_or_future_events_are_not_on_now():
    from app.lifecycle import event_ongoing
    # A concert that started an hour ago keeps its time
    assert not event_ongoing(start=datetime(2026, 10, 23, 11, tzinfo=timezone.utc),
                             end=datetime(2026, 10, 23, 14, tzinfo=timezone.utc), now=NOW)
    assert not event_ongoing(start=datetime(2025, 3, 23, tzinfo=timezone.utc),
                             end=datetime(2026, 10, 19, tzinfo=timezone.utc), now=NOW)  # closed
    assert not event_ongoing(start=datetime(2026, 12, 1, tzinfo=timezone.utc),
                             end=datetime(2027, 3, 1, tzinfo=timezone.utc), now=NOW)  # not open yet
    assert not event_ongoing(start=datetime(2025, 3, 23, tzinfo=timezone.utc), end=None, now=NOW)


def _row(title, start=None, ends=None, ongoing=False):
    from types import SimpleNamespace
    return ({"t": "event", "title": title, "start": start and start.isoformat(), "ongoing": ongoing},
            SimpleNamespace(start=start, ends_at=ends, created_at=NOW))


def test_date_sort_puts_upcoming_before_on_now_runs():
    from app.api.map import sort_items
    items = [
        _row("Bong Joon Ho", datetime(2025, 3, 23, tzinfo=timezone.utc), datetime(2027, 10, 25, tzinfo=timezone.utc), True),
        _row("Ponyo", datetime(2026, 2, 14, tzinfo=timezone.utc), datetime(2027, 3, 22, tzinfo=timezone.utc), True),
        _row("Workshop"),
        _row("Concert", datetime(2026, 11, 20, tzinfo=timezone.utc)),
        ({"t": "place", "title": "Academy Museum", "start": None}, None),
    ]
    assert [p["title"] for p in sort_items(items, "date")] == ["Concert", "Ponyo", "Bong Joon Ho", "Workshop",
                                                               "Academy Museum"]


def test_venue_page_lists_coming_then_on_now_then_undated_then_past():
    import uuid
    from types import SimpleNamespace

    from app.api.items import place_events

    def ev(title, start=None, end=None, **kw):
        base = dict(id=uuid.uuid4(), title=title, starts_at=start, ends_at=end, status="scheduled", duration_min=None,
                    all_day=True, rrule=None, recurrence_text=None)
        return SimpleNamespace(**{**base, **kw})

    weekly = ev("Weekly talk", datetime(2025, 1, 7, tzinfo=timezone.utc), rrule="FREQ=WEEKLY;BYDAY=TU",
                recurrence_text="every Tuesday")
    events = [ev("Bong Joon Ho", datetime(2025, 3, 23, tzinfo=timezone.utc), datetime(2027, 10, 25, tzinfo=timezone.utc)),
              ev("Ponyo", datetime(2026, 2, 14, tzinfo=timezone.utc), datetime(2027, 3, 22, tzinfo=timezone.utc)),
              ev("Barbie", None, datetime(2026, 10, 19, tzinfo=timezone.utc)),
              ev("Workshop", recurrence_text="third Friday of every month"),
              ev("Film night", datetime(2026, 11, 1, 3, tzinfo=timezone.utc), all_day=False),
              weekly]
    upcoming = {weekly.id: (17, datetime(2026, 10, 27, tzinfo=timezone.utc))}
    rows = place_events(events, upcoming, NOW)
    assert [r[0].title for r in rows] == ["Weekly talk", "Film night", "Ponyo", "Bong Joon Ho", "Workshop", "Barbie"]
    flags = {r[0].title: (r[2], r[3]) for r in rows}
    assert flags["Bong Joon Ho"] == (True, False) and flags["Barbie"] == (False, True)
    assert flags["Weekly talk"] == (False, False) and rows[0][1] == datetime(2026, 10, 27, tzinfo=timezone.utc)
