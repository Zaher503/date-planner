"""One place or event: detail, edits, my status, delete and reprocess."""
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Body, Depends, HTTPException, Response
from fastapi.exceptions import RequestValidationError
from geoalchemy2.shape import from_shape, to_shape
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from shapely.geometry import Point
from sqlalchemy import delete, exists, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app import jobs
from app.api.auth import current_user
from app.api.common import event_price_label, image_url, place_price_label
from app.config import get_settings
from app.db.models import (
    Candidate, Event, ItemSource, Job, Media, Occurrence, Place, Source, User, UserItemState,
)
from app.db.session import get_db
from app.hours import is_open
from app.ingest import media

router = APIRouter()

ItemType = Literal["place", "event"]
# Source kinds the ingest job can read again (Instagram is a stub, discovery rows have no link to read)
REPROCESSABLE = {"tiktok", "youtube", "gmaps", "applemaps", "event_page", "text", "image"}
CAPTION_CHARS = 500
MAX_TAGS = 20
NOT_NULL = {"title", "tags", "lat", "lon", "closed", "all_day", "status", "review_status"}


def _tz() -> ZoneInfo:
    return ZoneInfo(get_settings().default_tz)


def _latlon(geom) -> tuple[float, float]:
    p = to_shape(geom)
    return round(p.y, 6), round(p.x, 6)


def _iso(d: datetime | date | None) -> str | None:
    return d.isoformat() if d else None


def _num(v) -> float | None:
    return float(v) if v is not None else None


def load(db: Session, type_: str, item_id: uuid.UUID) -> Place | Event:
    item = db.get(Place if type_ == "place" else Event, item_id)
    if item is None:
        raise HTTPException(404, f"no such {type_}")
    return item


def _link_col(item: Place | Event):
    return ItemSource.place_id if isinstance(item, Place) else ItemSource.event_id


def _state_col(item: Place | Event):
    return UserItemState.place_id if isinstance(item, Place) else UserItemState.event_id


def linked_sources(db: Session, item: Place | Event) -> list[Source]:
    ids = select(ItemSource.source_id).where(_link_col(item) == item.id)
    return list(db.scalars(select(Source).where(Source.id.in_(ids)).order_by(Source.created_at)).all())


def _me(row: UserItemState | None) -> dict | None:
    if row is None:
        return None
    return {"status": row.status, "rating": row.rating, "notes": row.notes, "visited_at": _iso(row.visited_at)}


def _candidates(db: Session, place_id) -> list[dict]:
    cands = db.scalars(select(Candidate).where(Candidate.place_id == place_id)
                       .order_by(Candidate.chosen.desc(), Candidate.score.desc())).all()
    out = []
    for c in cands:
        lat, lon = _latlon(c.geom) if c.geom is not None else (None, None)
        out.append({"id": c.id, "name": c.name, "address": c.address_text, "score": c.score,
                    "provider": c.provider, "chosen": c.chosen, "lat": lat, "lon": lon})
    return out


