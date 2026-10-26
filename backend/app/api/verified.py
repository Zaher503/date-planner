"""Save items that were checked by hand (the daily import check) as real places and events.

Same save code as the ingest job, but the values come from the caller. A place or event that
already exists is not duplicated: missing fields are filled and wrong ones replaced, except
fields a person edited in the app (user_overrides)."""
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import hours
from app.api.auth import require_key
from app.db.models import Source
from app.db.session import get_db
from app.ingest import images, pipeline, store
from app.ingest.items import CATEGORIES, ItemHint
from app.ingest.urls import classify, normalize
from app.resolve import resolver

router = APIRouter()
log = logging.getLogger(__name__)

PLACE_FIELDS = ("name", "category", "address_text", "website", "phone", "opening_hours", "hours_text",
                "price_level", "price_text", "price_tiers", "description", "tags")
EVENT_FIELDS = ("title", "category", "description", "starts_at", "ends_at", "duration_min", "recurrence_text",
                "price_min", "price_max", "currency", "is_free", "price_text", "ticket_url", "tags")


class VerifiedItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["place", "event"] = "place"
    name: str = Field(min_length=1, max_length=300)  # the place, or the venue of an event
    event_title: str | None = Field(default=None, max_length=300)
    address: str | None = Field(default=None, max_length=300)
    area: str | None = Field(default=None, max_length=120)
    inside: str | None = Field(default=None, max_length=200)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    exact_pin: bool = False
    category: str | None = None
    description: str | None = Field(default=None, max_length=4000)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    all_day: bool = False
    tz: str | None = None
    recurrence: str | None = Field(default=None, max_length=300)
    price_min: float | None = Field(default=None, ge=0)
    price_max: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, max_length=3)
    is_free: bool | None = None
    price_text: str | None = Field(default=None, max_length=500)
    price_tiers: list[dict] = Field(default_factory=list, max_length=20)
    ticket_url: str | None = Field(default=None, max_length=2000)
    website: str | None = Field(default=None, max_length=2000)
    phone: str | None = Field(default=None, max_length=40)
    opening_hours: str | None = Field(default=None, max_length=500)
    hours_text: str | None = Field(default=None, max_length=500)
    price_level: int | None = Field(default=None, ge=0, le=4)
    tags: list[str] = Field(default_factory=list, max_length=12)
    images: list[str] = Field(default_factory=list, max_length=12)


class VerifiedIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(min_length=8, max_length=4000)  # the link that was checked
    items: list[VerifiedItem] = Field(min_length=1, max_length=10)
    dry_run: bool = False  # compute the result and diff, save nothing


def check_item(item: VerifiedItem) -> None:
    """400 for values the app could not use."""
    if item.category and item.category not in CATEGORIES:
        raise HTTPException(400, f"category must be one of: {', '.join(CATEGORIES)}")
    if item.opening_hours and hours.parse(item.opening_hours) is None:
        raise HTTPException(400, f"opening_hours is not valid OpenStreetMap syntax: {item.opening_hours}")
    if (item.lat is None) != (item.lon is None):
        raise HTTPException(400, "send lat and lon together")
    if item.kind == "event" and not (item.event_title or item.starts_at or item.recurrence):
        raise HTTPException(400, "an event needs an event_title, a start time or a recurrence")
    for u in (item.website, item.ticket_url, *item.images):
        if u and not u.lower().startswith(("http://", "https://")):
            raise HTTPException(400, f"not a web link: {u}")


def to_hint(item: VerifiedItem) -> ItemHint:
    data = item.model_dump()
    data["tags"] = list(dict.fromkeys(t.strip() for t in item.tags if t.strip()))
    return ItemHint(provider="verified", flags=[], **data)


def snapshot(obj, fields: tuple[str, ...]) -> dict:
    return {f: getattr(obj, f) for f in fields}


def _plain(v):
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    return v


