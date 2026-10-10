"""Map pins (GeoJSON) and the list view, both driven by the shared filters."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.api.auth import current_user
from app.api.common import event_price_label, has_image, place_price_label
from app.api.filters import (
    GEOM, Filters, common_conditions, event_conditions, event_end, filters_dep, my_state, place_conditions,
    point_sql,
)
from app.db.models import Event, ItemSource, Occurrence, Place, Source, User, UserItemState
from app.db.session import get_db
from app.ingest.store import home_point

router = APIRouter()

MAX_ROWS = 2000
MAX_TAGS = 5
SORTS = ("date", "distance", "recent", "name")


def _lonlat(model):
    g = model.geom.cast(GEOM)
    return func.ST_X(g), func.ST_Y(g)


def _thumb_src(model):
    """First linked source that has a picture, or NULL."""
    link = ItemSource.place_id if model is Place else ItemSource.event_id
    return (select(Source.id).join(ItemSource, ItemSource.source_id == Source.id)
            .where(link == model.id, has_image())
            .order_by(ItemSource.position, Source.created_at).limit(1)
            .correlate(model).scalar_subquery())


def place_query(f: Filters, user_id: int, origin) -> Select:
    lon, lat = _lonlat(Place)
    q = (select(Place.id, Place.name.label("title"), Place.category, lon.label("lon"), lat.label("lat"),
                Place.price_level, Place.review_status, UserItemState.status.label("my"),
                UserItemState.rating, Place.address_text, Place.tags, Place.opening_hours,
                Place.created_at, func.ST_Distance(Place.geom, origin).label("dist"),
                _thumb_src(Place).label("thumb_src"))
         .outerjoin(UserItemState, my_state(Place, user_id))
         .where(*common_conditions(Place, f, lon, lat, origin), *place_conditions(f)))
    return q


def event_query(f: Filters, user_id: int, origin) -> Select:
    lon, lat = _lonlat(Event)
    ref = f.window[0] if f.window else f.now
    # Next occurrence that has not ended (or that is in the window), else the event's own start
    upcoming = (select(func.min(Occurrence.starts_at))
                .where(Occurrence.event_id == Event.id, event_end(Occurrence.starts_at, Occurrence.ends_at) > ref)
                .correlate(Event).scalar_subquery())
    q = (select(Event.id, Event.title, Event.category, lon.label("lon"), lat.label("lat"),
                func.coalesce(upcoming, Event.starts_at).label("start"), Event.starts_at, Event.ends_at,
                Event.all_day, func.coalesce(Event.recurrence_text, Event.rrule).label("rec"),
                Event.is_free, Event.price_min, Event.price_max, Event.price_text, Event.currency,
                Event.review_status, UserItemState.status.label("my"), UserItemState.rating,
                Event.address_text, Event.venue_name, Event.tags, Event.created_at,
                func.ST_Distance(Event.geom, origin).label("dist"), _thumb_src(Event).label("thumb_src"))
         .outerjoin(UserItemState, my_state(Event, user_id))
         .where(*common_conditions(Event, f, lon, lat, origin), *event_conditions(f)))
    return q


def _iso(d: datetime | None) -> str | None:
    return d.isoformat() if d else None


def place_props(r) -> dict:
    return {
        "id": str(r.id), "t": "place", "title": r.title, "cat": r.category,
        "start": None, "end": None, "all_day": False, "rec": None,
        "price": place_price_label(r.price_level), "free": r.price_level == 0,
        "rs": r.review_status, "my": r.my, "rating": r.rating,
        "addr": r.address_text, "venue": None,
        "dist_m": round(r.dist) if r.dist is not None else None,
        "thumb": r.thumb_src is not None, **({"thumb_src": str(r.thumb_src)} if r.thumb_src else {}),
        "tags": list(r.tags or [])[:MAX_TAGS],
    }


def event_props(r) -> dict:
    end = r.ends_at
    if r.start and r.starts_at and r.ends_at and r.start != r.starts_at:
        end = r.start + (r.ends_at - r.starts_at)  # a later occurrence of a recurring event
    return {
        "id": str(r.id), "t": "event", "title": r.title, "cat": r.category,
        "start": _iso(r.start), "end": _iso(end), "all_day": bool(r.all_day), "rec": r.rec,
        "price": event_price_label(r.is_free, r.price_min, r.price_max, r.price_text, r.currency),
        "free": bool(r.is_free),
        "rs": r.review_status, "my": r.my, "rating": r.rating,
        "addr": r.address_text, "venue": r.venue_name,
        "dist_m": round(r.dist) if r.dist is not None else None,
        "thumb": r.thumb_src is not None, **({"thumb_src": str(r.thumb_src)} if r.thumb_src else {}),
        "tags": list(r.tags or [])[:MAX_TAGS],
    }


def keep_place(r, f: Filters) -> bool:
    """Checks done in Python after the query."""
    return True


def fetch_items(db: Session, f: Filters, user: User, sort: str = "date") -> list[tuple[dict, object]]:
    """(properties + lat/lon, row) for every matching item, one query per type."""
    origin = point_sql(*(f.near or home_point(db)))
    out: list[tuple[dict, object]] = []
    if "place" in f.types:
        q = place_query(f, user.id, origin)
        q = q.order_by(*{"distance": [q.selected_columns.dist], "recent": [Place.created_at.desc()]}
                       .get(sort, [func.lower(Place.name)]))
        for r in db.execute(q.limit(MAX_ROWS)).all():
            if keep_place(r, f):
                out.append(({**place_props(r), "lat": r.lat, "lon": r.lon}, r))
    if "event" in f.types:
        q = event_query(f, user.id, origin)
        q = q.order_by(*{"distance": [q.selected_columns.dist], "recent": [Event.created_at.desc()],
                         "name": [func.lower(Event.title)]}
                       .get(sort, [q.selected_columns.start.asc().nulls_last(), func.lower(Event.title)]))
        for r in db.execute(q.limit(MAX_ROWS)).all():
            out.append(({**event_props(r), "lat": r.lat, "lon": r.lon}, r))
    return out


def sort_items(items: list[tuple[dict, object]], sort: str) -> list[dict]:
    if sort == "distance":
        items.sort(key=lambda it: (it[0]["dist_m"] is None, it[0]["dist_m"] or 0))
    elif sort == "recent":
        items.sort(key=lambda it: it[1].created_at, reverse=True)
    elif sort == "name":
        items.sort(key=lambda it: (it[0]["title"] or "").lower())
    else:
        # Dated events by next start, then undated events, then places, by name
        def key(it):
            p = it[0]
            group = 2 if p["t"] == "place" else (0 if p["start"] else 1)
            return group, it[1].start if group == 0 else datetime.min, (p["title"] or "").lower()
        items.sort(key=key)
    return [p for p, _ in items]


@router.get("/api/map")
def map_pins(f: Filters = Depends(filters_dep), db: Session = Depends(get_db), user: User = Depends(current_user)):
    if f.bbox is None:
        raise HTTPException(400, "bbox=w,s,e,n is required")
    items = sort_items(fetch_items(db, f, user, "distance"), "distance")[:MAX_ROWS]
    features = []
    for p in items:
        lat, lon = p.pop("lat"), p.pop("lon")
        features.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
                         "properties": p})
    return {"type": "FeatureCollection", "features": features}


@router.get("/api/list")
def list_items(f: Filters = Depends(filters_dep), sort: str = "date", limit: int = 50, offset: int = 0,
               db: Session = Depends(get_db), user: User = Depends(current_user)):
    if sort not in SORTS:
        raise HTTPException(400, f"sort must be one of {', '.join(SORTS)}")
    limit, offset = max(1, min(limit, 200)), max(0, offset)
    items = sort_items(fetch_items(db, f, user, sort), sort)
    page = items[offset:offset + limit]
    for p in page:
        p["lat"], p["lon"] = round(p["lat"], 6), round(p["lon"], 6)
    return {"items": page, "total": len(items)}
