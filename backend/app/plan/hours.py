"""A small evaluator for OSM opening_hours strings.

Supported: "24/7", weekday ranges and lists (Mo-Fr, Mo,We,Fr, Fr-Mo), rules separated by ";"
(a later rule replaces earlier ones for the days it names), additional rules after ", "
(they add instead of replace), comma separated time ranges, ranges past midnight
(18:00-02:00), "off"/"closed". Holiday rules (PH, SH) are skipped. Anything else
(months, dates, sunrise, week numbers, comments) makes the whole string unknown, so
callers get None instead of a wrong answer.
"""
import re
from datetime import date, datetime, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

DAYS = ("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")
HOLIDAYS = ("PH", "SH")
DAY_TOKEN = r"(?:Mo|Tu|We|Th|Fr|Sa|Su|PH|SH)"
DAY_SELECTOR = re.compile(rf"^{DAY_TOKEN}(?:\s*-\s*{DAY_TOKEN})?(?:\s*,\s*{DAY_TOKEN}(?:\s*-\s*{DAY_TOKEN})?)*")
# ", " followed by a weekday after a time or "off" starts an additional rule
ADDITIONAL = re.compile(rf"(?:(?<=\d)|(?<=off)|(?<=closed))\s*,\s*(?={DAY_TOKEN}\b)")
TIME_RANGE = re.compile(r"^(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})$")
FULL_DAY = [(0, 1440)]
TZ = "America/Los_Angeles"

# Minutes from midnight; an end above 1440 runs into the next day
Ranges = list[tuple[int, int]]
Week = tuple[tuple[tuple[int, int], ...], ...]


class Unsupported(ValueError):
    pass


def _days(selector: str) -> set[int] | None:
    """Weekday numbers named by a selector; None when it only names holidays."""
    out: set[int] = set()
    holiday_only = True
    for part in selector.split(","):
        part = part.strip()
        if part in HOLIDAYS:
            continue
        holiday_only = False
        if "-" in part:
            a, b = (p.strip() for p in part.split("-"))
            if a in HOLIDAYS or b in HOLIDAYS:
                raise Unsupported(part)
            i, j = DAYS.index(a), DAYS.index(b)
            out.update(k % 7 for k in range(i, i + (j - i) % 7 + 1))  # Fr-Mo wraps
        else:
            out.add(DAYS.index(part))
    return None if holiday_only else out


def _times(text: str) -> Ranges:
    text = text.strip()
    if text in ("", "open"):
        return list(FULL_DAY)
    if text in ("off", "closed"):
        return []
    out = []
    for part in text.split(","):
        m = TIME_RANGE.match(part.strip())
        if not m:
            raise Unsupported(part)
        h1, m1, h2, m2 = map(int, m.groups())
        if h1 > 24 or h2 > 48 or m1 > 59 or m2 > 59:
            raise Unsupported(part)
        start, end = h1 * 60 + m1, h2 * 60 + m2
        if end <= start:
            end += 1440
        out.append((start, end))
    return out


@lru_cache(maxsize=2048)
def parse(spec: str | None) -> Week | None:
    """Opening ranges per weekday (Monday first), or None when the string is unknown."""
    if not spec or not spec.strip():
        return None
    week: list[Ranges] = [[] for _ in range(7)]
    try:
        for rule in spec.split(";"):
            rule = rule.strip()
            if not rule:
                continue
            for n, sub in enumerate(ADDITIONAL.split(rule)):
                sub = sub.strip()
                if sub == "24/7":
                    days, ranges = set(range(7)), list(FULL_DAY)
                else:
                    m = DAY_SELECTOR.match(sub)
                    days = _days(m.group(0)) if m else set(range(7))
                    rest = sub[m.end():] if m else sub
                    if days is None:
                        continue  # holiday-only rule
                    ranges = _times(rest)
                for d in days:
                    # The first part of a ";" rule replaces, later ", " parts add
                    week[d] = ranges + (week[d] if n else [])
    except (Unsupported, ValueError):
        return None
    return tuple(tuple(sorted(r)) for r in week)


def _local(at: datetime, tz: str) -> datetime:
    if at.tzinfo is not None:
        at = at.astimezone(ZoneInfo(tz))
    return at.replace(tzinfo=None)


def intervals(spec: str | None, day: date) -> list[tuple[datetime, datetime]] | None:
    """Naive local open intervals that touch this day, including spill-over from the day before."""
    week = parse(spec)
    if week is None:
        return None
    out = []
    for d in (day - timedelta(days=1), day):
        midnight = datetime(d.year, d.month, d.day)
        for s, e in week[d.weekday()]:
            a, b = midnight + timedelta(minutes=s), midnight + timedelta(minutes=e)
            if b > datetime(day.year, day.month, day.day):
                out.append((a, b))
    return _merge(out)


def _merge(spans: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    out: list[tuple[datetime, datetime]] = []
    for a, b in sorted(spans):
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def is_open(spec: str | None, at: datetime, tz: str = TZ) -> bool | None:
    """True/False for open at this moment, None when the hours are unknown."""
    t = _local(at, tz)
    spans = intervals(spec, t.date())
    if spans is None:
        return None
    return any(a <= t < b for a, b in spans)


def is_open_between(spec: str | None, start: datetime, end: datetime, tz: str = TZ) -> bool | None:
    """True when open for the whole of [start, end], None when the hours are unknown."""
    a, b = _local(start, tz), _local(end, tz)
    if b <= a:
        return is_open(spec, start, tz)
    spans: list[tuple[datetime, datetime]] = []
    d = a.date()
    while d <= b.date():
        day = intervals(spec, d)
        if day is None:
            return None
        spans.extend(day)
        d += timedelta(days=1)
    return any(s <= a and b <= e for s, e in _merge(spans))
