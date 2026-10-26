"""Recurrence wording ("every Tuesday at 6pm", "third Friday of every month") -> RFC 5545 RRULE, and the
concrete dates it produces. Only patterns that mean one thing are read; anything vaguer returns None."""
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from dateutil.rrule import rrulestr

DAYS = {"monday": "MO", "tuesday": "TU", "wednesday": "WE", "thursday": "TH", "friday": "FR",
        "saturday": "SA", "sunday": "SU", "mon": "MO", "tue": "TU", "tues": "TU", "wed": "WE", "thu": "TH",
        "thur": "TH", "thurs": "TH", "fri": "FR", "sat": "SA", "sun": "SU"}
ORDINALS = {"first": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3, "fourth": 4, "4th": 4,
            "last": -1}
DAY_RE = "|".join(sorted(DAYS, key=len, reverse=True))
ORD_RE = "|".join(ORDINALS)
TIME_RE = re.compile(r"\b(?:at\s+|from\s+|@\s*)?(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)", re.I)
HORIZON_DAYS = 120


@dataclass
class Recurrence:
    rrule: str
    start_time: time | None  # None when the wording gives no time


def _time(text: str) -> time | None:
    m = TIME_RE.search(text)
    if not m:
        return None
    hour, minute, ap = int(m.group(1)), int(m.group(2) or 0), m.group(3).lower()[0]
    if not (1 <= hour <= 12 and minute < 60):
        return None
    return time(hour % 12 + (12 if ap == "p" else 0), minute)


def parse(text: str | None) -> Recurrence | None:
    if not text:
        return None
    t = " ".join(text.lower().replace(",", " ").split())
    if t.startswith("ongoing until"):
        return None
    when = _time(t)
    # third Friday of every month / first Friday of the month / every 2nd Tuesday
    m = re.search(rf"\b(?:every\s+)?({ORD_RE})\s+({DAY_RE})\b(?:\s+of\s+(?:every|each|the)\s+month|\s+monthly|\s+of\s+the\s+month)?", t)
    if m and ("month" in t or t.startswith("every")):
        return Recurrence(f"FREQ=MONTHLY;BYDAY={ORDINALS[m.group(1)]}{DAYS[m.group(2)]}", when)
    # every other Saturday / every second week on Saturday / biweekly Saturdays
    m = re.search(rf"\bevery\s+other\s+({DAY_RE})s?\b", t) or re.search(rf"\bbi-?weekly\b.*?\b({DAY_RE})s?\b", t)
    if m:
        return Recurrence(f"FREQ=WEEKLY;INTERVAL=2;BYDAY={DAYS[m.group(1)]}", when)
    if re.search(r"\bevery\s+weekday\b|\bweekdays\b|\bmonday\s+(?:through|to|-)\s+friday\b", t):
        return Recurrence("FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR", when)
    if re.search(r"\bevery\s*day\b|\bdaily\b", t):
        return Recurrence("FREQ=DAILY", when)
    # every Tuesday / Tuesdays / every Tuesday and Thursday / weekly on Tuesdays
    days = []
    if re.search(r"\bevery\b|\bweekly\b|\beach\b", t) or re.search(rf"\b(?:{DAY_RE})s\b", t):
        for d in re.finditer(rf"\b({DAY_RE})s?\b", t):
            if DAYS[d.group(1)] not in days:
                days.append(DAYS[d.group(1)])
    if days:
        return Recurrence("FREQ=WEEKLY;BYDAY=" + ",".join(days), when)
    return None


def valid(rule: str) -> bool:
    try:
        rrulestr(rule, dtstart=datetime(2026, 1, 1))
    except (ValueError, TypeError):
        return False
    return True


def first_start(rule: str, when: time | None, tz: str, after: datetime) -> datetime | None:
    """The first date of the rule on or after `after`, at `when` (or midnight), in the event's zone."""
    zone = ZoneInfo(tz)
    local = after.astimezone(zone)
    anchor = datetime.combine(local.date(), when or time(0), zone)
    rule_obj = rrulestr(rule, dtstart=anchor.replace(tzinfo=None))
    nxt = rule_obj.after(datetime.combine(local.date(), time(0)) - timedelta(seconds=1), inc=True)
    return nxt.replace(tzinfo=zone) if nxt else None


def expand(rule: str, anchor: datetime, tz: str, *, now: datetime, days: int = HORIZON_DAYS) -> list[datetime]:
    """Dates of the rule from today to `days` ahead, at the anchor's local time of day (DST-correct)."""
    zone = ZoneInfo(tz)
    local = anchor.astimezone(zone)
    rule_obj = rrulestr(rule, dtstart=local.replace(tzinfo=None))
    start = max(now.astimezone(zone).date(), local.date())
    lo = datetime.combine(start, time(0))
    hi = datetime.combine(now.astimezone(zone).date() + timedelta(days=days), time(23, 59, 59))
    return [d.replace(tzinfo=zone) for d in rule_obj.between(lo, hi, inc=True)]
