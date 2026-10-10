"""Date-night picker: 2-3 itineraries for one day and time window.

Each itinerary is an anchor (an event in the window, or a place when there are not enough
events), a food stop open at the planned time near it (before or after the anchor), and an
optional drinks or dessert stop at the end. The scheduling here is pure: it takes Candidate
rows and a travel function, so it is tested without a database or OSRM. app.plan.loader
builds the candidates from the database.
"""
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.plan import hours
from app.plan.osrm import Leg, Point, haversine_m

FOOD = frozenset({"restaurant", "cafe", "dessert", "market"})
DRINKS = frozenset({"bar", "nightlife", "dessert"})
PRICE_LEVEL_PP = {0: 0.0, 1: 15.0, 2: 35.0, 3: 70.0, 4: 120.0}
# Minutes spent at a stop, by category
STAY_MIN = {
    "restaurant": 90, "cafe": 45, "dessert": 30, "market": 60, "bar": 75, "nightlife": 90,
    "museum": 120, "arts": 90, "park": 75, "outdoors": 90, "hike": 120, "beach": 120, "viewpoint": 45,
    "shopping": 60, "activity": 90, "class": 120, "spa": 120, "show": 150, "comedy": 120,
    "live_music": 150, "sports": 180, "festival": 150,
}
DEFAULT_STAY_MIN = 90
EVENT_STAY_MIN = 120  # an event with no end time
LONG_EVENT = timedelta(hours=4)  # longer events (festivals, markets) are visited, not sat through
MIN_ANCHOR = timedelta(minutes=45)
MIN_STAY = timedelta(minutes=30)
BUFFER = timedelta(minutes=5)  # parking, finding the table
STEP = timedelta(minutes=15)
SHORT_WALK_M = 800  # drive mode walks legs shorter than this
MAX_SHORT_WALK_MIN = 12
# Straight-line reach per travel minute, a generous upper bound used to prune before OSRM
REACH_M_PER_MIN = {"drive": 1000.0, "walk": 100.0}
MAX_ITINERARIES = 3
FOOD_TRIES = 8
DRINK_TRIES = 6
TABLE_LIMIT = 25

TravelFn = Callable[[Point, list[Point], str], list[Leg]]


@dataclass
class Candidate:
    id: str
    type: str  # place or event
    title: str
    lat: float
    lon: float
    category: str | None = None
    tags: list[str] = field(default_factory=list)
    price_pp: float | None = None  # dollars per person, None when unknown
    opening_hours: str | None = None  # places only, OSM syntax
    starts_at: datetime | None = None  # events: the occurrence in the window (aware)
    ends_at: datetime | None = None
    status: str | None = None  # best status any of us gave it: going, want or been
    rating: float | None = None  # mean of our ratings
    address: str | None = None
    venue: str | None = None
    place_id: str | None = None  # an event's place
    url: str | None = None
    suggested: bool = False  # discovered and not accepted yet

    @property
    def point(self) -> Point:
        return (self.lat, self.lon)


@dataclass
class Request:
    start: datetime  # aware, local tz
    end: datetime
    origin: Point
    mode: str = "drive"
    budget: float | None = None  # max dollars per person for the whole night
    vibe: list[str] = field(default_factory=list)
    max_travel_min: float = 30


@dataclass
class Slot:
    cand: Candidate
    role: str  # anchor, food, drinks
    stay: timedelta
    lo: datetime  # earliest arrival
    hi: datetime  # latest departure
    fixed: bool = False  # an event that starts at a set time


@dataclass
class Hop:
    leg: Leg
    mode: str


@dataclass
class Timed:
    slot: Slot
    arrive: datetime
    leave: datetime


def place_price(level: int | None) -> float | None:
    return PRICE_LEVEL_PP.get(level) if level is not None else None


def event_price(price_min: float | None, is_free: bool | None) -> float | None:
    if is_free:
        return 0.0
    return float(price_min) if price_min is not None else None


def _norm(s: str) -> str:
    return s.lower().replace("_", " ").replace("-", " ").strip()


def vibe_hits(c: Candidate, vibe: list[str]) -> list[str]:
    have = {_norm(t) for t in c.tags} | ({_norm(c.category)} if c.category else set())
    return [v for v in vibe if _norm(v) in have]


def score(c: Candidate, req: Request) -> float:
    s = {"going": 3.0, "want": 2.0, "been": 0.5}.get(c.status or "", 0.0)
    s += min(len(vibe_hits(c, req.vibe)), 3)
    if c.rating is not None:
        s += (c.rating - 3) * 0.5
    if c.suggested:
        s -= 0.5
    return s


