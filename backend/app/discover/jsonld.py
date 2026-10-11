"""schema.org Event JSON-LD -> RawEvent, reusing the ingest page parser."""
from datetime import datetime
from zoneinfo import ZoneInfo

from app.discover.base import RawEvent
from app.ingest.event_page import _types, event_item, jsonld_nodes


def event_nodes(html: str) -> list[dict]:
    """Event nodes from a page, including those wrapped in an ItemList."""
    out: list[dict] = []
    for n in jsonld_nodes(html):
        if "itemlist" in _types(n):
            for el in n.get("itemListElement") or []:
                item = el.get("item") if isinstance(el, dict) else None
                if isinstance(item, dict) and any(t.endswith("event") for t in _types(item)):
                    out.append(item)
        elif any(t.endswith("event") for t in _types(n)):
            out.append(n)
    return out


def _localize(dt: datetime | None, tz: str) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=ZoneInfo(tz))
    return dt


def raw_from_jsonld(node: dict, adapter: str, external_id: str, page_url: str, tz: str) -> RawEvent | None:
    """None for online-only events or nodes without a title or start."""
    item = event_item(node, page_url)
    if item is None or not (item.event_title or item.name) or item.starts_at is None:
        return None
    # A date-only startDate means the time is unknown
    all_day = isinstance(node.get("startDate"), str) and len(node["startDate"].strip()) <= 10
    return RawEvent(
        adapter=adapter,
        external_id=external_id,
        title=item.event_title or item.name,
        url=item.ticket_url or page_url,
        starts_at=_localize(item.starts_at, tz),
        ends_at=None if all_day else _localize(item.ends_at, tz),
        all_day=all_day,
        tz=tz,
        status=item.status,
        venue_name=item.name or None,
        address_text=item.address,
        lat=item.lat,
        lon=item.lon,
        price_min=item.price_min,
        price_max=item.price_max,
        currency=item.currency,
        is_free=item.is_free,
        description=item.description,
        image_url=item.image_url,
        raw={"source": "jsonld"},
    )
