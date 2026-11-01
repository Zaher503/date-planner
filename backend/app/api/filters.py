"""Filters shared by /api/map and /api/list: query parsing and SQL conditions."""
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException, Query
from geoalchemy2 import Geography, Geometry
from sqlalchemy import and_, case, exists, func, literal_column, or_, select

from app.config import get_settings
from app.db.models import Event, Occurrence, Place, UserItemState

WHENS = ("today", "tomorrow", "weekend", "week", "month", "range")
TYPES = ("place", "event")
PRICES = ("free", "1", "2", "3")
STATUSES = ("want", "going", "been", "suggested", "review")
MY_STATUSES = ("want", "going", "been")
# Event price buckets on price_min: 1 is under 20, 2 is 20 to 50, 3 is above 50
LOW, HIGH = 20, 50
DEFAULT_EVENT_HOURS = 3
GEOG = Geography(srid=4326)
GEOM = Geometry(srid=4326)


@dataclass
class Filters:
    bbox: tuple[float, float, float, float] | None = None  # w, s, e, n
    types: tuple[str, ...] = TYPES
    when: str | None = None
    window: tuple[datetime, datetime] | None = None  # aware, end exclusive
    open_now: bool = False
    price: set[str] = field(default_factory=set)
    tags: list[str] = field(default_factory=list)
    cats: list[str] = field(default_factory=list)
    status: set[str] = field(default_factory=set)
    near: tuple[float, float] | None = None  # lat, lon
    dist_km: float | None = None
    q: str | None = None
    past: bool = False  # keep archived events in the results
    archive: bool = False  # only archived events (the Archive section)
    now: datetime | None = None


def _bad(msg: str) -> HTTPException:
    return HTTPException(400, msg)


def _list(raw: str | None) -> list[str]:
    return [x.strip() for x in (raw or "").split(",") if x.strip()]


def _floats(raw: str, n: int, name: str) -> list[float]:
    try:
        vals = [float(x) for x in raw.split(",")]
    except ValueError:
        raise _bad(f"{name} must be {n} comma separated numbers") from None
    if len(vals) != n:
        raise _bad(f"{name} must be {n} comma separated numbers")
    return vals


def _flag(raw: str | None) -> bool:
    return (raw or "").strip().lower() in ("1", "true", "yes", "on")


def _day(raw: str | None, name: str) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise _bad(f"{name} must be YYYY-MM-DD") from None


def time_window(when: str, now: datetime, tz: ZoneInfo, start: date | None = None,
                end: date | None = None) -> tuple[datetime, datetime]:
    """Window for a `when` value in local time, as aware datetimes (end exclusive)."""
    local = now.astimezone(tz)
    today = local.date()

    def midnight(d: date) -> datetime:
        return datetime.combine(d, time(0), tzinfo=tz)

    if when == "today":
        return midnight(today), midnight(today + timedelta(days=1))
    if when == "tomorrow":
        return midnight(today + timedelta(days=1)), midnight(today + timedelta(days=2))
    if when == "weekend":
        # Coming Friday, or this one when it is already Friday to Sunday
        friday = today + timedelta(days=(4 - today.weekday()) % 7) if today.weekday() < 4 \
            else today - timedelta(days=today.weekday() - 4)
        return datetime.combine(friday, time(17), tzinfo=tz), midnight(friday + timedelta(days=3))
    if when == "week":
        return now, now + timedelta(days=7)
    if when == "month":
        return now, now + timedelta(days=31)
    if when == "range":
        if start is None:
            raise _bad("when=range needs from=YYYY-MM-DD")
        end = end or start
        if end < start:
            raise _bad("to is before from")
        return midnight(start), midnight(end + timedelta(days=1))
    raise _bad(f"when must be one of {', '.join(WHENS)}")


