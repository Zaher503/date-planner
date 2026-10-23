"""Web pages (event listings, venue sites): schema.org JSON-LD first, page text as fallback."""
import html as htmllib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlsplit

from app.ingest.age import min_age
from app.ingest.items import ItemHint

LD_BLOCK = re.compile(r"<script[^>]+application/ld\+json[^>]*>(.*?)</script>", re.S | re.I)
PLACE_TYPES = {
    "place", "localbusiness", "restaurant", "barorpub", "foodestablishment", "nightclub",
    "cafeorcoffeeshop", "bakery", "icecreamshop", "winery", "brewery", "museum", "park",
    "touristattraction", "musicvenue", "performingartstheater", "movietheater", "artgallery",
    "amusementpark", "zoo", "aquarium", "beach", "landmarksorhistoricalbuildings", "store",
    "entertainmentbusiness", "sportsactivitylocation", "healthandbeautybusiness", "dayspa",
    "eventvenue", "civicstructure", "stadiumorarena", "bowlingalley", "comedyclub",
}
# schema.org subtypes of Event that do not end in "event"
EVENT_TYPES = {
    "festival", "exhibitionevent", "courseinstance", "danceevent", "musicevent", "saleevent", "theaterevent",
    "comedyevent", "literaryevent", "screeningevent", "foodevent", "sportsevent", "socialevent", "visualartsevent",
    "businessevent", "childrensevent", "educationevent", "hackathon", "publicationevent",
}
MAX_EVENTS = 25
DAYS = {"monday": "Mo", "tuesday": "Tu", "wednesday": "We", "thursday": "Th", "friday": "Fr",
        "saturday": "Sa", "sunday": "Su"}
PLACE_CATEGORY = {
    "restaurant": "restaurant", "foodestablishment": "restaurant", "barorpub": "bar", "winery": "bar",
    "brewery": "bar", "nightclub": "nightlife", "cafeorcoffeeshop": "cafe", "bakery": "dessert",
    "icecreamshop": "dessert", "museum": "museum", "artgallery": "arts", "park": "park",
    "musicvenue": "live_music", "performingartstheater": "show", "movietheater": "show",
    "comedyclub": "comedy", "beach": "beach", "dayspa": "spa", "store": "shopping",
    "touristattraction": "activity", "amusementpark": "activity", "zoo": "activity", "aquarium": "activity",
}


@dataclass
class PageData:
    url: str
    title: str | None = None
    description: str | None = None
    image: str | None = None
    items: list[ItemHint] = field(default_factory=list)
    text: str = ""


def _types(node: dict) -> list[str]:
    t = node.get("@type")
    return [x.lower() for x in (t if isinstance(t, list) else [t]) if isinstance(x, str)]


def _nodes(data) -> list[dict]:
    """Flatten JSON-LD (lists, @graph) into dict nodes."""
    out: list[dict] = []
    stack = [data]
    while stack:
        d = stack.pop(0)
        if isinstance(d, list):
            stack[:0] = d
        elif isinstance(d, dict):
            if "@graph" in d:
                stack[:0] = d["@graph"] if isinstance(d["@graph"], list) else [d["@graph"]]
            if "@type" in d:
                out.append(d)
    return out


def jsonld_nodes(html: str) -> list[dict]:
    nodes: list[dict] = []
    for block in LD_BLOCK.findall(html):
        try:
            nodes += _nodes(json.loads(block.strip()))
        except json.JSONDecodeError:
            # Some sites put raw newlines inside strings
            try:
                nodes += _nodes(json.loads(re.sub(r"[\r\n\t]+", " ", block.strip())))
            except json.JSONDecodeError:
                continue
    return nodes


def _text(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, list):
        v = v[0] if v else None
    if isinstance(v, dict):
        v = v.get("name") or v.get("url") or v.get("@id")
    s = htmllib.unescape(str(v)).strip() if v is not None else ""
    return s or None


def address_text(a) -> str | None:
    if a is None:
        return None
    if isinstance(a, list):
        a = a[0] if a else None
    if isinstance(a, str):
        return re.sub(r"\s*\n\s*", ", ", a.strip()) or None
    if isinstance(a, dict):
        street = str(a.get("streetAddress") or "").strip()
        tail = [str(p).strip() for p in (a.get("addressLocality"),
                                        " ".join(p for p in (a.get("addressRegion"), a.get("postalCode")) if p))
                if p and str(p).strip()]
        # Some sites (Eventbrite) already put the city and zip inside streetAddress
        tail = [p for p in tail if p.lower() not in street.lower()]
        s = ", ".join(p for p in [street, *tail] if p)
        return s or None
    return None


