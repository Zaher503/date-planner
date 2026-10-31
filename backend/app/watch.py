"""Standing venues: re-read a venue's website on a schedule and keep its events up to date.

The place itself never changes here. A scan adds new events, updates the ones it still lists, and marks
events it no longer lists as unlisted (never deletes them; a bad scan must not wipe the venue's events).
"""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import jobs
from app.db.models import Event, ItemSource, Job, Place, Source
from app.ingest.urls import classify, normalize

SLACK = timedelta(hours=2)  # a daily check may run a little early without skipping a week


def attach(db: Session, place: Place, url: str, user_id: int | None = None) -> Source:
    """Point the place at the page to re-read; reuses the saved link when the page was imported before."""
    norm = normalize(url)
    src = db.scalars(select(Source).where(Source.url_norm == norm)).first()
    if src is None:
        src = Source(url=url, url_norm=norm, kind=classify(url), status="pending", submitted_by=user_id)
        db.add(src)
        db.flush()
    place.watch_url, place.watch_source_id = url, src.id
    return src


def is_due(place: Place, now: datetime) -> bool:
    if not place.standing or place.watch_source_id is None:
        return False
    if place.last_scanned_at is None:
        return True
    return now - place.last_scanned_at >= timedelta(days=place.watch_every_days) - SLACK


def next_scan(place: Place) -> datetime | None:
    if not place.standing or place.watch_source_id is None:
        return None
    if place.last_scanned_at is None:
        return datetime.now(timezone.utc)
    return place.last_scanned_at + timedelta(days=place.watch_every_days)


def enqueue_scan(db: Session, place: Place, user_id: int | None = None) -> int | None:
    """Queue a read of the venue's page. None when one is already waiting or running."""
    src = db.get(Source, place.watch_source_id) if place.watch_source_id else None
    if src is None:
        return None
    busy = db.scalars(select(Job.id).where(Job.source_id == src.id, Job.type == "ingest",
                                           Job.status.in_(("queued", "running")))).first()
    if busy:
        return None
    src.status, src.error = "pending", None
    job = jobs.enqueue(db, "ingest", {"source_id": str(src.id), "watch": True}, source_id=src.id,
                       needs_gpu=not place.watch_parser, submitted_by=user_id)
    return job.id


def scan_due(db: Session, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    places = db.scalars(select(Place).where(Place.standing.is_(True), Place.watch_source_id.is_not(None))).all()
    queued = [p.name for p in places if is_due(p, now) and enqueue_scan(db, p) is not None]
    db.commit()
    return {"standing": len(places), "queued": queued}


def _watchers(db: Session, src: Source) -> list[Place]:
    return list(db.scalars(select(Place).where(Place.watch_source_id == src.id, Place.standing.is_(True))).all())


def after_run(db: Session, src: Source, result: dict | None, error: str | None = None,
              now: datetime | None = None) -> None:
    """Record what a read of a watched page found, and unlist events it no longer shows."""
    places = _watchers(db, src)
    if not places:
        return
    now = now or datetime.now(timezone.utc)
    rows = (result or {}).get("items") or []
    seen = {uuid.UUID(r["id"]) for r in rows if r.get("type") == "event" and r.get("id")}
    err = error or (result or {}).get("error")
    for place in places:
        place.last_scanned_at = now
        if err:
            place.last_scan_status, place.last_scan_note = "failed", str(err)[:300]
        elif not seen:
            place.last_scan_status = "no_events"
            place.last_scan_note = "The page was read but no events were found; the saved events were kept."
        else:
            new, gone = reconcile(db, place, src, seen, now)
            place.last_scan_status = "ok"
            place.last_scan_note = f"{len(seen)} events listed" + (f", {gone} no longer listed" if gone else "")
    db.commit()


def reconcile(db: Session, place: Place, src: Source, seen: set[uuid.UUID], now: datetime) -> tuple[int, int]:
    """Events this page produced before: listed again if seen, unlisted if not. A status set by hand wins."""
    linked = db.scalars(select(Event).join(ItemSource, ItemSource.event_id == Event.id)
                        .where(ItemSource.source_id == src.id, Event.place_id == place.id)).all()
    relisted = unlisted = 0
    for ev in linked:
        by_hand = "status" in (ev.user_overrides or {})
        if ev.id in seen:
            ev.last_seen_at = now
            if not ev.listed:
                ev.listed = True
                if ev.status == "archived" and not by_hand:
                    ev.status = "scheduled"
                relisted += 1
        elif ev.listed:
            ev.listed = False
            if ev.status == "scheduled" and not by_hand:
                ev.status = "archived"
            unlisted += 1
    for ev in db.scalars(select(Event).where(Event.id.in_(seen), Event.place_id == place.id)):
        ev.last_seen_at = now
    return relisted, unlisted