def parse_filters(*, bbox: str | None = None, types: str | None = None, when: str | None = None,
                  from_: str | None = None, to: str | None = None, open_now: str | None = None,
                  price: str | None = None, tags: str | None = None, cats: str | None = None,
                  status: str | None = None, near: str | None = None, dist_km: str | None = None,
                  q: str | None = None, past: str | None = None, archive: str | None = None,
                  now: datetime | None = None, tz: str | None = None) -> Filters:
    """Validate the raw query strings. Raises HTTP 400 on bad input."""
    zone = ZoneInfo(tz or get_settings().default_tz)
    now = (now or datetime.now(zone)).astimezone(zone)  # local, so opening hours compare directly
    f = Filters(now=now, open_now=_flag(open_now), past=_flag(past), archive=_flag(archive))
    if bbox:
        w, s, e, n = _floats(bbox, 4, "bbox")
        if not (-180 <= w <= 180 and -180 <= e <= 180 and -90 <= s <= n <= 90):
            raise _bad("bbox must be w,s,e,n in degrees")
        f.bbox = (w, s, e, n)
    if types:
        ts = _list(types)
        if not ts or any(t not in TYPES for t in ts):
            raise _bad("types must be place and/or event")
        f.types = tuple(t for t in TYPES if t in ts)
    if f.archive:
        f.types = ("event",)  # only events are ever archived
    if when:
        f.when = when.strip().lower()
        f.window = time_window(f.when, now, zone, _day(from_, "from"), _day(to, "to"))
    f.price = set(_list(price))
    if f.price - set(PRICES):
        raise _bad("price must be any of free,1,2,3")
    f.tags = _list(tags)
    f.cats = _list(cats)
    f.status = set(_list(status))
    if f.status - set(STATUSES):
        raise _bad(f"status must be any of {','.join(STATUSES)}")
    if near:
        lat, lon = _floats(near, 2, "near")
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise _bad("near must be lat,lon")
        f.near = (lat, lon)
    if dist_km:
        try:
            f.dist_km = float(dist_km)
        except ValueError:
            raise _bad("dist_km must be a number") from None
        if f.dist_km <= 0:
            raise _bad("dist_km must be positive")
    f.q = (q or "").strip()[:200] or None
    return f


def filters_dep(bbox: str | None = None, types: str | None = None, when: str | None = None,
                from_: str | None = Query(None, alias="from"), to: str | None = None,
                open_now: str | None = None, price: str | None = None, tags: str | None = None,
                cats: str | None = None, status: str | None = None, near: str | None = None,
                dist_km: str | None = None, q: str | None = None, past: str | None = None,
                archive: str | None = None) -> Filters:
    return parse_filters(bbox=bbox, types=types, when=when, from_=from_, to=to, open_now=open_now,
                         price=price, tags=tags, cats=cats, status=status, near=near, dist_km=dist_km,
                         q=q, past=past, archive=archive)


def point_sql(lat: float, lon: float):
    return func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326).cast(GEOG)


def event_end(starts, ends):
    """Effective end: ends_at, else start + duration, else a day (all-day) or 3 hours."""
    return func.coalesce(
        ends,
        starts + func.make_interval(0, 0, 0, 0, 0, Event.duration_min),
        case((Event.all_day.is_(True), starts + timedelta(days=1)),
             else_=starts + timedelta(hours=DEFAULT_EVENT_HOURS)))


def recurring():
    return or_(Event.rrule.isnot(None), Event.recurrence_text.isnot(None))


def archived(now: datetime):
    """SQL: the event belongs in the Archive. This is the one rule for it: set by hand (status archived), or a
    one-off event that has ended (an exhibition with only a closing date counts). It reads the clock, so old and
    new events (whatever added them) move over by themselves, with no migration or job. Recurring and fully
    undated events never age out."""
    return or_(Event.status == "archived",
               and_(~recurring(), or_(Event.starts_at.isnot(None), Event.ends_at.isnot(None)),
                    event_end(Event.starts_at, Event.ends_at) < now))