def detail(db: Session, item: Place | Event, user: User) -> dict:
    is_place = isinstance(item, Place)
    lat, lon = _latlon(item.geom)
    out = {
        "id": str(item.id), "type": "place" if is_place else "event",
        "title": item.name if is_place else item.title, "category": item.category,
        "description": item.description, "tags": list(item.tags or []), "lat": lat, "lon": lon,
        "address_text": item.address_text, "review_status": item.review_status,
        "confidence": item.confidence, "origin": item.origin,
        "created_at": _iso(item.created_at), "updated_at": _iso(item.updated_at),
        "edited": sorted((item.user_overrides or {}).keys()),
    }
    review_place = None
    if is_place:
        events = db.scalars(select(Event).where(Event.place_id == item.id, Event.review_status != "dismissed")
                            .order_by(Event.starts_at.asc().nulls_last()).limit(50)).all()
        out.update({
            "price_label": place_price_label(item.price_level),
            "website": item.website, "phone": item.phone, "opening_hours": item.opening_hours,
            "open_now": is_open(item.opening_hours, datetime.now(_tz())),
            "price_level": item.price_level, "closed": item.closed,
            "events": [{"id": str(e.id), "title": e.title, "starts_at": _iso(e.starts_at),
                        "recurrence_text": e.recurrence_text} for e in events],
        })
        if item.review_status == "needs_review":
            review_place = item
    else:
        place = db.get(Place, item.place_id) if item.place_id else None
        out.update({
            "price_label": event_price_label(item.is_free, item.price_min, item.price_max, item.price_text,
                                             item.currency),
            "starts_at": _iso(item.starts_at), "ends_at": _iso(item.ends_at), "duration_min": item.duration_min,
            "duration_estimated": item.duration_estimated, "all_day": item.all_day,
            "recurrence_text": item.recurrence_text, "tz": item.tz,
            "price_min": _num(item.price_min), "price_max": _num(item.price_max), "currency": item.currency,
            "is_free": item.is_free, "price_text": item.price_text, "ticket_url": item.ticket_url,
            "status": item.status, "venue_name": item.venue_name,
            "place": {"id": str(place.id), "title": place.name} if place else None,
        })
        if place is not None and place.review_status == "needs_review":
            review_place = place

    names = {u.id: u.display_name or u.username for u in db.scalars(select(User)).all()}
    sources = linked_sources(db, item)
    archived = {(m.source_id, m.kind) for m in db.scalars(
        select(Media).where(Media.source_id.in_([s.id for s in sources]))).all()} if sources else set()
    out["sources"] = [{
        "id": str(s.id), "kind": s.kind, "url": s.url, "title": s.title,
        "caption": (s.caption or "")[:CAPTION_CHARS] or None,
        "thumb": f"/api/thumb/{s.id}" if (image_url(s.raw) or s.kind == "image"
                                          or (s.id, "thumb") in archived) else None,
        "video": f"/api/media/{s.id}/video" if (s.id, "video") in archived else None,
        "created_at": _iso(s.created_at), "submitted_by": names.get(s.submitted_by),
    } for s in sources]
    states = db.scalars(select(UserItemState).where(_state_col(item) == item.id)).all()
    out["me"] = _me(next((s for s in states if s.user_id == user.id), None))
    out["others"] = [{"user": names.get(s.user_id), "status": s.status, "rating": s.rating, "notes": s.notes}
                     for s in states if s.user_id != user.id]
    out["candidates"] = _candidates(db, review_place.id) if review_place is not None else []
    return out


@router.get("/api/items/{type_}/{item_id}")
def get_item(type_: ItemType, item_id: uuid.UUID, db: Session = Depends(get_db),
             user: User = Depends(current_user)):
    return detail(db, load(db, type_, item_id), user)


class PlacePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(None, max_length=300)
    category: str | None = Field(None, max_length=60)
    description: str | None = Field(None, max_length=10000)
    tags: list[str] | None = Field(None, max_length=50)
    address_text: str | None = Field(None, max_length=500)
    website: str | None = Field(None, max_length=2000)
    phone: str | None = Field(None, max_length=60)
    opening_hours: str | None = Field(None, max_length=500)
    price_level: int | None = Field(None, ge=0, le=4)
    lat: float | None = Field(None, ge=-90, le=90)
    lon: float | None = Field(None, ge=-180, le=180)
    closed: bool | None = None
    review_status: Literal["ok", "dismissed"] | None = None


class EventPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(None, max_length=300)
    category: str | None = Field(None, max_length=60)
    description: str | None = Field(None, max_length=10000)
    tags: list[str] | None = Field(None, max_length=50)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    all_day: bool | None = None
    recurrence_text: str | None = Field(None, max_length=300)
    price_min: float | None = Field(None, ge=0)
    price_max: float | None = Field(None, ge=0)
    is_free: bool | None = None
    price_text: str | None = Field(None, max_length=300)
    ticket_url: str | None = Field(None, max_length=2000)
    status: Literal["scheduled", "cancelled", "archived"] | None = None
    review_status: Literal["ok", "dismissed"] | None = None
    lat: float | None = Field(None, ge=-90, le=90)
    lon: float | None = Field(None, ge=-180, le=180)


def clean_tags(tags: list[str]) -> list[str]:
    return list(dict.fromkeys(t.strip() for t in tags if t and t.strip()))[:MAX_TAGS]