def diff_fields(before: dict | None, after: dict) -> dict:
    """{field: {before, after}} for what changed. For a new item `before` is None and every set field counts."""
    out = {}
    for k, new in after.items():
        old = None if before is None else before.get(k)
        if _plain(old) == _plain(new) or (old in (None, "", []) and new in (None, "", [])):
            continue
        out[k] = {"before": _plain(old), "after": _plain(new)}
    return out


def source_for(db: Session, url: str, now: datetime) -> Source:
    """The saved source for this link, or a new one that is already done (nothing is queued)."""
    url = url.strip()
    src = db.scalars(select(Source).where(Source.url_norm == normalize(url))).first()
    if src is None:
        src = Source(url=url, url_norm=normalize(url), kind=classify(url), status="done", fetched_at=now,
                     raw={"verified": True})
        db.add(src)
        db.flush()
    return src


def save_item(db: Session, src: Source, item: VerifiedItem, index: int, home, earlier: dict) -> dict:
    hint = to_hint(item)
    res = resolver.resolve(db, hint, home)
    if res.best is None:
        return {"name": item.name, "error": "not found on the map"}
    if pipeline.too_vague(res):
        return {"name": item.name, "error": "too vague to pin (only a city)"}
    name = store._place_name(hint, res.best)
    was_place, was_event = pipeline._reuse(db, hint, earlier.get(index), len(earlier) == 1)
    place = was_place or store.find_place(db, res.best, name)
    place_before = snapshot(place, PLACE_FIELDS) if place else None
    if place and not hint.category:
        hint.category = place.category  # a refresh must not turn a known category into "other"
    # Passing the saved place makes the verified values replace the old ones (user edits stay)
    place, place_new = store.upsert_place(db, hint, res, None, existing=place, engine="verified", source_id=src.id)
    if not place_new and item.address and "address_text" not in (place.user_overrides or {}):
        place.address_text = item.address  # the checked address replaces a different saved one
    row = {"name": place.name, "review": place.review_status == "needs_review", "method": res.method,
           "confidence": res.confidence,
           "place": {"id": str(place.id), "new": place_new,
                     "changes": diff_fields(place_before, snapshot(place, PLACE_FIELDS)),
                     "kept_user_edits": sorted(set(place.user_overrides or {}) & set(PLACE_FIELDS))}}
    event = None
    if hint.kind == "event":
        found = was_event or store.find_event(db, hint, place)[0]
        event_before = snapshot(found, EVENT_FIELDS) if found else None
        event, event_new = store.upsert_event(db, hint, place, res, None, existing=found, engine="verified",
                                                   source_id=src.id)
        row["event"] = {"id": str(event.id), "new": event_new,
                        "changes": diff_fields(event_before, snapshot(event, EVENT_FIELDS)),
                        "kept_user_edits": sorted(set(event.user_overrides or {}) & set(EVENT_FIELDS))}
        store.link(db, src, event=event, position=index, confidence=res.confidence)
    store.link(db, src, place=place, position=index, confidence=res.confidence)
    if hint.images or hint.image_url:
        images.page_images(db, src, hint, place=place, event=event, multi=False)
    return row


@router.post("/api/admin/verified-items", dependencies=[Depends(require_key)])
def save_verified(body: VerifiedIn, db: Session = Depends(get_db)):
    """Save checked items as real places/events, merging with what is already saved.
    Returns, per item, the saved ids and which fields were created, filled or replaced."""
    for item in body.items:
        check_item(item)
    src = source_for(db, body.url, datetime.now(timezone.utc))
    earlier = pipeline._earlier(db, src)
    home = store.home_point(db)
    results = []
    try:
        for i, item in enumerate(body.items):
            results.append(save_item(db, src, item, i, home, earlier))
    except Exception:
        db.rollback()
        raise
    saved = any("place" in r for r in results)
    if body.dry_run or not saved:
        db.rollback()
    else:
        db.commit()
    return {"source_id": str(src.id) if saved and not body.dry_run else None, "dry_run": body.dry_run,
            "items": results}
