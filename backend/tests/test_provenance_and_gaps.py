from datetime import datetime, timezone
from types import SimpleNamespace

from app.ingest import completeness, provenance


def event(**kw):
    base = dict(title="Magic night", starts_at=datetime(2026, 11, 7, 20, tzinfo=timezone.utc), rrule=None,
                recurrence_text=None, place_id="p1", address_text="1 Main St", all_day=False, ends_at=None,
                ticket_url=None, is_free=None, price_min=None, price_text=None, description=None)
    return SimpleNamespace(**{**base, **kw})


def place(**kw):
    base = dict(name="El Cid", address_text="4212 West Sunset Boulevard", website=None, phone=None,
                opening_hours=None, hours_text=None, description=None)
    return SimpleNamespace(**{**base, **kw})


def test_event_without_price_phone_or_ticket_is_not_marked():
    g = completeness.event_gaps(event())
    assert g["needed"] == []
    assert "a price" in g["optional"] and "a ticket link" in g["optional"]
    assert completeness.needs_review(event(), []) is False


def test_event_needs_a_date_or_a_repeat_pattern():
    assert completeness.event_gaps(event(starts_at=None))["needed"] == ["a date, or how often it repeats"]
    assert completeness.event_gaps(event(starts_at=None, recurrence_text="every Tuesday"))["needed"] == []
    assert completeness.event_gaps(event(starts_at=None, rrule="FREQ=WEEKLY;BYDAY=TU"))["needed"] == []
    assert completeness.needs_review(event(starts_at=None), []) is True


def test_ongoing_series_and_assumed_timezone_do_not_mark_an_event():
    flags = ["recurring series, dates unclear", "start time has no time zone"]
    assert completeness.needs_review(event(), flags) is False


def test_dates_that_cannot_be_trusted_do_mark_an_event():
    assert completeness.needs_review(event(), ["removed unverified date"]) is True
    assert completeness.needs_review(event(), ["event already happened"]) is True


def test_place_needs_an_address_but_not_a_phone_or_site():
    assert completeness.needs_review(place(), []) is False
    assert completeness.place_gaps(place(address_text=None))["needed"] == ["an address"]


def test_street_only_address_is_a_check_not_a_review():
    g = completeness.place_gaps(place(address_text="South Union Avenue, Los Angeles"))
    assert g["needed"] == [] and g["check"]
    assert completeness.needs_review(place(address_text="South Union Avenue"), []) is False


def test_stamp_records_engine_and_keeps_earlier_reads_newest_first():
    item = SimpleNamespace(import_info={"importer_version": "unknown", "engine": "legacy", "history": []})
    info = provenance.stamp(item, "llm", "s1")
    assert info["importer_version"] == provenance.IMPORTER_VERSION and info["engine"] == "llm"
    assert info["source_id"] == "s1" and info["model"] and info["prompt_hash"]
    assert info["history"][0]["engine"] == "legacy"
    provenance.stamp(item, "verified")
    assert [h["engine"] for h in item.import_info["history"]] == ["llm", "legacy"]
    assert item.import_info["engine"] == "verified"


def test_parser_reads_have_no_model():
    item = SimpleNamespace(import_info={})
    info = provenance.stamp(item, "parser:academy")
    assert info["model"] is None and info["prompt_hash"] is None


def test_history_is_capped():
    item = SimpleNamespace(import_info={})
    for _ in range(provenance.HISTORY_KEEP + 4):
        provenance.stamp(item, "llm")
    assert len(item.import_info["history"]) == provenance.HISTORY_KEEP


def test_old_or_unrecorded_items_are_outdated():
    assert provenance.is_older({}) and provenance.is_older(None)
    assert provenance.is_older({"importer_version": "2026.01.01-1"})
    assert not provenance.is_older({"importer_version": provenance.IMPORTER_VERSION})
