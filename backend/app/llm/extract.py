"""Text (caption, on-screen text, transcript, page text) -> places and events, via the local model."""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.ingest.items import CATEGORIES, ItemHint
from app.llm import verify
from app.textclean import clean_name
from app.llm.ollama import chat_json

MAX_ITEMS = 15

SYSTEM = """You read social media posts and web pages and pull out date ideas: specific places and events in or near {region} that two people could go to.

Rules:
- Only return places or events the text actually names. Never invent a business name, address, price, date or time.
- A list post ("10 date ideas in LA", "5 rooftop bars") has one item per entry, in order.
- name: the business, venue or landmark exactly as written (fix obvious speech-to-text spelling only). For an event, name is the venue and event_title is the event.
- If an entry is an activity with no named venue (for example "bike by the beach"), set specific to false and put the area it mentions (for example "Venice") in area.
- address: only if the text gives a street address. area: neighborhood or city if mentioned.
- A venue page or listing that shows several events or classes at one venue gets one item per event: kind "event", name is the venue, event_title is that event, each with its own dates, times and price. Never put an event's title in name.
- inside: if the place is inside another named venue (a bar inside a hotel, a stall inside a market), the host venue's name, else null.
- A location tag or hashtag that is only a neighborhood or city is not an item.
- Dates as YYYY-MM-DD, times as 24h HH:MM. Today is {today}. The post was published {posted}. Resolve "this Friday" from the publish date. Leave dates empty unless the text states them.
- recurrence: wording like "every Sunday" or "first Friday of the month", else null.
- price_min/price_max only from numbers in the text; is_free true only if it says free.
- description: one short sentence on what it is and why it is a good date, from the text.
- tags: 2 to 6 lowercase words (cuisine, vibe, activity, setting). No hashtags, no city names.
- Skip the creator's own account, sponsors, apps, products and anything outside {region} unless the post is clearly about a trip there."""

SCHEMA = {
    "type": "object",
    "properties": {
        "is_list": {"type": "boolean"},
        "items": {
            "type": "array",
            "maxItems": MAX_ITEMS,
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["place", "event"]},
                    "name": {"type": "string"},
                    "event_title": {"type": ["string", "null"]},
                    "specific": {"type": "boolean"},
                    "address": {"type": ["string", "null"]},
                    "area": {"type": ["string", "null"]},
                    "inside": {"type": ["string", "null"]},
                    "category": {"type": "string", "enum": list(CATEGORIES)},
                    "description": {"type": ["string", "null"]},
                    "start_date": {"type": ["string", "null"]},
                    "start_time": {"type": ["string", "null"]},
                    "end_date": {"type": ["string", "null"]},
                    "end_time": {"type": ["string", "null"]},
                    "recurrence": {"type": ["string", "null"]},
                    "price_text": {"type": ["string", "null"]},
                    "price_min": {"type": ["number", "null"]},
                    "price_max": {"type": ["number", "null"]},
                    "is_free": {"type": ["boolean", "null"]},
                    "tags": {"type": "array", "items": {"type": "string"}, "maxItems": 6},
                },
                "required": ["kind", "name", "event_title", "specific", "address", "area", "inside", "category",
                             "description", "start_date", "start_time", "end_date", "end_time",
                             "recurrence", "price_text", "price_min", "price_max", "is_free", "tags"],
            },
        },
    },
    "required": ["is_list", "items"],
}


def _date(s: str | None) -> date | None:
    try:
        return date.fromisoformat(s.strip()) if s else None
    except ValueError:
        return None


def _tags(raw: list[str]) -> list[str]:
    out = []
    for t in raw or []:
        t = t.strip().lstrip("#").lower()[:24]
        if t and t not in out and t not in ("la", "los angeles", "losangeles", "date", "datenight", "fyp"):
            out.append(t)
    return out[:6]


NULLISH = {"", "null", "none", "n/a", "na", "unknown", "tbd", "tba"}


def _s(v) -> str | None:
    v = (v or "").strip() if isinstance(v, str) else None
    return None if v is None or v.lower() in NULLISH else v


def name_ok(inside: str, name: str) -> bool:
    """A host venue different from the place itself."""
    return inside.strip().lower() != (name or "").strip().lower()


