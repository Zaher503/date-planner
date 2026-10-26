import uuid
from datetime import datetime, time, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app import occurrences, watch
from app.api.items import EventPatch, PlacePatch, _after_watch_change, patch_changes
from app.ingest import completeness

NOW = datetime(2026, 10, 26, 18, 0, tzinfo=timezone.utc)


def venue(**kw):
    base = dict(name="Academy Museum", standing=True, watch_source_id=uuid.uuid4(), watch_every_days=7,
                last_scanned_at=None, last_scan_status=None, last_scan_note=None, watch_url=None, website=None,
                watch_parser=None)
    return SimpleNamespace(**{**base, **kw})


def event(**kw):
    base = dict(id=uuid.uuid4(), recurrence_text="every Tuesday at 6pm", rrule=None, starts_at=None, ends_at=None,
                all_day=False, duration_min=None, duration_estimated=False, tz="America/Los_Angeles",
                listed=True, status="scheduled", user_overrides={})
    return SimpleNamespace(**{**base, **kw})


def test_never_scanned_venue_is_due():
    assert watch.is_due(venue(), NOW)


def test_weekly_venue_is_due_after_seven_days_not_before():
    assert not watch.is_due(venue(last_scanned_at=NOW - timedelta(days=5)), NOW)
    assert watch.is_due(venue(last_scanned_at=NOW - timedelta(days=7)), NOW)
    assert watch.is_due(venue(last_scanned_at=NOW - timedelta(days=6, hours=23)), NOW)  # a little early is fine


def test_not_standing_or_without_a_page_is_never_due():
    assert not watch.is_due(venue(standing=False), NOW)
    assert not watch.is_due(venue(watch_source_id=None), NOW)
    assert watch.next_scan(venue(standing=False)) is None


def test_next_scan_is_one_interval_after_the_last():
    last = NOW - timedelta(days=2)
    assert watch.next_scan(venue(last_scanned_at=last, watch_every_days=14)) == last + timedelta(days=14)


def run_after(monkeypatch, places, result=None, error=None):
    calls = []
    monkeypatch.setattr(watch, "_watchers", lambda db, src: places)
    monkeypatch.setattr(watch, "reconcile", lambda db, p, s, seen, now: calls.append(seen) or (0, 2))
    db = SimpleNamespace(commit=lambda: None)
    watch.after_run(db, SimpleNamespace(id="s"), result, error, NOW)
    return calls


def test_successful_scan_records_events_and_unlists_the_missing(monkeypatch):
    p = venue()
    eid = str(uuid.uuid4())
    calls = run_after(monkeypatch, [p], {"items": [{"type": "event", "id": eid}, {"type": "place", "id": "x"}]})
    assert calls == [{uuid.UUID(eid)}]
    assert p.last_scan_status == "ok" and "1 events listed" in p.last_scan_note and "2 no longer listed" in p.last_scan_note
    assert p.last_scanned_at == NOW


def test_scan_that_finds_no_events_keeps_everything(monkeypatch):
    p = venue()
    calls = run_after(monkeypatch, [p], {"items": [{"type": "place", "id": "x"}]})
    assert calls == [] and p.last_scan_status == "no_events"


def test_failed_scan_is_recorded_and_unlists_nothing(monkeypatch):
    p = venue()
    assert run_after(monkeypatch, [p], {"error": "no place or event found in this link"}) == []
    assert p.last_scan_status == "failed" and "no place or event" in p.last_scan_note
    q = venue()
    assert run_after(monkeypatch, [q], None, error="Unprocessable: HTTP 403") == []
    assert q.last_scan_status == "failed" and q.last_scanned_at == NOW


def test_apply_rule_sets_the_rule_and_the_first_date():
    e = event()
    assert occurrences.apply_rule(e, NOW) is True
    assert e.rrule == "FREQ=WEEKLY;BYDAY=TU"
    assert (e.starts_at.month, e.starts_at.day, e.starts_at.hour) == (10, 27, 18) and not e.all_day
    assert e.duration_min == occurrences.DEFAULT_MINUTES


