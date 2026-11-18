"""When an event counts as over. The SQL twin lives in app.api.filters (archived())."""
import re
from datetime import datetime, timedelta

DEFAULT_EVENT_HOURS = 3
UNTIL_RE = re.compile(r"UNTIL=(\d{8})")


def event_ended(*, status: str | None, starts_at: datetime | None, ends_at: datetime | None,
                duration_min: int | None, all_day: bool | None, is_recurring: bool, now: datetime,
                rrule: str | None = None) -> bool:
    """Python twin of archived(), for rows already in memory. Keep the two in step."""
    if status == "archived":
        return True
    m = UNTIL_RE.search(rrule or "")
    if m and m.group(1) < now.strftime("%Y%m%d"):
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


def event_ongoing(*, start: datetime | None, end: datetime | None, now: datetime) -> bool:
    """A run that is on now and lasts longer than a day: an exhibition or a season that opened before now (or
    has only a closing date) and closes later. Lists show it as "On now, until <end>" instead of its opening
    date."""
    if end is None:
        return False
    if end.tzinfo is None:
        end = end.replace(tzinfo=now.tzinfo)
    if start is None:
        return end > now
    if start.tzinfo is None:
        start = start.replace(tzinfo=now.tzinfo)
    return start <= now < end and end - start > timedelta(days=1)
