from datetime import datetime, timezone

from app.ingest.items import ItemHint
from app.ingest.pipeline import tidy

NOW = datetime(2026, 10, 10, tzinfo=timezone.utc)


def test_dateless_event_becomes_place():
    h = tidy(ItemHint("event", "Graveline Tours", flags=["event with no date"]), NOW)
    assert h.kind == "place" and "event with no date" not in h.flags


def test_recurring_event_kept():
    h = tidy(ItemHint("event", "Melrose Trading Post", recurrence="every Sunday"), NOW)
    assert h.kind == "event"


def test_long_running_series_is_recurring_not_dated():
    h = tidy(ItemHint("event", "Bar Lis", event_title="Jazz Eclectic LA",
                      starts_at=datetime(2021, 8, 31, tzinfo=timezone.utc),
                      ends_at=datetime(2026, 12, 30, tzinfo=timezone.utc)), NOW)
    assert h.kind == "event" and h.starts_at is None
    assert h.recurrence == "ongoing until 2026-12-30"
    assert "recurring series, dates unclear" in h.flags


def test_event_without_venue_uses_title():
    h = tidy(ItemHint("event", "", event_title="Candlelight Concert",
                      starts_at=datetime(2026, 10, 20, tzinfo=timezone.utc)), NOW)
    assert h.name == "Candlelight Concert" and "not a specific venue" in h.flags