def test_rule_without_a_time_is_all_day_and_asks_for_a_check():
    e = event(recurrence_text="third Friday of every month", place_id="p", address_text="x", title="t",
              ticket_url=None, is_free=None, price_min=None, price_text=None, description=None)
    occurrences.apply_rule(e, NOW)
    assert e.rrule == "FREQ=MONTHLY;BYDAY=3FR" and e.all_day and e.starts_at.weekday() == 4
    g = completeness.event_gaps(e)
    assert g["needed"] == [] and any("start time" in c for c in g["check"])


def test_vague_wording_sets_no_rule():
    e = event(recurrence_text="Weekly")
    assert occurrences.apply_rule(e, NOW) is False and e.rrule is None and e.starts_at is None


def test_existing_date_is_kept_as_the_anchor():
    start = datetime(2026, 11, 3, 18, tzinfo=timezone.utc)
    e = event(starts_at=start)
    occurrences.apply_rule(e, NOW)
    assert e.starts_at == start and e.rrule


def test_refresh_does_nothing_for_unlisted_or_non_repeating_events():
    db = SimpleNamespace()
    assert occurrences.refresh(db, event(rrule=None)) == 0
    assert occurrences.refresh(db, event(rrule="FREQ=DAILY", starts_at=NOW, listed=False)) == 0
    assert occurrences.refresh(db, event(rrule="FREQ=DAILY", starts_at=NOW, status="archived")) == 0


def sent(model, body):
    data = model.model_validate(body)
    return {k: getattr(data, k) for k in data.model_fields_set}


def test_watch_settings_are_patchable_and_validated():
    cols = patch_changes("place", sent(PlacePatch, {"standing": True, "watch_every_days": 14,
                                                   "watch_url": " https://www.academymuseum.org/en/calendar "}))
    assert cols == {"standing": True, "watch_every_days": 14, "watch_url": "https://www.academymuseum.org/en/calendar"}
    for bad in ({"watch_every_days": 0}, {"watch_every_days": 91}):
        with pytest.raises(Exception):
            PlacePatch.model_validate(bad)
    for bad in ({"standing": None}, {"watch_every_days": None}):
        with pytest.raises(HTTPException):
            patch_changes("place", sent(PlacePatch, bad))


def test_event_rrule_is_patchable():
    assert patch_changes("event", sent(EventPatch, {"rrule": "FREQ=WEEKLY;BYDAY=TU"})) == {"rrule": "FREQ=WEEKLY;BYDAY=TU"}


def test_standing_without_any_page_is_refused():
    p = venue(watch_source_id=None, website=None, watch_url=None)
    with pytest.raises(HTTPException) as e:
        _after_watch_change(SimpleNamespace(), p, {"standing"}, SimpleNamespace(id=1))
    assert e.value.status_code == 400


def test_standing_uses_the_website_when_there_is_no_watch_link(monkeypatch):
    seen = []
    monkeypatch.setattr(watch, "attach", lambda db, place, url, uid: seen.append(url))
    p = venue(watch_source_id=None, website="https://www.academymuseum.org/")
    _after_watch_change(SimpleNamespace(), p, {"standing"}, SimpleNamespace(id=1))
    assert seen == ["https://www.academymuseum.org/"]


class Rows(list):
    def all(self):
        return list(self)


def test_reconcile_unlists_missing_relists_returned_and_respects_hand_set_status():
    kept = event(id=uuid.uuid4(), last_seen_at=None)
    gone = event(id=uuid.uuid4())
    by_hand = event(id=uuid.uuid4(), user_overrides={"status": True}, status="scheduled")
    back = event(id=uuid.uuid4(), listed=False, status="archived")
    cancelled = event(id=uuid.uuid4(), status="cancelled")
    linked = Rows([kept, gone, by_hand, back, cancelled])
    answers = iter([linked, Rows([kept, back])])
    db = SimpleNamespace(scalars=lambda q: next(answers))
    relisted, unlisted = watch.reconcile(db, SimpleNamespace(id="p"), SimpleNamespace(id="s"), {kept.id, back.id}, NOW)
    assert (relisted, unlisted) == (1, 3)
    assert gone.listed is False and gone.status == "archived"
    assert by_hand.listed is False and by_hand.status == "scheduled"  # unlisted, but not archived over a manual status
    assert cancelled.listed is False and cancelled.status == "cancelled"
    assert back.listed is True and back.status == "scheduled" and back.last_seen_at == NOW
    assert kept.last_seen_at == NOW
