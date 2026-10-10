"""No invented numbers: every price, time and date the model returns must be backed by the text.

Same rule as Recipe Box. Anything unsupported is dropped and the item is flagged.
"""
import re
from datetime import date

NUM = re.compile(r"\d+(?:[.,]\d+)?")
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september",
          "october", "november", "december"]
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
RELATIVE = re.compile(r"\b(today|tonight|tomorrow|this weekend|this week|next week)\b", re.I)


def numbers_in(text: str) -> set[float]:
    out = set()
    for n in NUM.findall(text or ""):
        try:
            out.add(float(n.replace(",", "")))
        except ValueError:
            pass
    return out


def price_supported(value: float | None, nums: set[float]) -> bool:
    return value is None or value == 0 or float(value) in nums


def time_supported(hhmm: str | None, text: str) -> bool:
    """'20:00' is backed by '8pm', '8 PM', '20:00' or '8:00'."""
    if not hhmm:
        return True
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", hhmm.strip())
    if not m:
        return False
    h, mi = int(m.group(1)), int(m.group(2))
    h12 = h % 12 or 12
    low = (text or "").lower()
    if mi == 0 and ((h == 12 and "noon" in low) or (h == 0 and "midnight" in low)):
        return True
    for hr in {h, h12}:
        # 8:00 / 08:00 / 8:30 / 8.30
        if re.search(rf"(?<![\d:]){hr:d}[:.]{mi:02d}(?!\d)", low) or re.search(rf"(?<![\d:]){hr:02d}:{mi:02d}(?!\d)", low):
            return True
    # 8pm / 8 p.m. / 8 o'clock (whole hours only)
    return mi == 0 and bool(re.search(rf"(?<![\d:]){h12}\s*(am|pm|a\.m\.|p\.m\.|o'?clock)", low))


def date_supported(d: date | None, text: str) -> bool:
    """Backed by the day number with its month, the weekday, or a relative word."""
    if d is None:
        return True
    low = (text or "").lower()
    month = MONTHS[d.month - 1]
    day = d.day
    if re.search(rf"\b({month}|{month[:3]})\.?\s+{day}(st|nd|rd|th)?\b", low):
        return True
    if re.search(rf"\b{day}(st|nd|rd|th)?\s+(of\s+)?({month}|{month[:3]})\b", low):
        return True
    if re.search(rf"\b0?{d.month}[/.-]0?{day}\b", low) or d.isoformat() in low:
        return True
    if WEEKDAYS[d.weekday()] in low or re.search(rf"\b{WEEKDAYS[d.weekday()][:3]}\b", low):
        return True
    return bool(RELATIVE.search(low))


def address_supported(address: str, text: str) -> bool:
    """The house number (and street name) of an address must be in the text."""
    m = re.match(r"\s*(\d+[A-Za-z]?)\s+(.*)", address or "")
    if not m:
        return True  # no house number, nothing to invent
    number, rest = m.group(1), m.group(2)
    low = (text or "").lower()
    if not re.search(rf"(?<!\d){re.escape(number.lower())}(?!\d)", low):
        return False
    words = [w for w in re.findall(r"[a-z]{3,}", rest.lower())
             if w not in {"street", "avenue", "blvd", "boulevard", "road", "drive", "north", "south", "east", "west",
                          "los", "angeles", "california", "suite", "place", "lane"}]
    return not words or any(w in low for w in words[:2])