def _geo(node: dict) -> tuple[float | None, float | None]:
    g = node.get("geo") or {}
    if isinstance(g, list):
        g = g[0] if g else {}
    lat = g.get("latitude", node.get("latitude")) if isinstance(g, dict) else None
    lon = g.get("longitude", node.get("longitude")) if isinstance(g, dict) else None
    try:
        return (float(lat), float(lon)) if lat is not None and lon is not None else (None, None)
    except (TypeError, ValueError):
        return None, None


def _dt(v) -> datetime | None:
    if not v or not isinstance(v, str):
        return None
    try:
        return datetime.fromisoformat(v.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def opening_hours(node: dict) -> str | None:
    """schema.org openingHours / openingHoursSpecification -> OSM opening_hours syntax."""
    oh = node.get("openingHours")
    if oh:
        parts = oh if isinstance(oh, list) else re.split(r",\s*(?=[A-Z][a-z][ \-,])", str(oh))
        return "; ".join(p.strip() for p in parts if p.strip()) or None
    spec = node.get("openingHoursSpecification")
    if isinstance(spec, dict):
        spec = [spec]
    rules = []
    for s in spec or []:
        days = s.get("dayOfWeek")
        days = days if isinstance(days, list) else [days]
        codes = [DAYS.get(str(d).rsplit("/", 1)[-1].lower()) for d in days if d]
        opens, closes = (s.get("opens") or "")[:5], (s.get("closes") or "")[:5]
        if codes and opens and closes:
            rules.append(f"{','.join(c for c in codes if c)} {opens}-{closes}")
    return "; ".join(rules) or None


def _price_level(pr) -> int | None:
    if isinstance(pr, str) and re.fullmatch(r"\s*\$+\s*", pr):
        return min(4, pr.strip().count("$"))
    return None


def _offers(node: dict) -> dict:
    offers = node.get("offers")
    offers = offers if isinstance(offers, list) else [offers] if offers else []
    prices, currency, url, free = [], None, None, None
    for o in offers:
        if not isinstance(o, dict):
            continue
        avail = str(o.get("availability") or "").rsplit("/", 1)[-1].lower()
        sold_out = avail in ("outofstock", "soldout", "discontinued")
        for k in ("price", "lowPrice", "highPrice"):
            try:
                if o.get(k) not in (None, ""):
                    val = float(str(o[k]).replace(",", ""))
                    # A $0 range with no availability, or on a sold-out offer, is a ticket site with
                    # nothing on sale (Dice shows 0.00 once an event is off sale), not a free event
                    if val == 0 and (sold_out or (k != "price" and not avail)):
                        continue
                    prices.append(val)
            except ValueError:
                pass
        currency = currency or o.get("priceCurrency")
        url = url or o.get("url")
    if node.get("isAccessibleForFree") in (True, "true", "True"):
        free = True
    elif prices and max(prices) == 0:
        free = True
    elif prices:
        free = False
    return {"price_min": min(prices) if prices else None, "price_max": max(prices) if prices else None,
            "currency": currency, "ticket_url": url, "is_free": free}


def event_item(node: dict, page_url: str) -> ItemHint | None:
    loc = node.get("location")
    loc = loc[0] if isinstance(loc, list) and loc else loc
    if isinstance(loc, dict) and "virtuallocation" in _types(loc):
        return None  # online only
    loc = loc if isinstance(loc, dict) else {"name": loc} if isinstance(loc, str) else {}
    lat, lon = _geo(loc)
    status = str(node.get("eventStatus") or "").rsplit("/", 1)[-1].lower()
    offers = _offers(node)
    item = ItemHint(
        kind="event",
        name=_text(loc.get("name")) or "",
        event_title=_text(node.get("name")),
        address=address_text(loc.get("address")),
        lat=lat, lon=lon, exact_pin=lat is not None,
        description=_text(node.get("description")),
        starts_at=_dt(node.get("startDate")),
        ends_at=_dt(node.get("endDate")),
        image_url=_text(node.get("image")),
        ticket_url=offers["ticket_url"] or _text(node.get("url")) or page_url,
        price_min=offers["price_min"], price_max=offers["price_max"],
        currency=offers["currency"], is_free=offers["is_free"],
        provider="jsonld", min_age=min_age(_text(node.get("typicalAgeRange"))),
        status="cancelled" if status in ("eventcancelled", "cancelled") else "scheduled",
    )
    if item.description and len(item.description) > 600:
        item.description = item.description[:600].rsplit(" ", 1)[0] + "..."
    if item.starts_at and item.starts_at.tzinfo is None:
        item.flags.append("start time has no time zone")
    return item


def place_item(node: dict, page_url: str) -> ItemHint:
    lat, lon = _geo(node)
    types = _types(node)
    category = next((PLACE_CATEGORY[t] for t in types if t in PLACE_CATEGORY), None)
    cuisine = node.get("servesCuisine")
    return ItemHint(
        kind="place",
        name=_text(node.get("name")) or "",
        address=address_text(node.get("address")),
        lat=lat, lon=lon, exact_pin=lat is not None,
        category=category,
        description=_text(node.get("description")),
        website=_text(node.get("url")) or page_url,
        phone=_text(node.get("telephone")),
        opening_hours=opening_hours(node),
        price_level=_price_level(node.get("priceRange")),
        tags=[c.lower() for c in (cuisine if isinstance(cuisine, list) else [cuisine] if cuisine else [])][:3],
        image_url=_text(node.get("image")),
        provider="jsonld",
    )


def _is_event(n: dict) -> bool:
    return any(t.endswith("event") or t in EVENT_TYPES for t in _types(n))


def _nested_events(places: list[dict]) -> list[dict]:
    """Events a venue lists inside itself (its "event" / "subEvent" property), located at that venue."""
    out = []
    for p in places:
        for key in ("event", "events", "subEvent"):
            inner = p.get(key)
            for e in inner if isinstance(inner, list) else [inner] if inner else []:
                if isinstance(e, dict) and _is_event({"@type": e.get("@type") or "Event"}):
                    out.append({**e, "@type": e.get("@type") or "Event",
                                "location": e.get("location") or {k: v for k, v in p.items() if k not in
                                                                  ("event", "events", "subEvent")}})
    return out


def items_from_jsonld(nodes: list[dict], page_url: str) -> list[ItemHint]:
    places = [n for n in nodes if set(_types(n)) & PLACE_TYPES]
    # A LocalBusiness/Restaurant node is only useful with an address or coordinates
    places = [n for n in places if n.get("address") or n.get("geo")]
    events = [n for n in nodes if _is_event(n)] + _nested_events(places)
    if events:
        # An event with no location of its own happens at the venue the page is about
        here = places[0] if len(places) == 1 else None
        items = []
        for n in events[:MAX_EVENTS]:
            if here is not None and not n.get("location"):
                n = {**n, "location": {k: v for k, v in here.items() if k not in ("event", "events", "subEvent")}}
            items.append(event_item(n, page_url))
        return [i for i in items if i and (i.event_title or i.name)]
    return [place_item(places[0], page_url)] if places else []


def _meta(html: str, prop: str) -> str | None:
    for pat in (rf'<meta[^>]+(?:property|name)=["\']{prop}["\'][^>]+content=["\']([^"\']*)',
                rf'<meta[^>]+content=["\']([^"\']*)["\'][^>]+(?:property|name)=["\']{prop}["\']'):
        m = re.search(pat, html, re.I)
        if m and m.group(1).strip():
            return htmllib.unescape(m.group(1).strip())
    return None


STRUCTURED_CONTENT = re.compile(r'"structuredContent"\s*:\s*(?=\{\s*"modules")')


def embedded_description(html: str) -> str:
    """The organizer's write-up when the page only carries it in embedded data (Eventbrite renders the
    description in the browser, so the page text has the menus but none of the details or prices)."""
    m = STRUCTURED_CONTENT.search(html)
    if not m:
        return ""
    try:
        data, _ = json.JSONDecoder().raw_decode(html, m.end())
    except ValueError:
        return ""
    parts = []
    for mod in data.get("modules") or []:
        if isinstance(mod, dict) and mod.get("type") == "text" and isinstance(mod.get("text"), str):
            text = htmllib.unescape(re.sub(r"<(br|/p|/h\d|/li)[^>]*>", "\n", mod["text"]))
            parts.append(re.sub(r"\n\s*\n+", "\n", re.sub(r"<[^>]+>", "", text)).strip())
    return "\n".join(p for p in parts if p)


def _is_host_name(name: str | None, url: str) -> bool:
    """'Losangelesmuseumoflove' on losangelesmuseumoflove.com: the name is just the domain."""
    label = ((urlsplit(url).hostname or "").removeprefix("www.").split(".") or [""])[0]
    flat = re.sub(r"[^a-z0-9]", "", (name or "").lower())
    return bool(flat) and " " not in (name or "").strip() and flat == re.sub(r"[^a-z0-9]", "", label.lower())


def parse_page(url: str, html: str) -> PageData:
    import trafilatura

    page = PageData(url=url)
    page.title = _meta(html, "og:title") or (re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I) or [None, None])[1]
    page.title = htmllib.unescape(page.title.strip()) if page.title else None
    page.description = _meta(html, "og:description") or _meta(html, "description")
    page.image = _meta(html, "og:image")
    page.items = items_from_jsonld(jsonld_nodes(html), url)
    site_name = _meta(html, "og:site_name")
    if site_name:
        for it in page.items:
            if _is_host_name(it.name, url) and it.name != site_name:
                it.name = site_name  # Wix and others fill the JSON-LD name with the domain, run together
    body = trafilatura.extract(html, include_comments=False, include_tables=True) or ""
    page.text = "\n".join(t for t in (embedded_description(html), body) if t)[:8000]
    return page
