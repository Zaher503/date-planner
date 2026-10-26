"""What an item must have to be usable, what is worth a look, and what is only nice to have.

needed:   without it the item cannot be placed or found; this marks the item for review.
check:    present but doubtful; shown in the item's details, never forces a review.
optional: many items legitimately lack it (phone, price, photos); listed as information only.
"""
import re

# Reasons recorded at import that mean the date or the venue cannot be trusted
EVENT_REVIEW_FLAGS = {"removed unverified date", "event with no date", "event already happened"}
PLACE_REVIEW_FLAGS = {"not a specific venue"}
# Recorded for information only: an ongoing series is a valid shape, a missing time zone assumes Los Angeles
INFO_FLAGS = {"recurring series, dates unclear", "start time has no time zone"}

HOUSE_NUMBER = re.compile(r"^\s*\d")


def _blank(v) -> bool:
    return v is None or (isinstance(v, str) and not v.strip()) or v == [] or v == {}


def event_gaps(e) -> dict[str, list[str]]:
    needed, check, optional = [], [], []
    if _blank(e.title):
        needed.append("a title")
    if not (e.starts_at or e.rrule or not _blank(e.recurrence_text)):
        needed.append("a date, or how often it repeats")
    if e.place_id is None and _blank(e.address_text):
        needed.append("a venue")
    if _blank(e.ticket_url):
        optional.append("a ticket link")
    if e.is_free is None and e.price_min is None and _blank(e.price_text):
        optional.append("a price")
    if _blank(e.description):
        optional.append("a description")
    return {"needed": needed, "check": check, "optional": optional}


def place_gaps(p) -> dict[str, list[str]]:
    needed, check, optional = [], [], []
    if _blank(p.name):
        needed.append("a name")
    if _blank(p.address_text):
        needed.append("an address")
    elif not HOUSE_NUMBER.match(p.address_text):
        check.append("a street number (only a street or area is known)")
    for label, value in (("a website", p.website), ("a phone number", p.phone),
                         ("opening hours", p.opening_hours or p.hours_text), ("a description", p.description)):
        if _blank(value):
            optional.append(label)
    return {"needed": needed, "check": check, "optional": optional}


def gaps(item) -> dict[str, list[str]]:
    return place_gaps(item) if hasattr(item, "website") else event_gaps(item)


def needs_review(item, flags: list[str]) -> bool:
    """Review only for what blocks use of the item itself. An uncertain venue pin is reviewed on the venue."""
    blocking = EVENT_REVIEW_FLAGS if not hasattr(item, "website") else PLACE_REVIEW_FLAGS
    return bool(blocking & set(flags)) or bool(gaps(item)["needed"])
