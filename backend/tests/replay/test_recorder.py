"""The recorder's save and load format, with a fake web and a fake model."""
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from app.replay import Case, load_case, record, replay, save_case

FIX = Path(__file__).parent.parent / "fixtures"
NOW = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
URL = "https://www.perchla.com/"


def fake_web(url):
    if url == URL:
        return URL, (FIX / "page_perch.html").read_text(encoding="utf-8")
    raise httpx.ConnectError("down")


def fake_model(system, user, schema, **kw):
    return {"items": [{"index": 0, "category": "bar", "tags": ["rooftop"]}]}


def test_record_then_replay_gives_the_same_hints(tmp_path):
    case = record(URL, tmp_path / "perch", fake_web, {"extract": fake_model, "pricing": fake_model}, now=NOW)
    folder = tmp_path / "perch"
    assert sorted(p.name for p in folder.iterdir()) == ["case.json", "expected.json", "model.json", "pages"]
    assert (folder / "pages" / "page1.html").read_text(encoding="utf-8").startswith("<html>")
    meta = json.loads((folder / "case.json").read_text(encoding="utf-8"))
    assert meta["kind"] == "event_page" and meta["pages"][URL] == {"final": URL, "file": "page1.html"}
    saved = json.loads((folder / "model.json").read_text(encoding="utf-8"))
    assert [(r["module"], r["answer"]["items"][0]["category"]) for r in saved] == [("extract", "bar")]
    assert saved[0]["system"].startswith("For each numbered place or event")

    loaded = load_case(folder)
    got, tape = replay(loaded)
    assert got == case.expected == loaded.expected
    assert tape.misses == [] and tape.unused == []
    assert got[0]["name"] == "Perch LA" and got[0]["category"] == "bar"


def test_failed_fetches_are_saved_and_replayed_as_failures(tmp_path):
    case = Case(kind="event_page", url=URL, caption=None, now=NOW,
                pages={URL: {"status": 404}, "https://x.example/": {"error": "ConnectError"}})
    save_case(case, tmp_path / "c")
    loaded = load_case(tmp_path / "c")
    assert loaded.pages == case.pages and loaded.model == []
    from app.ingest.pipeline import Unprocessable
    with pytest.raises(Unprocessable, match="has no page there"):
        replay(loaded)


def test_a_call_that_was_not_recorded_is_reported(tmp_path):
    case = Case(kind="event_page", url=URL, caption=None, now=NOW,
                pages={URL: {"final": URL, "file": "page.html"}},
                files={"page.html": (FIX / "page_perch.html").read_text(encoding="utf-8")})
    save_case(case, tmp_path / "c")  # no model answers saved
    loaded = load_case(tmp_path / "c")
    with pytest.raises(AssertionError, match="model answer not in the saved case"):
        replay(loaded)
