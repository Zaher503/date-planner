import uuid
from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api import plans
from app.api.auth import current_user
from app.db.models import Plan
from app.db.session import get_db
from app.main import app
from app.plan.picker import Candidate

ME = SimpleNamespace(id=1, username="zaher", display_name="Zaher")
KATHY = SimpleNamespace(id=2, username="kathy", display_name=None)
STOP = {"item": {"type": "place", "id": "p1", "title": "Perch"}, "arrive": "2026-11-07T19:00:00-08:00",
        "leave": "2026-11-07T20:30:00-08:00", "role": "food", "travel_min": 12.5, "mode": "drive"}
STOP2 = {"item": {"type": "event", "id": "e1", "title": "Jazz night"}, "arrive": "2026-11-07T18:00:00-08:00",
         "leave": "2026-11-07T18:45:00-08:00"}


class Result:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return list(self.rows)

    def __iter__(self):
        return iter(self.rows)


class FakeDB:
    """Just enough Session for the plans routes: one table of plans and two users."""
    def __init__(self):
        self.plans: dict[uuid.UUID, Plan] = {}

    def scalars(self, stmt):
        return Result([ME, KATHY] if "FROM users" in str(stmt) else sorted(self.plans.values(), key=lambda p: p.day, reverse=True))  # the real query orders by day

    def get(self, _model, key):
        return self.plans.get(key)

    def add(self, plan):
        plan.id = uuid.uuid4()
        plan.created_at = datetime(2026, 10, 24, 12, tzinfo=timezone.utc)
        self.plans[plan.id] = plan

    def delete(self, plan):
        del self.plans[plan.id]

    def commit(self): ...

    def refresh(self, _plan): ...


@pytest.fixture
def api():
    db = FakeDB()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[current_user] = lambda: ME
    yield TestClient(app), db
    app.dependency_overrides.clear()


def make(c, **kw):
    r = c.post("/api/plans", json={"day": "2026-11-07", "stops": [STOP2, STOP], **kw})
    assert r.status_code == 201, r.text
    return r.json()


def test_router_is_registered():
    paths = set(app.openapi()["paths"])
    assert {"/api/plans", "/api/plans/suggest", "/api/plans/{plan_id}"} <= paths


def test_create_sorts_stops_and_titles_the_plan_from_them(api):
    c, db = api
    plan = make(c, window_start="18:00", budget=80, vibe=["jazz"])
    assert [s["item"]["title"] for s in plan["stops"]] == ["Jazz night", "Perch"]
    assert plan["title"] == "Jazz night + Perch"
    assert plan["window_start"] == "18:00" and plan["window_end"] is None
    assert plan["budget"] == 80 and plan["vibe"] == ["jazz"]
    assert plan["created_by"] == {"id": 1, "display_name": "Zaher"}
    assert plan["stops"][1]["role"] == "food" and plan["stops"][1]["travel_min"] == 12.5
    assert len(db.plans) == 1


def test_create_without_title_or_stops_is_date_night(api):
    c, _ = api
    assert c.post("/api/plans", json={"day": "2026-11-07", "title": "  "}).json()["title"] == "Date night"


def test_create_accepts_start_time_alias_and_rejects_bad_bodies(api):
    c, _ = api
    r = c.post("/api/plans", json={"day": "2026-11-07", "start_time": "17:30", "end_time": "22:00"})
    assert (r.json()["window_start"], r.json()["window_end"]) == ("17:30", "22:00")
    backwards = {**STOP, "arrive": STOP["leave"], "leave": STOP["arrive"]}
    bad_type = {**STOP, "item": {"type": "cafe", "id": "x", "title": "y"}}
    for body in ({"day": "not a day"}, {"day": "2026-11-07", "budget": -1}, {"day": "2026-11-07", "stops": [backwards]},
                 {"day": "2026-11-07", "stops": [bad_type]}, {"day": "2026-11-07", "stops": [STOP] * 13}):
        assert c.post("/api/plans", json=body).status_code == 422


def test_get_and_missing_plan(api):
    c, _ = api
    plan = make(c)
    assert c.get(f"/api/plans/{plan['id']}").json() == plan
    assert plan["ics"] == f"/api/plans/{plan['id']}.ics"
    assert c.get(f"/api/plans/{uuid.uuid4()}").status_code == 404


def test_list_puts_upcoming_first_then_past_newest_first(api, monkeypatch):
    c, _ = api
    monkeypatch.setattr(plans, "datetime", SimpleNamespace(now=lambda tz: datetime(2026, 11, 1, tzinfo=tz)))
    for day, start in (("2026-10-01", "19:00"), ("2026-11-20", "19:00"), ("2026-11-05", "20:00"),
                       ("2026-11-05", "18:00"), ("2026-10-15", "19:00")):
        c.post("/api/plans", json={"day": day, "window_start": start, "title": f"{day} {start}"})
    out = c.get("/api/plans").json()
    assert [p["title"] for p in out] == ["2026-11-05 18:00", "2026-11-05 20:00", "2026-11-20 19:00",
                                         "2026-10-15 19:00", "2026-10-01 19:00"]
    assert [p["past"] for p in out] == [False, False, False, True, True]


def test_patch_changes_only_what_is_sent(api):
    c, _ = api
    plan = make(c, budget=80)
    r = c.patch(f"/api/plans/{plan['id']}", json={"title": "Anniversary", "budget": None, "stops": [STOP]})
    assert r.status_code == 200
    out = r.json()
    assert out["title"] == "Anniversary" and out["budget"] is None and len(out["stops"]) == 1
    assert out["day"] == "2026-11-07" and out["vibe"] == []
    out = c.patch(f"/api/plans/{plan['id']}", json={"day": "2026-12-01", "window_end": "23:00"}).json()
    assert out["day"] == "2026-12-01" and out["window_end"] == "23:00" and out["title"] == "Anniversary"


