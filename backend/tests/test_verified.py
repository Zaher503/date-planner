from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api import auth, verified
from app.api.verified import VerifiedItem, check_item, diff_fields, save_item
from app.db.session import get_db
from app.ingest import store
from app.main import app


class Obj(SimpleNamespace):
    """Stands in for a Place or Event row."""


def place(**kw) -> Obj:
    base = dict(id="p1", name="Sunset Ranch Hollywood", category="activity", address_text="3400 Beachwood Dr",
                website=None, phone=None, opening_hours=None, hours_text=None, price_level=None, price_text=None,
                price_tiers=[], description=None, tags=[], user_overrides={}, review_status="ok")
    return Obj(**{**base, **kw})


def test_diff_lists_only_real_changes():
    before = {"phone": None, "website": "https://a.example/", "tags": [], "price_min": Decimal("10.00")}
    after = {"phone": "(323) 469-5450", "website": "https://a.example/", "tags": [], "price_min": 10.0}
    assert diff_fields(before, after) == {"phone": {"before": None, "after": "(323) 469-5450"}}
    assert diff_fields(None, {"name": "X", "phone": None, "tags": []}) == {"name": {"before": None, "after": "X"}}
    t = datetime(2026, 11, 8, 20, tzinfo=timezone.utc)
    assert diff_fields({"starts_at": t}, {"starts_at": t.replace(hour=21)})["starts_at"]["after"].startswith("2026-11-08T21")


def test_check_item_rejects_unusable_values():
    for body in ({"name": "A", "category": "nope"}, {"name": "A", "opening_hours": "daily whenever"},
                 {"name": "A", "lat": 34.0}, {"name": "A", "kind": "event"}, {"name": "A", "website": "ftp://x"}):
        with pytest.raises(HTTPException) as e:
            check_item(VerifiedItem(**body))
        assert e.value.status_code == 400
    check_item(VerifiedItem(name="A", opening_hours="Mo-Fr 09:00-17:00", category="activity"))


def test_user_edits_are_kept_and_other_fields_replaced():
    p = place(phone="(111) 111-1111", website="https://old.example/", user_overrides={"phone": "x"})
    store._set(p, "phone", "(323) 469-5450", overwrite=True)
    store._set(p, "website", "https://new.example/", overwrite=True)
    assert p.phone == "(111) 111-1111" and p.website == "https://new.example/"
    q = place(phone="(111) 111-1111")
    store._set(q, "phone", "(323) 469-5450", overwrite=False)  # a normal import only fills blanks
    assert q.phone == "(111) 111-1111"


def fake_pipeline(monkeypatch, existing, created):
    """The map lookup and the row writes are replaced; what is checked is how save_item uses them."""
    res = SimpleNamespace(best=SimpleNamespace(name="Sunset Ranch Hollywood"), confidence=0.95, method="address",
                          needs_review=False)
    seen = {}
    monkeypatch.setattr(verified.resolver, "resolve", lambda db, hint, home: res)
    monkeypatch.setattr(verified.pipeline, "too_vague", lambda r: False)
    monkeypatch.setattr(verified.store, "_place_name", lambda hint, cand: hint.name)
    monkeypatch.setattr(verified.store, "find_place", lambda db, cand, name: existing)
    monkeypatch.setattr(verified.store, "link", lambda *a, **k: seen.setdefault("links", []).append(k))

    def upsert(db, hint, r, user, existing=None, **_):
        seen["existing"], seen["hint"] = existing, hint
        row = existing or place(id="new")
        store._set(row, "phone", hint.phone, overwrite=existing is not None)
        store._set(row, "website", hint.website, overwrite=existing is not None)
        return row, created
    monkeypatch.setattr(verified.store, "upsert_place", upsert)
    return seen


def run(item: VerifiedItem) -> dict:
    return save_item(None, SimpleNamespace(id="s"), item, 0, (34.0, -118.0), {})


