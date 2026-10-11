"""Picker candidates from the database."""
import uuid
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from geoalchemy2.shape import to_shape
from sqlalchemy import case, func, literal_column, select
from sqlalchemy.orm import Session

from app.db.models import Event, Occurrence, Place, UserItemState
from app.plan.osrm import Point
from app.plan.picker import EVENT_STAY_MIN, Candidate, event_price, place_price

STATUS_RANK = {"going": 3, "want": 2, "been": 1}
MAX_RADIUS_M = 80_000


def _origin(p: Point):
    return func.ST_GeogFromText(f"SRID=4326;POINT({p[1]:.6f} {p[0]:.6f})")


def _states(db: Session, col, ids: list[uuid.UUID]) -> dict[uuid.UUID, dict]:
    """Our combined status and mean rating per item; dismissed by anyone wins."""
    out: dict[uuid.UUID, dict] = defaultdict(lambda: {"status": None, "ratings": [], "dismissed": False})
    if not ids:
        return out
    for row in db.scalars(select(UserItemState).where(col.in_(ids))):
        s = out[getattr(row, col.key)]
        if row.status == "dismissed":
            s["dismissed"] = True
        elif STATUS_RANK.get(row.status or "", 0) > STATUS_RANK.get(s["status"] or "", 0):
            s["status"] = row.status
        if row.rating:
            s["ratings"].append(row.rating)
    return out


def _rating(s: dict) -> float | None:
    return round(sum(s["ratings"]) / len(s["ratings"]), 1) if s["ratings"] else None


def load_candidates(db: Session, start: datetime, end: datetime, origin: Point, reach_m: float,
                    tz: str) -> list[Candidate]:
    """Events with an occurrence overlapping [start, end] within reach of the origin, and places
    within twice that (a food stop can be one hop past the anchor)."""
    zone = ZoneInfo(tz)
    here = _origin(origin)
    minute = literal_column("interval '1 minute'")
    occ_end = func.coalesce(Occurrence.ends_at, case(
        (Event.all_day, Occurrence.starts_at + literal_column("interval '1 day'")),
        else_=Occurrence.starts_at + func.coalesce(Event.duration_min, EVENT_STAY_MIN) * minute))
    rows = db.execute(
        select(Event, Occurrence.starts_at, occ_end)
        .join(Occurrence, Occurrence.event_id == Event.id)
        .where(Occurrence.starts_at < end, occ_end > start,
               Event.status == "scheduled", Event.review_status != "dismissed",
               func.ST_DWithin(Event.geom, here, min(reach_m, MAX_RADIUS_M)))
        .order_by(Occurrence.starts_at)).all()
    first: dict[uuid.UUID, tuple] = {}
    for ev, s, e in rows:
        first.setdefault(ev.id, (ev, s, e))
    ev_states = _states(db, UserItemState.event_id, list(first))
    out = []
    for ev, s, e in first.values():
        st = ev_states[ev.id]
        if st["dismissed"]:
            continue
        p = to_shape(ev.geom)
        out.append(Candidate(
            id=str(ev.id), type="event", title=ev.title, lat=p.y, lon=p.x, category=ev.category,
            tags=list(ev.tags or []), price_pp=event_price(ev.price_min, ev.is_free),
            starts_at=s.astimezone(zone), ends_at=e.astimezone(zone) if e else None,
            status=st["status"], rating=_rating(st), address=ev.address_text, venue=ev.venue_name,
            place_id=str(ev.place_id) if ev.place_id else None, url=ev.ticket_url,
            suggested=ev.review_status == "suggested"))

    places = db.scalars(
        select(Place).where(Place.review_status != "dismissed", Place.closed.is_(False),
                            func.ST_DWithin(Place.geom, here, min(2 * reach_m, MAX_RADIUS_M)))).all()
    pl_states = _states(db, UserItemState.place_id, [p.id for p in places])
    for pl in places:
        st = pl_states[pl.id]
        if st["dismissed"]:
            continue
        p = to_shape(pl.geom)
        out.append(Candidate(
            id=str(pl.id), type="place", title=pl.name, lat=p.y, lon=p.x, category=pl.category,
            tags=list(pl.tags or []), price_pp=place_price(pl.price_level), opening_hours=pl.opening_hours,
            status=st["status"], rating=_rating(st), address=pl.address_text, url=pl.website,
            suggested=pl.review_status == "suggested"))
    return out