def stay_for(c: Candidate) -> timedelta:
    return timedelta(minutes=STAY_MIN.get(c.category or "", DEFAULT_STAY_MIN))


class Travel:
    """Memoized travel lookups on top of a one-to-many travel function."""

    def __init__(self, fn: TravelFn, req: Request):
        self.fn, self.req = fn, req
        self.cache: dict[tuple[Point, Point, str], Leg] = {}

    def many(self, origin: Point, dests: list[Point], mode: str | None = None) -> list[Leg]:
        mode = mode or self.req.mode
        missing = list(dict.fromkeys(d for d in dests if (origin, d, mode) not in self.cache))
        if missing:
            for d, leg in zip(missing, self.fn(origin, missing, mode)):
                self.cache[(origin, d, mode)] = leg
        return [self.cache[(origin, d, mode)] for d in dests]

    def hop(self, a: Point, b: Point) -> Hop:
        leg = self.many(a, [b])[0]
        if self.req.mode == "drive" and haversine_m(a, b) < SHORT_WALK_M:
            walk = self.many(a, [b], "walk")[0]
            if walk.minutes <= MAX_SHORT_WALK_MIN:
                return Hop(walk, "walk")
        return Hop(leg, self.req.mode)


def _gap(hop: Hop) -> timedelta:
    return timedelta(minutes=math.ceil(hop.leg.minutes)) + BUFFER


def _ceil5(t: datetime) -> datetime:
    t = t.replace(second=0, microsecond=0) + (timedelta(minutes=1) if t.second or t.microsecond else timedelta())
    return t + timedelta(minutes=(-t.minute) % 5)


def _floor5(t: datetime) -> datetime:
    t = t.replace(second=0, microsecond=0)
    return t - timedelta(minutes=t.minute % 5)


def _open_ok(slot: Slot, arrive: datetime, leave: datetime) -> bool:
    if slot.cand.type != "place":
        return True
    return hours.is_open_between(slot.cand.opening_hours, arrive, leave) is not False


def _forward(slot: Slot, earliest: datetime, req: Request) -> tuple[datetime, datetime] | None:
    """Earliest arrival from `earliest` that fits the slot, the window and the opening hours."""
    arrive = _ceil5(max(earliest, slot.lo))
    hi = min(slot.hi, req.end)
    while arrive + slot.stay <= hi:
        if _open_ok(slot, arrive, arrive + slot.stay):
            return arrive, arrive + slot.stay
        arrive += STEP
    return None


def _backward(slot: Slot, latest_leave: datetime, req: Request) -> tuple[datetime, datetime] | None:
    """Latest departure before `latest_leave`, so nobody waits around before a fixed event."""
    leave = _floor5(min(latest_leave, slot.hi, req.end))
    lo = max(slot.lo, req.start)
    while leave - slot.stay >= lo:
        if _open_ok(slot, leave - slot.stay, leave):
            return leave - slot.stay, leave
        leave -= STEP
    return None


def schedule(slots: list[Slot], req: Request, travel: Travel) -> tuple[list[Hop], list[Timed]] | None:
    """Times for stops in this order, or None when they do not fit.

    hops[0] is start -> first stop, hops[i] is stop i-1 -> stop i.
    """
    points = [req.origin] + [s.cand.point for s in slots]
    hops = [travel.hop(points[i], points[i + 1]) for i in range(len(slots))]
    if any(h.leg.minutes > req.max_travel_min for h in hops):
        return None
    times: list[tuple[datetime, datetime] | None] = [None] * len(slots)
    fixed = next((i for i, s in enumerate(slots) if s.fixed), None)
    if fixed is not None:
        f = slots[fixed]
        times[fixed] = (f.lo, f.lo + f.stay)
        nxt = f.lo
        for i in range(fixed - 1, -1, -1):
            placed = _backward(slots[i], nxt - _gap(hops[i + 1]), req)
            if placed is None:
                return None
            times[i] = placed
            nxt = placed[0]
        if nxt < req.start + _gap(hops[0]):
            return None
        t, begin = f.lo + f.stay, fixed + 1
    else:
        t, begin = req.start, 0
    for i in range(begin, len(slots)):
        placed = _forward(slots[i], t + _gap(hops[i]), req)
        if placed is None:
            return None
        times[i] = placed
        t = placed[1]
    return hops, [Timed(s, *tt) for s, tt in zip(slots, times)]


def _total_price(slots: list[Slot]) -> float:
    return sum(s.cand.price_pp or 0.0 for s in slots)


