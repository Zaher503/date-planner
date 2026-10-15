"""Save resolved items: create or merge places and events, link them to the source,
and keep the alternatives for the review picker. Fields the user edited are never overwritten."""
import re
from datetime import timedelta

from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import Point
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import AppSettings, Candidate as CandidateRow, Event, ItemSource, Occurrence, Place, Source
from app.ingest.items import ItemHint
from app.resolve.candidates import Candidate
from app.resolve.resolver import Resolution
from app.resolve.scorer import OSM_CATEGORY, name_similarity
from app.textclean import clean_name, strip_emoji

SAME_PLACE_M = 75
SAME_SERIES = 0.85  # title match that makes another date at the same venue part of one event
DEFAULT_MINUTES = {"live_music": 180, "show": 150, "comedy": 120, "festival": 240, "market": 240,
                   "class": 120, "sports": 180, "nightlife": 240, "activity": 120, "arts": 120}
PLACE_REVIEW_FLAGS = {"not a specific venue"}
EVENT_REVIEW_FLAGS = {"removed unverified date", "event with no date", "recurring series, dates unclear",
                      "start time has no time zone"}


def home_point(db: Session) -> tuple[float, float]:
    s = db.get(AppSettings, 1)
    if s is None or s.home is None:
        return 34.0522, -118.2437  # downtown LA until zone.home arrives
    p = to_shape(s.home)
    return p.y, p.x


def _pt(lat: float, lon: float):
    return from_shape(Point(lon, lat), srid=4326)


def _set(obj, field: str, value, *, overwrite: bool = False) -> None:
    """Fill a field unless the user edited it; only replace existing values when asked."""
    if field == "description":
        value = strip_emoji(value)
    if value in (None, "", []) or field in (obj.user_overrides or {}):
        return
    if overwrite or getattr(obj, field) in (None, "", []):
        setattr(obj, field, value)


def find_place(db: Session, cand: Candidate, name: str) -> Place | None:
    if cand.osm_type and cand.osm_id:
        p = db.scalars(select(Place).where(Place.osm_type == cand.osm_type, Place.osm_id == cand.osm_id)).first()
        if p:
            return p
    point = func.ST_GeogFromText(f"SRID=4326;POINT({cand.lon} {cand.lat})")
    nearby = db.scalars(select(Place).where(func.ST_DWithin(Place.geom, point, SAME_PLACE_M))
                        .order_by(func.similarity(Place.name, name).desc()).limit(5)).all()
    for p in nearby:
        if name_similarity(p.name, name) >= 0.7 or name_similarity(p.name, cand.name) >= 0.7:
            return p
    return None


def _place_name(hint: ItemHint, cand: Candidate) -> str:
    # Prefer the official spelling when it clearly is the same place
    if cand.kind == "poi" and cand.name and name_similarity(hint.name, cand.name) >= 0.8:
        return cand.name
    return clean_name(hint.name) or cand.name


def upsert_place(db: Session, hint: ItemHint, res: Resolution, user_id: int | None, origin: str = "manual",
                 existing: Place | None = None) -> tuple[Place, bool]:
    """existing: the place a link read before (a reread). It is updated in place, pin and name included as is."""
    cand = res.best
    name = _place_name(hint, cand)
    place = existing or find_place(db, cand, name)
    refresh = existing is not None
    created = place is None
    review = res.needs_review or bool(PLACE_REVIEW_FLAGS & set(hint.flags))
    if created:
        place = Place(name=name, geom=_pt(cand.lat, cand.lon), origin=origin, created_by=user_id,
                      review_status="needs_review" if review else ("suggested" if origin == "discovered" else "ok"),
                      confidence=res.confidence, tags=[], address={}, user_overrides={})
        db.add(place)
    elif place.review_status == "needs_review" and not review and "review_status" not in place.user_overrides:
        place.review_status = "ok"  # a stronger second source settles it
    if not created and res.confidence > (place.confidence or 0):
        place.confidence = res.confidence

    extra = cand.extra or {}
    _set(place, "category", hint.category or OSM_CATEGORY.get(cand.osm_value or "") or "other", overwrite=refresh)
    new_addr = cand.address_text or hint.address
    # A house-numbered address replaces a street-only one from an earlier, vaguer source
    precise = bool(new_addr and re.match(r"\s*\d", new_addr)) and not re.match(r"\s*\d", place.address_text or "")
    _set(place, "address_text", new_addr, overwrite=precise)
    _set(place, "website", hint.website or extra.get("website"), overwrite=refresh)
    _set(place, "phone", hint.phone or extra.get("phone"), overwrite=refresh)
    _set(place, "opening_hours", hint.opening_hours or extra.get("opening_hours"), overwrite=refresh)
    _set(place, "hours_text", hint.hours_text, overwrite=refresh)
    if hint.kind == "place":
        _set(place, "price_tiers", hint.price_tiers, overwrite=refresh)
        _set(place, "price_text", hint.price_text, overwrite=refresh)
    _set(place, "price_level", hint.price_level if hint.price_level is not None else extra.get("price_level"),
         overwrite=refresh)
    _set(place, "description", hint.description if hint.kind == "place" else None, overwrite=refresh)
    if cand.osm_type and cand.osm_id and place.osm_id is None:
        clash = db.scalars(select(Place.id).where(Place.osm_type == cand.osm_type, Place.osm_id == cand.osm_id)).first()
        if clash is None:
            place.osm_type, place.osm_id = cand.osm_type, cand.osm_id
    if "tags" not in place.user_overrides:
        cuisine = [c.strip() for c in (extra.get("cuisine") or "").split(";") if c.strip()]
        place.tags = list(dict.fromkeys([*(place.tags or []), *hint.tags, *cuisine]))[:12]
    db.flush()
    return place, created


