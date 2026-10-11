from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.plan.osrm import Leg, haversine_m
from app.plan.picker import Candidate, Request, anchor_slot, place_price, suggest

LA = ZoneInfo("America/Los_Angeles")
HOME = (34.0461, -118.3265)
SAT = (2026, 10, 17)


def t(hh, mm=0, day=SAT):
    return datetime(*day, hh, mm, tzinfo=LA)


calls = []


def travel(origin, dests, mode):
    """Straight line at 30 km/h driving, 4.8 km/h walking."""
    calls.append(mode)
    speed = 500.0 if mode == "drive" else 80.0
    return [Leg(haversine_m(origin, d) / speed, haversine_m(origin, d)) for d in dests]


def ev(id, lat, lon, start, end, price=None, **kw):
    return Candidate(id=id, type="event", title=id.title(), lat=lat, lon=lon, starts_at=start, ends_at=end,
                     price_pp=price, **kw)


def pl(id, lat, lon, cat, hours=None, level=None, **kw):
    return Candidate(id=id, type="place", title=id.title(), lat=lat, lon=lon, category=cat, opening_hours=hours,
                     price_pp=place_price(level), **kw)


def world():
    return [
        ev("jazz", 34.0500, -118.3000, t(20), t(22), 25, category="live_music", tags=["jazz"], status="going"),
        ev("comedy", 34.0600, -118.3500, t(18), t(19, 30), 20, category="comedy"),
        ev("concert", 34.0700, -118.3100, t(19), t(22), 150, category="live_music"),
        pl("bistro", 34.0520, -118.3050, "restaurant", "Mo-Su 17:00-22:00", 2, status="want"),
        pl("lunchspot", 34.0610, -118.3480, "restaurant", "Mo-Su 11:00-15:00", 1, status="going"),
        pl("tacos", 34.0590, -118.3460, "restaurant", None, 1),
        pl("dive", 34.0510, -118.2980, "bar", "Mo-Su 16:00-02:00", 1),
        pl("gelato", 34.0620, -118.3440, "dessert", "Mo-Su 12:00-23:00", 1),
        pl("faraway", 34.4000, -118.9000, "restaurant", "24/7", 1, status="going"),
    ]


def req(**kw):
    base = dict(start=t(17), end=t(23), origin=HOME, mode="drive", max_travel_min=30)
    return Request(**{**base, **kw})


def stops_of(plan):
    return [(s["role"], s["item"]["id"]) for s in plan["stops"]]


def test_distinct_anchors_and_events_first():
    plans = suggest(world(), req(), travel)
    assert 2 <= len(plans) <= 3
    anchors = [p["anchor"]["id"] for p in plans]
    assert len(set(anchors)) == len(anchors)
    assert all(p["anchor"]["type"] == "event" for p in plans)
    # Going and vibe beat an unmarked event
    assert anchors[0] == "jazz" or suggest(world(), req(vibe=["jazz"]), travel)[0]["anchor"]["id"] == "jazz"


def test_budget_filters():
    plans = suggest(world(), req(budget=70), travel)
    assert "concert" not in [p["anchor"]["id"] for p in plans]
    for p in plans:
        assert p["price_pp"] <= 70
        assert sum(s["price_pp"] or 0 for s in p["stops"]) == p["price_pp"]


def test_tight_budget_drops_paid_stops():
    plans = suggest(world(), req(budget=30), travel)
    assert plans
    for p in plans:
        assert p["price_pp"] <= 30


def test_opening_hours_respected():
    for p in suggest(world(), req(), travel):
        ids = [s["item"]["id"] for s in p["stops"]]
        assert "lunchspot" not in ids  # closed in the evening
        for s in p["stops"]:
            if s["item"]["id"] == "bistro":
                assert datetime.fromisoformat(s["leave"]) <= t(22)
                assert datetime.fromisoformat(s["arrive"]) >= t(17)


def test_unknown_hours_allowed_but_marked():
    cands = [ev("comedy", 34.0600, -118.3500, t(18), t(19, 30), 20, category="comedy"),
             pl("tacos", 34.0590, -118.3460, "restaurant", None, 1)]
    plans = suggest(cands, req(), travel)
    p = plans[0]
    assert p["anchor"]["id"] == "comedy"
    food = next(s for s in p["stops"] if s["role"] == "food")
    assert food["item"]["id"] == "tacos" and food["hours_known"] is False
    assert "Hours unknown" in food["reason"]
    assert any("tacos" in n.lower() for n in p["notes"])


def test_times_are_ordered_and_travel_fits():
    for p in suggest(world(), req(), travel):
        stops = p["stops"]
        first = datetime.fromisoformat(stops[0]["arrive"])
        assert first >= t(17) + timedelta(minutes=p["start_leg"]["travel_min"])
        assert p["start_leg"]["travel_min"] <= 30
        for a, b in zip(stops, stops[1:]):
            leave, arrive = datetime.fromisoformat(a["leave"]), datetime.fromisoformat(b["arrive"])
            assert datetime.fromisoformat(a["arrive"]) < leave
            assert leave + timedelta(minutes=a["travel_min"]) <= arrive
            assert a["travel_min"] <= 30 and a["mode"] in ("drive", "walk")
        assert datetime.fromisoformat(stops[-1]["leave"]) <= t(23)
        assert stops[-1]["travel_min"] is None