def _fits_budget(slots: list[Slot], req: Request) -> bool:
    return req.budget is None or _total_price(slots) <= req.budget + 1e-9


def anchor_slot(c: Candidate, req: Request) -> Slot | None:
    if c.type == "event":
        if c.starts_at is None:
            return None
        end = c.ends_at or c.starts_at + timedelta(minutes=EVENT_STAY_MIN)
        lo, hi = max(c.starts_at, req.start), min(end, req.end)
        if hi - lo < MIN_ANCHOR:
            return None
        if c.starts_at >= req.start and end - c.starts_at <= LONG_EVENT:
            return Slot(c, "anchor", hi - c.starts_at, c.starts_at, hi, fixed=True)
        stay = min(timedelta(minutes=STAY_MIN.get(c.category or "", EVENT_STAY_MIN)), hi - lo)
        return Slot(c, "anchor", stay, lo, hi)
    return Slot(c, "anchor", stay_for(c), req.start, req.end)


def _nearby(origin: Point, pool: list[Candidate], req: Request, travel: Travel,
            used: set[str] = frozenset()) -> list[tuple[Candidate, Leg]]:
    """Pool members reachable from origin, best first (score, then travel time)."""
    reach = req.max_travel_min * REACH_M_PER_MIN.get(req.mode, 1000.0)
    close = [c for c in pool if haversine_m(origin, c.point) <= reach]
    close.sort(key=lambda c: (-score(c, req), haversine_m(origin, c.point)))
    close = close[:TABLE_LIMIT]
    legs = travel.many(origin, [c.point for c in close])
    ok = [(c, leg) for c, leg in zip(close, legs) if leg.minutes <= req.max_travel_min]
    ok.sort(key=lambda cl: -(score(cl[0], req) - 0.05 * cl[1].minutes - (1.5 if cl[0].id in used else 0.0)))
    return ok


def _try_add(core: list[Slot], options: list[tuple[Candidate, Leg]], role: str, at_end: bool,
             req: Request, travel: Travel, tries: int):
    for c, _ in options[:tries]:
        full = stay_for(c)
        # A shorter visit when the full one does not fit
        for stay in dict.fromkeys((full, max(MIN_STAY, _floor_td(full * 0.6)))):
            slot = Slot(c, role, stay, req.start, req.end)
            slots = [*core, slot] if at_end else [slot, *core]
            if not _fits_budget(slots, req):
                break
            result = schedule(slots, req, travel)
            if result:
                return slots, result
    return None