@pytest.mark.parametrize("body", [{"title": None}, {"day": None}, {"vibe": None}, {"title": ""}, {"budget": -5},
                                  {"stops": [{"item": {"type": "place"}}]}])
def test_patch_rejects_bad_values(api, body):
    c, _ = api
    plan = make(c)
    assert c.patch(f"/api/plans/{plan['id']}", json=body).status_code == 422
    assert c.get(f"/api/plans/{plan['id']}").json()["title"] == plan["title"]


def test_patch_and_delete_missing_plan(api):
    c, _ = api
    missing = uuid.uuid4()
    assert c.patch(f"/api/plans/{missing}", json={"title": "x"}).status_code == 404
    assert c.delete(f"/api/plans/{missing}").status_code == 404


def test_delete_removes_the_plan(api):
    c, db = api
    plan = make(c)
    assert c.delete(f"/api/plans/{plan['id']}").status_code == 204
    assert db.plans == {} and c.get(f"/api/plans/{plan['id']}").status_code == 404


def test_window_runs_past_midnight_when_the_end_is_earlier():
    a, b = plans.window(date(2026, 11, 7), time(19), time(1))
    assert b - a == timedelta(hours=6) and b.date() == date(2026, 11, 8)
    a, b = plans.window(date(2026, 11, 7), time(18), time(22))
    assert b - a == timedelta(hours=4)


class SuggestSpy:
    def __init__(self, monkeypatch):
        self.calls = {}
        cands = [Candidate(id="e1", type="event", title="Jazz", lat=34.05, lon=-118.25),
                 Candidate(id="p1", type="place", title="Perch", lat=34.05, lon=-118.25),
                 Candidate(id="p2", type="place", title="Bar", lat=34.06, lon=-118.25)]
        monkeypatch.setattr(plans, "home_point", lambda db: (34.0522, -118.2437))

        def load(db, start, end, origin, reach, tz):
            self.calls["load"] = (start, end, origin, reach, tz)
            return cands

        def pick(found, req, travel):
            self.calls["req"] = req
            return [{"stops": []}]

        monkeypatch.setattr(plans, "load_candidates", load)
        monkeypatch.setattr(plans, "suggest", pick)


def test_suggest_uses_home_by_default(api, monkeypatch):
    c, _ = api
    spy = SuggestSpy(monkeypatch)
    r = c.post("/api/plans/suggest", json={"day": "2026-11-07", "start_time": "18:00", "end_time": "23:00",
                                           "budget": 100, "vibe": [" Jazz ", ""]})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["itineraries"] == [{"stops": []}]
    assert out["start"] == {"lat": 34.0522, "lon": -118.2437, "source": "home"}
    assert out["considered"] == {"events": 1, "places": 2}
    assert out["window"]["start"].startswith("2026-11-07T18:00") and out["window"]["end"].startswith("2026-11-07T23:00")
    req = spy.calls["req"]
    assert req.vibe == ["jazz"] and req.budget == 100 and req.mode == "drive" and req.max_travel_min == 30
    assert spy.calls["load"][3] == 30 * 1000  # reach in metres for 30 drive minutes


def test_suggest_walk_mode_given_start_and_travel_limit(api, monkeypatch):
    c, _ = api
    spy = SuggestSpy(monkeypatch)
    out = c.post("/api/plans/suggest", json={"day": "2026-11-07", "start_time": "22:00", "end_time": "01:00",
                                             "mode": "walk", "start": {"lat": 34.1, "lon": -118.3}}).json()
    assert out["start"] == {"lat": 34.1, "lon": -118.3, "source": "given"}
    assert out["window"]["end"].startswith("2026-11-08T01:00")
    assert spy.calls["req"].max_travel_min == 25 and spy.calls["load"][3] == 25 * 100
    c.post("/api/plans/suggest", json={"day": "2026-11-07", "start_time": "18:00", "end_time": "20:00",
                                       "max_travel_min": 10})
    assert spy.calls["req"].max_travel_min == 10


@pytest.mark.parametrize("body", [{"mode": "bike"}, {"max_travel_min": 0}, {"max_travel_min": 500},
                                  {"start": {"lat": 120, "lon": 0}}, {"budget": -1}, {"end_time": None}])
def test_suggest_rejects_bad_input(api, monkeypatch, body):
    c, _ = api
    SuggestSpy(monkeypatch)
    full = {"day": "2026-11-07", "start_time": "18:00", "end_time": "20:00", **body}
    assert c.post("/api/plans/suggest", json=full).status_code == 422


def test_suggest_passes_a_working_travel_function_to_the_picker(api, monkeypatch):
    c, _ = api
    seen = {}
    monkeypatch.setattr(plans, "home_point", lambda db: (34.05, -118.25))
    monkeypatch.setattr(plans, "load_candidates", lambda *a: [])
    monkeypatch.setattr(plans.osrm, "table", lambda o, ds, mode, client=None: seen.update(args=(o, ds, mode)) or [])

    def pick(found, req, travel):
        travel((34.05, -118.25), [(34.06, -118.26)], "walk")
        return []

    monkeypatch.setattr(plans, "suggest", pick)
    assert c.post("/api/plans/suggest", json={"day": "2026-11-07", "start_time": "18:00",
                                              "end_time": "20:00"}).status_code == 200
    assert seen["args"] == ((34.05, -118.25), [(34.06, -118.26)], "walk")