def test_fixed_event_keeps_its_time_and_dinner_goes_before():
    plans = suggest(world(), req(), travel)
    jazz = next(p for p in plans if p["anchor"]["id"] == "jazz")
    roles = [r for r, _ in stops_of(jazz)]
    assert roles[:2] == ["food", "anchor"]
    anchor = jazz["stops"][1]
    assert datetime.fromisoformat(anchor["arrive"]) == t(20)
    assert datetime.fromisoformat(anchor["leave"]) == t(22)
    assert jazz["stops"][0]["item"]["id"] == "bistro"


def test_early_event_eats_after():
    plans = suggest(world(), req(), travel)
    comedy = next(p for p in plans if p["anchor"]["id"] == "comedy")
    roles = [r for r, _ in stops_of(comedy)]
    assert roles[0] == "anchor" and "food" in roles


def test_drinks_come_last():
    for p in suggest(world(), req(), travel):
        roles = [r for r, _ in stops_of(p)]
        if "drinks" in roles:
            assert roles[-1] == "drinks"


def test_far_places_never_used():
    for p in suggest(world(), req(max_travel_min=20), travel):
        assert "faraway" not in [s["item"]["id"] for s in p["stops"]]


def test_short_hop_walks_in_drive_mode():
    cands = [ev("jazz", 34.0500, -118.3000, t(20), t(22), 25, category="live_music"),
             pl("bistro", 34.0520, -118.3020, "restaurant", "Mo-Su 17:00-22:00", 2)]
    calls.clear()
    p = suggest(cands, req(), travel)[0]
    assert p["anchor"]["id"] == "jazz"
    assert p["stops"][0]["mode"] == "walk" and p["start_leg"]["mode"] == "drive"
    assert "walk" in calls


def test_walk_mode_limits_reach():
    plans = suggest(world(), req(mode="walk", max_travel_min=15), travel)
    for p in plans:
        assert all(s["mode"] in (None, "walk") for s in p["stops"])
        assert p["start_leg"]["travel_min"] <= 15


def test_place_anchor_when_no_events():
    cands = [pl("museum", 34.0600, -118.3300, "museum", "Mo-Su 10:00-20:00"),
             pl("park", 34.0400, -118.3200, "park", None),
             pl("bistro", 34.0620, -118.3310, "restaurant", "Mo-Su 17:00-22:00", 2),
             pl("dive", 34.0410, -118.3190, "bar", "Mo-Su 16:00-02:00", 1)]
    plans = suggest(cands, req(start=t(15)), travel)
    assert {p["anchor"]["id"] for p in plans} == {"museum", "park"}
    museum = next(p for p in plans if p["anchor"]["id"] == "museum")
    stop = museum["stops"][[r for r, _ in stops_of(museum)].index("anchor")]
    assert datetime.fromisoformat(stop["leave"]) <= t(20)


def test_dinner_anchor_when_only_food():
    cands = [pl("bistro", 34.0520, -118.3050, "restaurant", "Mo-Su 17:00-22:00", 2),
             pl("dive", 34.0510, -118.3040, "bar", "Mo-Su 16:00-02:00", 1)]
    [p] = suggest(cands, req(), travel)
    assert stops_of(p) == [("anchor", "bistro"), ("drinks", "dive")]


def test_one_event_gets_a_dinner_alternative():
    cands = [ev("jazz", 34.0500, -118.3000, t(20), t(22), 25, category="live_music"),
             pl("bistro", 34.0520, -118.3050, "restaurant", "Mo-Su 17:00-22:00", 2),
             pl("tacos", 34.0590, -118.3460, "restaurant", "Mo-Su 12:00-23:00", 1)]
    plans = suggest(cands, req(), travel)
    assert [p["anchor"]["id"] for p in plans][0] == "jazz" and len(plans) == 2
    assert plans[1]["anchor"]["type"] == "place"


def test_nothing_fits():
    assert suggest([pl("lunchspot", 34.05, -118.32, "restaurant", "Mo-Su 11:00-15:00")], req(), travel) == []
    assert suggest([], req(), travel) == []


def test_event_in_progress_is_flexible():
    r = req(start=t(18))
    slot = anchor_slot(ev("fest", 34.05, -118.30, t(12), t(22), 0, category="festival"), r)
    assert not slot.fixed and slot.lo == t(18) and slot.hi == t(22)
    assert anchor_slot(ev("late", 34.05, -118.30, t(22, 45), t(23, 59)), r) is None
    fixed = anchor_slot(ev("show", 34.05, -118.30, t(21), t(23, 30)), r)
    assert fixed.fixed and fixed.stay == timedelta(hours=2)  # cut at the window end


def test_window_past_midnight():
    late = req(start=t(20, 30), end=t(1, day=(2026, 10, 18)))
    cands = [ev("dj", 34.0500, -118.3000, t(22), t(0, 30, day=(2026, 10, 18)), 15, category="nightlife"),
             pl("diner", 34.0510, -118.3020, "restaurant", "Mo-Su 18:00-03:00", 1)]
    p = suggest(cands, late, travel)[0]
    assert p["anchor"]["id"] == "dj"
    assert [r for r, _ in stops_of(p)] == ["food", "anchor"]
    assert p["stops"][0]["stay_min"] < 90  # a quicker dinner to make the start