def _event_minutes(hint: ItemHint) -> tuple[int | None, bool]:
    if hint.starts_at and hint.ends_at:
        return int((hint.ends_at - hint.starts_at).total_seconds() // 60), False
    if hint.all_day or not hint.starts_at:
        return None, False
    return DEFAULT_MINUTES.get(hint.category or "", 120), True


def _series_match(db: Session, place: Place, title: str) -> Event | None:
    """An event at this venue with the same title: this date belongs to it."""
    rows = db.scalars(select(Event).where(Event.place_id == place.id, Event.starts_at.is_not(None),
                                          Event.review_status != "dismissed")).all()
    return next((e for e in rows if name_similarity(e.title, title) >= SAME_SERIES), None)


def upsert_event(db: Session, hint: ItemHint, place: Place, res: Resolution, user_id: int | None,
                 origin: str = "manual", existing: Event | None = None) -> tuple[Event, bool]:
    """existing: the event a link read before (a reread). It is updated in place, never matched again."""
    title = hint.event_title or hint.name
    refresh = existing is not None
    event = existing
    another_date = False
    if event is None:
        q = select(Event).where(Event.place_id == place.id)
        if hint.starts_at:
            q = q.where(Event.starts_at.between(hint.starts_at - timedelta(minutes=60),
                                                hint.starts_at + timedelta(minutes=60)))
        else:
            q = q.where(Event.starts_at.is_(None))
        event = next((e for e in db.scalars(q).all() if name_similarity(e.title, title) >= 0.6), None)
        if event is None and hint.starts_at:
            event = _series_match(db, place, title)
            another_date = event is not None
    elif hint.starts_at and event.starts_at != hint.starts_at:
        another_date = True  # the link now shows a date the event did not have
    created = event is None
    minutes, estimated = _event_minutes(hint)
    review = place.review_status == "needs_review" or bool(EVENT_REVIEW_FLAGS & set(hint.flags))
    if created:
        event = Event(title=title, place_id=place.id, geom=place.geom, venue_name=place.name,
                      address_text=place.address_text, origin=origin, created_by=user_id,
                      review_status="needs_review" if review else ("suggested" if origin == "discovered" else "ok"),
                      confidence=res.confidence, tags=[], user_overrides={},
                      tz=hint.tz or "America/Los_Angeles")
        db.add(event)
    _set(event, "category", hint.category or place.category, overwrite=refresh)
    _set(event, "description", hint.description, overwrite=refresh)
    end = hint.ends_at or (hint.starts_at + timedelta(minutes=minutes) if hint.starts_at and minutes else None)
    if (not created and hint.starts_at and event.starts_at and hint.starts_at < event.starts_at
            and not {"starts_at", "ends_at"} & set(event.user_overrides or {})):
        event.starts_at, event.ends_at = hint.starts_at, end  # the event shows its earliest date
    _set(event, "starts_at", hint.starts_at)
    _set(event, "ends_at", end)
    _set(event, "duration_min", minutes)
    if created:
        event.duration_estimated = estimated
        event.all_day = hint.all_day
        event.status = hint.status
    _set(event, "recurrence_text", hint.recurrence, overwrite=refresh)
    for f in ("price_min", "price_max", "currency", "is_free", "price_text", "ticket_url"):
        _set(event, f, getattr(hint, f), overwrite=refresh)
    if "tags" not in event.user_overrides:
        event.tags = list(dict.fromkeys([*(event.tags or []), *hint.tags]))[:12]
    db.flush()
    if another_date:
        # Another date of an event we already have is one more occurrence, not a second event
        db.execute(insert(Occurrence).values(event_id=event.id, starts_at=hint.starts_at, ends_at=end)
                   .on_conflict_do_nothing(constraint="uq_occurrence"))
    if event.starts_at:
        db.execute(insert(Occurrence).values(event_id=event.id, starts_at=event.starts_at, ends_at=event.ends_at)
                   .on_conflict_do_nothing(constraint="uq_occurrence"))
    return event, created


def link(db: Session, source: Source, *, place: Place | None = None, event: Event | None = None,
         position: int = 0, confidence: float | None = None) -> None:
    values = {"source_id": source.id, "position": position, "confidence": confidence}
    if event is not None:
        values["event_id"], idx = event.id, "uq_item_sources_event"
        where = text("event_id IS NOT NULL")
    else:
        values["place_id"], idx = place.id, "uq_item_sources_place"
        where = text("place_id IS NOT NULL")
    cols = ["source_id", "event_id" if event is not None else "place_id"]
    db.execute(insert(ItemSource).values(**values).on_conflict_do_nothing(index_elements=cols, index_where=where))


def save_candidates(db: Session, source: Source, place: Place, index: int, res: Resolution) -> None:
    db.query(CandidateRow).filter(CandidateRow.source_id == source.id, CandidateRow.item_index == index).delete()
    for c, chosen in [(res.best, True), *((a, False) for a in res.alternatives)]:
        db.add(CandidateRow(source_id=source.id, place_id=place.id, item_index=index, provider=c.provider,
                            name=c.name or place.name, geom=_pt(c.lat, c.lon), address_text=c.address_text,
                            payload=c.as_payload(), score=c.score, chosen=chosen))