def to_hint(raw: dict, text: str, tz: str) -> ItemHint | None:
    name = clean_name(_s(raw.get("name")))
    area = _s(raw.get("area"))
    if not name and not area:
        return None
    for key in ("event_title", "address", "inside", "description", "recurrence", "price_text"):
        raw[key] = _s(raw.get(key))
    hint = ItemHint(
        kind=raw.get("kind") or "place",
        name=name or area,
        event_title=clean_name(raw.get("event_title")) or None,
        address=(raw.get("address") or "").strip() or None,
        area=area,
        inside=raw.get("inside") if raw.get("inside") and name_ok(raw.get("inside"), name) else None,
        category=raw.get("category"),
        description=(raw.get("description") or "").strip() or None,
        recurrence=(raw.get("recurrence") or "").strip() or None,
        price_text=(raw.get("price_text") or "").strip() or None,
        is_free=raw.get("is_free"),
        tags=_tags(raw.get("tags")),
        tz=tz,
        provider="llm",
    )
    # The model's own "specific" flag is unreliable; judge it from the name
    if not name or (area and name.lower() == area.lower()):
        hint.flags.append("not a specific venue")

    # Numbers must come from the text: the model sometimes "remembers" an address
    nums = verify.numbers_in(text)
    if hint.address and not verify.address_supported(hint.address, text):
        hint.flags.append("removed unverified address")
        hint.address = None
    for key in ("price_min", "price_max"):
        v = raw.get(key)
        if v is not None and not verify.price_supported(v, nums):
            hint.flags.append(f"removed unverified {key.replace('_', ' ')}")
            v = None
        setattr(hint, key, float(v) if v is not None else None)
    # Free only when the text says so; "not free" only when it states a price
    if hint.is_free and "free" not in text.lower():
        hint.is_free = None
    if hint.is_free is False and hint.price_min is None and hint.price_max is None and "$" not in text:
        hint.is_free = None

    start_d, end_d = _date(raw.get("start_date")), _date(raw.get("end_date"))
    start_t, end_t = raw.get("start_time"), raw.get("end_time")
    if start_d and not verify.date_supported(start_d, text):
        hint.flags.append("removed unverified date")
        start_d = end_d = None
    if start_t and not verify.time_supported(start_t, text):
        hint.flags.append("removed unverified time")
        start_t = None
    if end_t and not verify.time_supported(end_t, text):
        end_t = None

    zone = ZoneInfo(tz)
    if start_d:
        if start_t:
            hint.starts_at = datetime.combine(start_d, time.fromisoformat(start_t), zone)
        else:
            hint.starts_at, hint.all_day = datetime.combine(start_d, time(0), zone), True
        if end_t or end_d:
            ed = end_d or start_d
            et = time.fromisoformat(end_t) if end_t else time(23, 59)
            end = datetime.combine(ed, et, zone)
            if end <= hint.starts_at and not end_d:
                end += timedelta(days=1)  # "8pm to 1am"
            if end > hint.starts_at:
                hint.ends_at = end
    if hint.kind == "event" and not hint.starts_at and not hint.recurrence:
        hint.flags.append("event with no date")
    return hint


CLASSIFY_SYSTEM = """For each numbered place or event, choose its category and 2 to 6 lowercase tags
(cuisine, vibe, activity, setting). No hashtags, no city names. Use only what the text supports."""

CLASSIFY_SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {"type": "object", "properties": {
        "index": {"type": "integer"},
        "category": {"type": "string", "enum": list(CATEGORIES)},
        "tags": {"type": "array", "items": {"type": "string"}, "maxItems": 6},
    }, "required": ["index", "category", "tags"]}}},
    "required": ["items"],
}


def classify(hints: list[ItemHint], context: str = "") -> None:
    """Fill category and tags on structured items (JSON-LD has neither), in one call."""
    todo = [(i, h) for i, h in enumerate(hints) if not h.category or not h.tags]
    if not todo:
        return
    lines = [f"{i}. {h.event_title or ''} at {h.name}: {(h.description or '')[:300]}" for i, h in todo]
    out = chat_json(CLASSIFY_SYSTEM, (context[:1500] + "\n\n" if context else "") + "\n".join(lines), CLASSIFY_SCHEMA)
    for row in out.get("items", []):
        i = row.get("index")
        if isinstance(i, int) and 0 <= i < len(hints):
            hints[i].category = hints[i].category or row.get("category")
            hints[i].tags = hints[i].tags or _tags(row.get("tags"))


def extract(text: str, *, posted: date | None = None, today: date | None = None,
            region: str = "Los Angeles / Southern California", tz: str = "America/Los_Angeles") -> tuple[bool, list[ItemHint]]:
    today = today or date.today()
    posted_s = posted.strftime("%Y-%m-%d (%A)") if posted else "unknown"
    system = SYSTEM.format(region=region, today=today.strftime("%Y-%m-%d (%A)"), posted=posted_s)
    out = chat_json(system, text[:12000], SCHEMA)
    hints = [h for h in (to_hint(r, text, tz) for r in out.get("items", [])[:MAX_ITEMS]) if h]
    return bool(out.get("is_list")), hints