def test_new_place_is_created_and_reported(monkeypatch):
    seen = fake_pipeline(monkeypatch, None, True)
    out = run(VerifiedItem(name="Sunset Ranch Hollywood", phone="(323) 469-5450"))
    assert out["place"]["new"] is True and out["place"]["id"] == "new"
    assert out["place"]["changes"]["phone"]["after"] == "(323) 469-5450"
    assert seen["existing"] is None and seen["links"]


def test_duplicate_is_filled_not_created(monkeypatch):
    existing = place(website="https://sunsetranchhollywood.com/")
    seen = fake_pipeline(monkeypatch, existing, False)
    out = run(VerifiedItem(name="Sunset Ranch Hollywood", phone="(323) 469-5450"))
    assert out["place"]["new"] is False and out["place"]["id"] == "p1"
    assert seen["existing"] is existing  # updated in place, no second row
    assert out["place"]["changes"] == {"phone": {"before": None, "after": "(323) 469-5450"}}
    assert seen["hint"].category == "activity"  # the saved category is not reset


def test_duplicate_wrong_value_is_replaced_but_user_edit_is_kept(monkeypatch):
    existing = place(phone="(000) 000-0000", website="https://wrong.example/", user_overrides={"phone": "x"})
    fake_pipeline(monkeypatch, existing, False)
    out = run(VerifiedItem(name="Sunset Ranch Hollywood", phone="(323) 469-5450",
                           website="https://sunsetranchhollywood.com/"))
    assert existing.phone == "(000) 000-0000"
    assert out["place"]["changes"] == {"website": {"before": "https://wrong.example/",
                                                    "after": "https://sunsetranchhollywood.com/"}}
    assert out["place"]["kept_user_edits"] == ["phone"]


def test_checked_address_replaces_a_different_saved_one(monkeypatch):
    existing = place(address_text="1 Wrong St")
    fake_pipeline(monkeypatch, existing, False)
    run(VerifiedItem(name="Sunset Ranch Hollywood", address="3400 N Beachwood Drive"))
    assert existing.address_text == "3400 N Beachwood Drive"
    kept = place(address_text="1 Wrong St", user_overrides={"address_text": "mine"})
    fake_pipeline(monkeypatch, kept, False)
    run(VerifiedItem(name="Sunset Ranch Hollywood", address="3400 N Beachwood Drive"))
    assert kept.address_text == "1 Wrong St"


def test_unmappable_item_is_reported_not_saved(monkeypatch):
    monkeypatch.setattr(verified.resolver, "resolve", lambda *a: SimpleNamespace(best=None))
    assert run(VerifiedItem(name="Nowhere")) == {"name": "Nowhere", "error": "not found on the map"}


class Session:
    def rollback(self): ...
    def commit(self): ...


def client(monkeypatch, key="secret"):
    monkeypatch.setattr(auth, "get_settings", lambda: SimpleNamespace(dates_key=key))
    app.dependency_overrides[get_db] = lambda: Session()
    return TestClient(app)


BODY = {"url": "https://www.sunsetranchhollywood.com/", "items": [{"name": "Sunset Ranch Hollywood"}]}


def test_endpoint_needs_the_key(monkeypatch):
    c = client(monkeypatch)
    try:
        assert c.post("/api/admin/verified-items", json=BODY).status_code == 401
        assert c.post("/api/admin/verified-items", json=BODY, headers={"X-Dates-Key": "wrong"}).status_code == 401
        unset = client(monkeypatch, key="")
        assert unset.post("/api/admin/verified-items", json=BODY, headers={"X-Dates-Key": ""}).status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_endpoint_rejects_bad_body_with_a_good_key(monkeypatch):
    c = client(monkeypatch)
    try:
        h = {"X-Dates-Key": "secret"}
        bad = {**BODY, "items": [{"name": "A", "opening_hours": "whenever"}]}
        assert c.post("/api/admin/verified-items", json=bad, headers=h).status_code == 400
        assert c.post("/api/admin/verified-items", json={**BODY, "items": []}, headers=h).status_code == 422
        assert c.post("/api/admin/verified-items", json={**BODY, "extra": 1}, headers=h).status_code == 422
    finally:
        app.dependency_overrides.clear()