def _floor_td(d: timedelta) -> timedelta:
    return timedelta(minutes=int(d.total_seconds() // 300) * 5)


def _plan(anchor: Candidate, req: Request, travel: Travel, food: list[Candidate],
          drinks: list[Candidate], used: set[str]) -> dict | None:
    a = anchor_slot(anchor, req)
    if a is None or not _fits_budget([a], req):
        return None
    base = schedule([a], req, travel)
    if base is None:
        return None
    notes = []
    slots, result = [a], base
    skip = {anchor.id, anchor.place_id}
    if (anchor.category or "") not in FOOD:
        options = _nearby(anchor.point, [f for f in food if f.id not in skip], req, travel, used)
        # Eat on the side of the anchor with more free time
        if a.fixed:
            before_first = (a.lo - req.start) >= (req.end - (a.lo + a.stay))
        else:
            before_first = False
        found = None
        for before in (before_first, not before_first):
            found = _try_add([a], options, "food", not before, req, travel, FOOD_TRIES)
            if found:
                break
        if found:
            slots, result = found
        else:
            notes.append("No food stop open near this at a time that fits.")
    last = slots[-1].cand
    taken = {s.cand.id for s in slots} | skip
    food_cats = {s.cand.category for s in slots if s.role == "food" or s.cand.category in FOOD}
    pool = [d for d in drinks if d.id not in taken and not (d.category == "dessert" and "dessert" in food_cats)]
    options = _nearby(last.point, pool, req, travel, used)
    found = _try_add(slots, options, "drinks", True, req, travel, DRINK_TRIES)
    if found:
        slots, result = found
    return _render(slots, result, req, notes)


def suggest(cands: list[Candidate], req: Request, travel_fn: TravelFn) -> list[dict]:
    """Up to three itineraries, each with a different anchor."""
    travel = Travel(travel_fn, req)
    food = [c for c in cands if c.type == "place" and c.category in FOOD]
    drinks = [c for c in cands if c.type == "place" and c.category in DRINKS]
    events = [c for c in cands if c.type == "event" and anchor_slot(c, req)]
    places = [c for c in cands if c.type == "place" and (c.category or "other") not in FOOD | DRINKS]
    dinners = [c for c in food if c.category in ("restaurant", "market")]
    out: list[dict] = []
    used: set[str] = set()
    seen: set[str] = set()
    # Events first, then other places, and a dinner as the anchor only to reach two
    for group, upto in ((events, MAX_ITINERARIES), (places, MAX_ITINERARIES), (dinners, 2)):
        for anchor, _ in _nearby(req.origin, group, req, travel):
            if len(out) >= upto:
                break
            if anchor.id in seen:
                continue
            plan = _plan(anchor, req, travel, food, drinks, used)
            if plan is None:
                continue
            seen.add(anchor.id)
            used.update(s["item"]["id"] for s in plan["stops"] if s["role"] != "anchor")
            out.append(plan)
    return out


def _clock(t: datetime) -> str:
    return f"{t.hour % 12 or 12}:{t.minute:02d} {'AM' if t.hour < 12 else 'PM'}"


def _reason(t: Timed, req: Request, near: tuple[Hop, str] | None) -> str:
    c, parts = t.slot.cand, []
    if c.status == "going":
        parts.append("Marked going")
    elif c.status == "want":
        parts.append("On the want list")
    if c.rating is not None and c.rating >= 4:
        parts.append(f"Rated {c.rating:g}")
    hits = vibe_hits(c, req.vibe)
    if hits:
        parts.append("Fits " + ", ".join(hits))
    if c.type == "event" and c.starts_at:
        parts.append(f"Starts {_clock(c.starts_at)}")
    if t.slot.role != "anchor" and near is not None:
        hop, where = near
        parts.append(f"{math.ceil(hop.leg.minutes)} min {hop.mode} {where}")
    if c.type == "place":
        parts.append("Open then" if hours.parse(c.opening_hours) else "Hours unknown, check first")
    if c.price_pp == 0:
        parts.append("Free")
    elif c.price_pp is None:
        parts.append("Price unknown")
    return ". ".join(parts[:5])


def _hop_json(h: Hop | None) -> dict:
    if h is None:
        return {"travel_min": None, "travel_m": None, "mode": None, "estimated": False}
    return {"travel_min": math.ceil(h.leg.minutes), "travel_m": round(h.leg.metres), "mode": h.mode,
            "estimated": h.leg.estimated}


def item_json(c: Candidate) -> dict:
    return {"type": c.type, "id": c.id, "title": c.title, "category": c.category, "lat": c.lat, "lon": c.lon,
            "address": c.address, "venue": c.venue, "url": c.url}


def _render(slots: list[Slot], result: tuple[list[Hop], list[Timed]], req: Request, notes: list[str]) -> dict:
    hops, timed = result
    anchor_i = next(i for i, s in enumerate(slots) if s.role == "anchor")
    anchor = slots[anchor_i].cand
    stops = []
    for i, t in enumerate(timed):
        nxt = hops[i + 1] if i + 1 < len(hops) else None
        # How far it is from the stop before, or to the anchor when it comes first
        if i < anchor_i:
            near = (hops[i + 1], f"to {timed[i + 1].slot.cand.title}")
        elif i > 0:
            near = (hops[i], f"from {timed[i - 1].slot.cand.title}")
        else:
            near = None
        c = t.slot.cand
        stops.append({
            "role": t.slot.role, "item": item_json(c),
            "arrive": t.arrive.isoformat(), "leave": t.leave.isoformat(),
            "stay_min": round((t.leave - t.arrive).total_seconds() / 60),
            "price_pp": c.price_pp,
            "hours_known": (hours.parse(c.opening_hours) is not None) if c.type == "place" else None,
            **_hop_json(nxt),
            "reason": _reason(t, req, near),
        })
        if t.slot.fixed and c.ends_at and t.leave < c.ends_at:
            notes.append(f"Leaves {anchor.title} at {_clock(t.leave)}, before it ends.")
        if c.type == "place" and hours.parse(c.opening_hours) is None:
            notes.append(f"Opening hours for {c.title} are unknown.")
    first = timed[0]
    depart = first.arrive - timedelta(minutes=math.ceil(hops[0].leg.minutes))
    return {
        "title": " + ".join(s.cand.title for s in slots),
        "anchor": {"type": anchor.type, "id": anchor.id},
        "start": depart.isoformat(), "end": timed[-1].leave.isoformat(),
        "start_leg": _hop_json(hops[0]),
        "stops": stops,
        "price_pp": _total_price(slots),
        "price_complete": all(s.cand.price_pp is not None for s in slots),
        "notes": notes,
    }