def patch_changes(kind: str, sent: dict) -> dict:
    """Column values for the keys that were sent: place title -> name, lat + lon -> geom (lat, lon)."""
    if ("lat" in sent) != ("lon" in sent):
        raise HTTPException(400, "send lat and lon together")
    for k in NOT_NULL & sent.keys():
        if sent[k] is None:
            raise HTTPException(400, f"{k} cannot be null")
    cols: dict = {}
    for k, v in sent.items():
        if k in ("lat", "lon"):
            continue
        if isinstance(v, str):
            v = v.strip() or None
        if k == "title" and v is None:
            raise HTTPException(400, "title cannot be empty")
        if k == "tags":
            v = clean_tags(v)
        cols["name" if k == "title" and kind == "place" else k] = v
    if "lat" in sent:
        cols["geom"] = (sent["lat"], sent["lon"])
    return cols


def _same(cur, new) -> bool:
    if isinstance(cur, Decimal) or isinstance(new, Decimal):
        return cur is not None and new is not None and float(cur) == float(new)
    return cur == new


def apply_changes(item: Place | Event, cols: dict) -> set[str]:
    """Write the values that differ; returns the changed column names."""
    changed = set()
    for col, v in cols.items():
        if col == "geom":
            if _latlon(item.geom) != (round(v[0], 6), round(v[1], 6)):
                item.geom = from_shape(Point(v[1], v[0]), srid=4326)
                changed.add(col)
        elif not _same(getattr(item, col), v):
            setattr(item, col, v)
            changed.add(col)
    return changed


def _event_times(ev: Event, cols: dict) -> None:
    """Local times without an offset are in the event's zone; keep end after start."""
    zone = ZoneInfo(ev.tz or get_settings().default_tz)
    for k in ("starts_at", "ends_at"):
        if cols.get(k) is not None and cols[k].tzinfo is None:
            cols[k] = cols[k].replace(tzinfo=zone)
    if "starts_at" in cols and "ends_at" not in cols and ev.starts_at and ev.ends_at and cols["starts_at"]:
        cols["ends_at"] = cols["starts_at"] + (ev.ends_at - ev.starts_at)  # keep the duration
    start = cols.get("starts_at", ev.starts_at)
    end = cols.get("ends_at", ev.ends_at)
    if start and end and end < start:
        raise HTTPException(400, "ends_at is before starts_at")
    lo, hi = cols.get("price_min", ev.price_min), cols.get("price_max", ev.price_max)
    if lo is not None and hi is not None and float(hi) < float(lo):
        raise HTTPException(400, "price_max is below price_min")


