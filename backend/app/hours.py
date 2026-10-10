"""OSM opening_hours, the common subset.

Handles 24/7, weekday ranges and lists (Mo-Fr, Sa,Su, Tu-We,Fr), several rules
separated by ";" (a later rule replaces earlier ones for its days) or by "," after a
time (adds to them), comma separated time ranges, ranges past midnight (18:00-02:00),
off/closed, and ignores public/school holiday rules (PH, SH). Anything else
(months, dates, sunrise, week numbers) makes the result unknown (None).
"""
import re
from datetime import datetime, timedelta

DAYS = ("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")
DAY = r"(?:Mo|Tu|We|Th|Fr|Sa|Su|PH|SH)"
SELECTOR = re.compile(rf"^({DAY}(?:\s*-\s*{DAY})?(?:\s*,\s*{DAY}(?:\s*-\s*{DAY})?)*)\s*:?\s*(.*)$")
TIME_RANGE = re.compile(r"^(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})$")
# "," followed by a weekday after a time or off/closed/open starts an additional rule
ADDITIONAL = re.compile(rf"(?<=[\dfdn])\s*,\s*(?={DAY}\b)")
COMMENT = re.compile(r'"[^"]*"')

Interval = tuple[int, int]  # minutes from the day's midnight; the end may pass 1440


class Unsupported(ValueError):
    pass


def _days(selector: str) -> list[int] | None:
    """Weekday indexes for a selector; None when it only names holidays."""
    out: list[int] = []
    holiday_only = True
    for part in selector.replace(" ", "").split(","):
        a, _, b = part.partition("-")
        if a in ("PH", "SH") or b in ("PH", "SH"):
            continue
        holiday_only = False
        i, j = DAYS.index(a), DAYS.index(b or a)
        while True:
            if i not in out:
                out.append(i)
            if i == j:
                break
            i = (i + 1) % 7
    return None if holiday_only else out


def _times(text: str) -> list[Interval]:
    text = re.sub(r"\s*-\s*", "-", text.strip())
    if text in ("off", "closed"):
        return []
    if text in ("", "open"):
        return [(0, 1440)]
    out: list[Interval] = []
    for part in re.split(r"\s*,\s*", text):
        m = TIME_RANGE.match(part)
        if not m:
            raise Unsupported(part)
        h1, m1, h2, m2 = map(int, m.groups())
        if h1 > 24 or h2 > 48 or m1 > 59 or m2 > 59:
            raise Unsupported(part)
        start, end = h1 * 60 + m1, h2 * 60 + m2
        if end <= start:
            end += 1440  # past midnight
        out.append((start, end))
    return out


def parse(spec: str | None) -> dict[int, list[Interval]] | None:
    """Weekday -> open intervals, or None when the spec cannot be read."""
    spec = COMMENT.sub("", spec or "").strip()
    if not spec:
        return None
    if spec == "24/7":
        return {d: [(0, 1440)] for d in range(7)}
    week: dict[int, list[Interval]] = {}
    used = False
    try:
        for rule in re.split(r"\s*(?:;|\|\|)\s*", spec):
            for k, part in enumerate(ADDITIONAL.split(rule.strip())):
                if not part:
                    continue
                m = SELECTOR.match(part)
                if m:
                    days, rest = _days(m.group(1)), m.group(2)
                    if days is None:
                        continue  # holiday rule
                else:
                    days, rest = list(range(7)), part
                if re.search(r"[A-Za-z]", re.sub(r"\b(off|closed|open)\b", "", rest)):
                    raise Unsupported(part)
                times = _times(rest)
                for d in days:
                    week[d] = [*week.get(d, []), *times] if k else list(times)
                used = True
    except (Unsupported, ValueError):
        return None
    return week if used else None


def is_open(spec: str | None, at: datetime) -> bool | None:
    """Open at this local time? None when the hours are missing or not understood."""
    week = parse(spec)
    if week is None:
        return None
    day, minute = at.weekday(), at.hour * 60 + at.minute
    if any(s <= minute < e for s, e in week.get(day, [])):
        return True
    yesterday = (at - timedelta(days=1)).weekday()
    return any(e > 1440 and minute < e - 1440 for _, e in week.get(yesterday, []))
