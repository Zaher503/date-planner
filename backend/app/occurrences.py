"""Keep an event's concrete dates (the occurrences table) in step with its repeat rule."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app import recurrence
from app.db.models import Event, Occurrence

DEFAULT_MINUTES = 120


def length(event: Event) -> timedelta:
    if event.duration_min:
        return timedelta(minutes=event.duration_min)
    if event.starts_at and event.ends_at:
        return event.ends_at - event.starts_at
    return timedelta(minutes=DEFAULT_MINUTES)


def apply_rule(event: Event, now: datetime | None = None) -> bool:
    """Set the rule from the event's wording (and a first date when it has none). True when a rule was set."""
    now = now or datetime.now(timezone.utc)
    parsed = recurrence.parse(event.recurrence_text)
    if parsed is None:
        return False
    event.rrule = parsed.rrule
    if event.starts_at is None:
        event.starts_at = recurrence.first_start(parsed.rrule, parsed.start_time, event.tz, now)
        event.all_day = parsed.start_time is None
        event.duration_min = event.duration_min or (None if event.all_day else DEFAULT_MINUTES)
        event.duration_estimated = not event.all_day
    return True


def refresh(db: Session, event: Event, now: datetime | None = None) -> int:
    """Rebuild the future occurrences of a repeating event for the next 120 days. Past ones stay."""
    if not event.rrule or event.starts_at is None or not event.listed or event.status != "scheduled":
        return 0
    now = now or datetime.now(timezone.utc)
    span = length(event)
    wanted = recurrence.expand(event.rrule, event.starts_at, event.tz, now=now)
    keep = {d.astimezone(timezone.utc) for d in wanted}
    stale = [o for o in db.scalars(select(Occurrence).where(Occurrence.event_id == event.id,
                                                            Occurrence.starts_at >= now)).all()
             if o.starts_at.astimezone(timezone.utc) not in keep]
    if stale:
        db.execute(delete(Occurrence).where(Occurrence.id.in_([o.id for o in stale])))
    for d in wanted:
        db.execute(insert(Occurrence).values(event_id=event.id, starts_at=d, ends_at=d + span)
                   .on_conflict_do_update(constraint="uq_occurrence", set_={"ends_at": d + span}))
    return len(wanted)


def refresh_all(db: Session, now: datetime | None = None) -> dict:
    events = db.scalars(select(Event).where(Event.rrule.is_not(None), Event.listed.is_(True),
                                            Event.status == "scheduled")).all()
    total = sum(refresh(db, e, now) for e in events)
    db.commit()
    return {"events": len(events), "occurrences": total}