def _after_event_change(db: Session, ev: Event, changed: set[str], sent: set[str]) -> None:
    if not changed & {"starts_at", "ends_at"}:
        return
    if ev.starts_at and ev.ends_at:
        ev.duration_min = int((ev.ends_at - ev.starts_at).total_seconds() // 60)
        if "ends_at" in sent:
            ev.duration_estimated = False
    if not ev.rrule:
        # A one-off event has exactly one occurrence
        db.execute(delete(Occurrence).where(Occurrence.event_id == ev.id))
        if ev.starts_at:
            db.add(Occurrence(event_id=ev.id, starts_at=ev.starts_at, ends_at=ev.ends_at))


def _after_place_change(db: Session, place: Place, changed: set[str], was_review: bool) -> None:
    """Events at the place follow its pin, name and address unless edited themselves."""
    for col, ev_col, value in (("geom", "geom", place.geom), ("name", "venue_name", place.name),
                               ("address_text", "address_text", place.address_text)):
        if col in changed:
            db.execute(update(Event).where(Event.place_id == place.id, ~Event.user_overrides.has_key(ev_col))
                       .values({ev_col: value}))
    if "review_status" in changed and was_review and place.review_status == "ok":
        # Confirmed by a person, like choosing in the review picker
        place.confidence = 1.0
        db.execute(update(Event).where(Event.place_id == place.id, Event.review_status == "needs_review")
                   .values(review_status="ok"))


@router.patch("/api/items/{type_}/{item_id}")
def patch_item(type_: ItemType, item_id: uuid.UUID, body: dict = Body(...), db: Session = Depends(get_db),
               user: User = Depends(current_user)):
    model = PlacePatch if type_ == "place" else EventPatch
    try:
        data = model.model_validate(body)
    except ValidationError as e:
        raise RequestValidationError(e.errors(include_url=False)) from None
    sent = data.model_fields_set
    item = load(db, type_, item_id)
    cols = patch_changes(type_, {k: getattr(data, k) for k in sent})
    if isinstance(item, Event):
        _event_times(item, cols)
    was_review = item.review_status == "needs_review"
    changed = apply_changes(item, cols)
    if isinstance(item, Event):
        _after_event_change(db, item, changed, sent)
    else:
        _after_place_change(db, item, changed, was_review)
    if changed:
        item.user_overrides = {**(item.user_overrides or {}), **{c: True for c in changed}}
    db.commit()
    db.refresh(item)  # times come back in UTC like everywhere else
    return detail(db, item, user)


@router.delete("/api/items/{type_}/{item_id}", status_code=204)
def delete_item(type_: ItemType, item_id: uuid.UUID, db: Session = Depends(get_db),
                _: User = Depends(current_user)):
    item = load(db, type_, item_id)
    source_ids = set(db.scalars(select(ItemSource.source_id).where(_link_col(item) == item.id)).all())
    if isinstance(item, Place):
        event_ids = select(Event.id).where(Event.place_id == item.id)
        source_ids |= set(db.scalars(select(ItemSource.source_id).where(ItemSource.event_id.in_(event_ids))).all())
        db.execute(delete(Event).where(Event.place_id == item.id))
    db.delete(item)
    db.flush()
    # Sources left with no items go too, so the same link can be added again
    orphans = db.scalars(select(Source.id).where(
        Source.id.in_(source_ids), ~exists().where(ItemSource.source_id == Source.id))).all() if source_ids else []
    if orphans:
        db.execute(delete(Source).where(Source.id.in_(orphans)))
    db.commit()
    thumbs = get_settings().data_dir / "media" / "thumbs"
    for sid in orphans:
        for f in thumbs.glob(f"{sid}.*"):
            f.unlink(missing_ok=True)
        media.remove(sid)
    return Response(status_code=204)


class MeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["want", "going", "been", "dismissed"] | None = None
    rating: int | None = Field(None, ge=1, le=5)
    notes: str | None = Field(None, max_length=10000)
    visited_at: date | None = None


@router.put("/api/items/{type_}/{item_id}/me")
def put_me(type_: ItemType, item_id: uuid.UUID, body: MeIn, db: Session = Depends(get_db),
           user: User = Depends(current_user)):
    item = load(db, type_, item_id)
    col = "place_id" if type_ == "place" else "event_id"
    db.execute(insert(UserItemState).values(user_id=user.id, **{col: item.id})
               .on_conflict_do_nothing(index_elements=["user_id", col], index_where=text(f"{col} IS NOT NULL")))
    row = db.scalars(select(UserItemState).where(UserItemState.user_id == user.id,
                                                 _state_col(item) == item.id)).one()
    sent = body.model_fields_set
    for k in sent:
        setattr(row, k, getattr(body, k))
    if body.status == "been" and "status" in sent and "visited_at" not in sent and row.visited_at is None:
        row.visited_at = datetime.now(_tz()).date()
    db.commit()
    return _me(row)


@router.post("/api/items/{type_}/{item_id}/reprocess")
def reprocess(type_: ItemType, item_id: uuid.UUID, db: Session = Depends(get_db),
              user: User = Depends(current_user)):
    """Queue a fresh ingest for every linked source; user edits survive through user_overrides."""
    item = load(db, type_, item_id)
    job_ids = []
    for src in linked_sources(db, item):
        if src.kind not in REPROCESSABLE:
            continue
        running = db.scalars(select(Job.id).where(Job.source_id == src.id, Job.type == "ingest",
                                                  Job.status.in_(("queued", "running")))).first()
        if running:
            job_ids.append(running)
            continue
        src.status, src.error = "pending", None
        job = jobs.enqueue(db, "ingest", {"source_id": str(src.id)}, source_id=src.id, needs_gpu=True,
                           submitted_by=user.id)
        job_ids.append(job.id)
    db.commit()
    return {"jobs": job_ids}
