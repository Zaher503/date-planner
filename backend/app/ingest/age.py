"""Minimum age of an event (18 or 21), read from the words on its page or post.

Only clear statements count: "21+", "ages 18 and up", "must be 21 or older". When the text gives both ages
(18+ to enter but 21+ to drink) or says it is for all ages, the answer is None and the app shows nothing."""
import re

from app.ingest.items import ItemHint

AGES = ("18", "21")
_NUM = r"(?<![\d$.,:/-])(18|21)(?![\d,]|\.\d)"
PATTERNS = [
    re.compile(_NUM + r"\s*\+(?!\d)"),
    re.compile(r"(?<![\d$])\+\s*(18|21)(?!\d)"),
    re.compile(_NUM + r"\s*(?:years?\s*(?:old\s*)?|yrs?\.?\s*(?:old\s*)?)?(?:and|or|&)\s*(?:over|up|older|above)\b", re.I),
    re.compile(_NUM + r"\s*(?:plus|and\s*(?:up|over)|only)\b", re.I),
    re.compile(r"\bages?\s*:?\s*(18|21)(?![\d,])", re.I),
    re.compile(r"\b(?:must\s+be|only|guests?\s+must\s+be|you\s+must\s+be)\s+(?:at\s+least\s+)?(18|21)\b", re.I),
]
ALL_AGES = re.compile(r"\ball[\s-]ages\b|\bfamily[\s-]friendly\b|\bkids\s+(?:welcome|free)\b", re.I)


def min_age(text: str | None) -> int | None:
    """18 or 21 when the text names exactly one of them, else None."""
    if not text:
        return None
    found = {m.group(1) for p in PATTERNS for m in p.finditer(text)}
    if len(found) != 1 or ALL_AGES.search(text):
        return None
    return int(next(iter(found)))


def apply(hints: list[ItemHint], *texts: str | None) -> None:
    """Set min_age on the one event a page or post is about. Several events share the text, so none is set."""
    events = [h for h in hints if h.kind == "event"]
    if len(events) != 1 or events[0].min_age is not None:
        return
    events[0].min_age = min_age("\n".join(t for t in texts if t))