def event_ended(*, status: str | None, starts_at: datetime | None, ends_at: datetime | None,
                duration_min: int | None, all_day: bool | None, is_recurring: bool, now: datetime) -> bool:
    """Python twin of archived(), for rows already in memory. Keep the two in step."""
    if status == "archived":
        return True
    if is_recurring or (starts_at is None and ends_at is None):
        return False
    if starts_at is not None and starts_at.tzinfo is None:  # a time that was never given an offset reads in the caller's zone
        starts_at = starts_at.replace(tzinfo=now.tzinfo)
    if ends_at is not None and ends_at.tzinfo is None:
        ends_at = ends_at.replace(tzinfo=now.tzinfo)
    if ends_at is not None:
        end = ends_at
    elif duration_min is not None:
        end = starts_at + timedelta(minutes=duration_min)
    else:
        end = starts_at + (timedelta(days=1) if all_day else timedelta(hours=DEFAULT_EVENT_HOURS))
    return end < now


def overlaps(start: datetime, end: datetime):
    """SQL: the event has an occurrence (or its own start/end) overlapping [start, end)."""
    occ = exists(select(Occurrence.id).where(
        Occurrence.event_id == Event.id, Occurrence.starts_at < end,
        event_end(Occurrence.starts_at, Occurrence.ends_at) > start))
    own = and_(Event.starts_at.isnot(None), Event.starts_at < end,
               event_end(Event.starts_at, Event.ends_at) > start)
    return or_(occ, own)


def common_conditions(model, f: Filters, lon_sql, lat_sql, origin) -> list:
    """Conditions that apply the same way to places and events."""
    conds = []
    if f.bbox:
        w, s, e, n = f.bbox
        env = func.ST_MakeEnvelope(w, s, e, n, 4326).cast(GEOG)
        conds += [model.geom.op("&&")(env), lon_sql.between(w, e), lat_sql.between(s, n)]
    if f.tags:
        conds.append(model.tags.contains(f.tags))
    if f.cats:
        conds.append(model.category.in_(f.cats))
    if f.status:
        alts = []
        mine = f.status & set(MY_STATUSES)
        if mine:
            alts.append(UserItemState.status.in_(mine))
        if "suggested" in f.status:
            alts.append(model.review_status == "suggested")
        if "review" in f.status:
            alts.append(model.review_status == "needs_review")
        conds.append(or_(*alts))
    else:
        conds += [model.review_status != "dismissed",
                  or_(UserItemState.status.is_(None), UserItemState.status != "dismissed")]
    if f.dist_km:
        conds.append(func.ST_DWithin(model.geom, origin, f.dist_km * 1000))
    if f.q:
        name = model.name if model is Place else model.title
        tsq = func.websearch_to_tsquery(literal_column("'english'::regconfig"), f.q)
        conds.append(or_(model.search.op("@@")(tsq), func.similarity(name, f.q) > 0.3))
    return conds


def place_conditions(f: Filters) -> list:
    conds = []
    if f.price:
        alts = []
        if "free" in f.price:
            alts.append(Place.price_level == 0)
        if "1" in f.price:
            alts.append(Place.price_level == 1)
        if "2" in f.price:
            alts.append(Place.price_level == 2)
        if "3" in f.price:
            alts.append(Place.price_level >= 3)
        conds.append(or_(*alts))
    return conds


def event_conditions(f: Filters) -> list:
    conds = []
    now = f.now
    if f.archive:
        conds.append(archived(now))
    elif not f.past:
        conds.append(~archived(now))
    if f.window:
        # Recurring events always pass; undated one-offs are dropped
        conds.append(or_(recurring(), overlaps(*f.window)))
    if f.open_now:
        conds.append(overlaps(now, now + timedelta(seconds=1)))
    if f.price:
        price = func.coalesce(Event.price_min, Event.price_max)
        alts = []
        if "free" in f.price:
            alts.append(Event.is_free.is_(True))
        if "1" in f.price:
            alts.append(price < LOW)
        if "2" in f.price:
            alts.append(price.between(LOW, HIGH))
        if "3" in f.price:
            alts.append(price > HIGH)
        conds.append(or_(*alts))
    return conds


def my_state(model, user_id: int):
    """Outer join condition for the caller's user_item_state row."""
    col = UserItemState.place_id if model is Place else UserItemState.event_id
    return and_(col == model.id, UserItemState.user_id == user_id)
