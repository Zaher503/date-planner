"""Look a place up on the web: official site, exact location, hours, phone, price tiers, photos.

Steps: search (SearXNG) -> the model picks the official site -> the site is checked to be the
right venue -> home page plus a few contact/hours/pricing pages are read (JSON-LD first, the
model second, every number checked against the page text) -> photos and map coordinates are
collected -> the address is geocoded. Nothing is invented: unsupported values are dropped.
"""
import html as htmllib
import logging
import re
import time
from urllib.parse import urljoin, urlsplit

from lxml import html as lxml_html
from sqlalchemy.orm import Session

from app import browser, hours
from app.ingest.event_page import parse_page
from app.ingest.items import ItemHint
from app.ingest import maps_links, pricing
from app.ingest.page_images import SKIP_URL, _side, _src
from app.llm import verify
from app.llm.ollama import LLMError, chat_json
from app.net import fetch_text
from app.resolve import candidates as cands
from app.resolve import resolver
from app.resolve.candidates import km

log = logging.getLogger(__name__)
REGION = "Los Angeles"
MAX_EXTRA_PAGES = 4
MAX_IMAGES = 12
PAGE_TEXT = 4500

PICK_SYSTEM = """You find the official website of a venue from search results.
Return the result numbers that are the venue's OWN website (or its page on the owner's site), best first.
Never pick review sites, directories, social media, news or listing aggregators. If none is the venue's own site, return an empty list."""
PICK_SCHEMA = {"type": "object", "properties": {"picks": {"type": "array", "items": {"type": "integer"}},
                                                "why": {"type": "string"}}, "required": ["picks", "why"]}

FACTS_SYSTEM = """You read pages from a venue's website and report practical facts about visiting it.
Rules:
- Use only what the text says. Never guess or invent. Use null or an empty list when the text does not say.
- address: the venue's street address, one line.
- phone: as written.
- opening_hours: OpenStreetMap syntax, e.g. "Mo-Fr 10:00-18:00; Sa,Su 09:00-20:00" (24 hour clock). null if the regular hours are not stated or are too irregular to write that way.
- hours_text: the hours as the site words them, short.
- price_tiers: every ticket or admission type with its price in dollars per person (label such as Adult, Child, Senior, Weekend, Group of 6+; note for conditions). One entry per price shown.
- is_free: true only when the text says entry is free.
- price_text: one short sentence on how pricing works (discounts, peak times, memberships), or null."""
FACTS_SCHEMA = {
    "type": "object",
    "properties": {
        "address": {"type": ["string", "null"]},
        "phone": {"type": ["string", "null"]},
        "opening_hours": {"type": ["string", "null"]},
        "hours_text": {"type": ["string", "null"]},
        "price_tiers": {"type": "array", "items": {"type": "object", "properties": {
            "label": {"type": "string"}, "price": {"type": ["number", "null"]}, "note": {"type": ["string", "null"]}},
            "required": ["label", "price", "note"]}},
        "is_free": {"type": ["boolean", "null"]},
        "price_text": {"type": ["string", "null"]},
    },
    "required": ["address", "phone", "opening_hours", "hours_text", "price_tiers", "is_free", "price_text"],
}

PAGE_WORDS = ((r"contact|hours|opening|visit|plan-your|directions|location|find-us|getting-here|tickets?|pricing|prices|"
               r"admission|rates|book|reserve|faq|info", 3), (r"about|experience|what-to|how-it", 1))


def _tokens(name: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", name.lower()) if len(w) > 2 and w not in ("the", "and")]


def _mentions(text: str, name: str) -> bool:
    flat = re.sub(r"[^a-z0-9]+", "", text.lower())
    words = _tokens(name)
    return bool(words) and all(w in flat for w in words)


def _domain_matches(url: str, name: str) -> bool:
    """The site's own domain is the venue's name (academymuseum.org for Academy Museum of Motion Pictures):
    the page text may not repeat the full name, but the domain says whose site it is."""
    label = re.sub(r"[^a-z0-9]", "", ((urlsplit(url).hostname or "").removeprefix("www.").split(".") or [""])[0].lower())
    words = _tokens(name)
    return len(label) >= 5 and label in {"".join(words[:k]) for k in range(1, len(words) + 1)}


def _same_site(a: str, b: str) -> bool:
    ha, hb = (urlsplit(a).hostname or "").removeprefix("www."), (urlsplit(b).hostname or "").removeprefix("www.")
    return ha == hb or ha.endswith("." + hb) or hb.endswith("." + ha)


def known_site(hint: ItemHint, out: dict) -> tuple[str, str] | None:
    """A website the page itself gave (JSON-LD), when it is not an aggregator."""
    if not hint.website or cands.AGGREGATORS.search(hint.website):
        return None
    try:
        final, html = fetch_text(hint.website)
    except Exception:
        return None
    out["site_pick_why"] = "website given by the source page"
    return final, html


def find_site(db: Session | None, hint: ItemHint, out: dict) -> tuple[str, str] | None:
    """(final url, html) of the venue's official site, or None."""
    where = hint.inside or hint.area or REGION
    q = f"{hint.name} {where}".strip()
    results = [r for r in cands.searx(db, q) if r.get("url")]
    out["search_query"] = q
    out["search_results"] = [{"title": r.get("title"), "url": r["url"], "aggregator": bool(cands.AGGREGATORS.search(r["url"]))}
                             for r in results]
    if not results:
        out["site_note"] = "search returned nothing (is the SearXNG tunnel up?)"
        return None
    usable = [r for r in results if not cands.AGGREGATORS.search(r["url"])][:8]
    if not usable:
        out["site_note"] = "only aggregator sites in the results"
        return None
    lines = [f"{i}. {r.get('title', '')} | {r['url']} | {(r.get('content') or '')[:160]}" for i, r in enumerate(usable)]
    prompt = (f"Venue: {hint.name}\nAddress: {hint.address or 'unknown'}\nArea: {hint.area or 'unknown'}\n"
              f"Inside: {hint.inside or '-'}\n\nSearch results:\n" + "\n".join(lines))
    try:
        pick = chat_json(PICK_SYSTEM, prompt, PICK_SCHEMA)
    except LLMError as e:
        out["site_note"] = f"model pick failed: {e}"
        return None
    out["site_pick_why"] = pick.get("why")
    for i in [p for p in pick.get("picks", []) if isinstance(p, int) and 0 <= p < len(usable)][:3]:
        url = usable[i]["url"]
        try:
            final, html = fetch_text(url)
        except Exception as e:
            out.setdefault("site_rejected", []).append({"url": url, "why": f"fetch failed: {type(e).__name__}"})
            continue
        page = parse_page(final, html)
        text = page.text + " " + (page.title or "")
        if len(text.strip()) < 40 and browser.available():
            try:
                final, html = browser.render(final)
                text = parse_page(final, html).text
            except Exception as e:
                log.info("browser render of %s failed: %s", final, e)
        if _mentions(text + " " + final, hint.name) or _domain_matches(final, hint.name):
            return final, html
        out.setdefault("site_rejected", []).append({"url": final, "why": "page does not mention the venue name"})
    out["site_note"] = out.get("site_note") or "no result passed the name check"
    return None


def page_links(html: str, base: str) -> list[str]:
    scored: dict[str, int] = {}
    for href, inner in re.findall(r'<a\b[^>]*?href=["\']([^"\'#][^"\']*)["\'][^>]*>(.*?)</a>', html, re.S | re.I):
        if re.search(r"\.(png|jpe?g|gif|svg|webp|pdf|css|js)(\?|$)|^(mailto|tel|javascript):", href, re.I):
            continue
        url = urljoin(base, href).split("#")[0]
        if urlsplit(url).scheme not in ("http", "https") or not _same_site(url, base) or url.rstrip("/") == base.rstrip("/"):
            continue
        label = re.sub(r"<[^>]+>", " ", inner).strip().lower()[:60]
        s = max((w for pat, w in PAGE_WORDS if re.search(pat, label) or re.search(pat, urlsplit(url).path.lower())), default=0)
        if s:
            scored[url] = max(scored.get(url, 0), s)
    return [u for u, _ in sorted(scored.items(), key=lambda kv: -kv[1])][:MAX_EXTRA_PAGES]


def page_photos(html: str, base: str) -> list[str]:
    urls: list[str] = []
    og = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)', html, re.I)
    if og:
        urls.append(urljoin(base, og.group(1)))
    try:
        root = lxml_html.fromstring(html)
    except (ValueError, lxml_html.etree.ParserError):
        return urls
    for bad in root.xpath("//script|//style|//noscript|//footer"):
        bad.drop_tree()
    for img in root.iter("img"):
        raw = _src(img)
        if not raw or SKIP_URL.search(raw) or _side(img, "width") < 200 or _side(img, "height") < 150:
            continue
        u = urljoin(base, raw)
        if u.startswith(("http://", "https://")) and u not in urls:
            urls.append(u)
    return urls


def map_point(html: str) -> tuple[float, float, str] | None:
    """Coordinates in an embedded Google map or a maps link on the page."""
    for pat, order, label in ((r"!2d(-?\d+\.\d+)!3d(-?\d+\.\d+)", "lonlat", "map embed"),
                              (r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)", "latlon", "map link"),
                              (r"maps[^\"' ]*[?&](?:q|ll|query)=(-?\d{1,2}\.\d+)(?:,|%2C)(-?\d{1,3}\.\d+)", "latlon", "map link"),
                              (r"maps[^\"' ]*@(-?\d{1,2}\.\d+),(-?\d{1,3}\.\d+)", "latlon", "map link")):
        m = re.search(pat, html)
        if m:
            a, b = float(m.group(1)), float(m.group(2))
            lat, lon = (a, b) if order == "latlon" else (b, a)
            if 20 < lat < 60 and -130 < lon < -60:
                return lat, lon, label
    return None


def footer_text(html: str) -> str:
    """Text of the page's footer. Article extraction drops it, but small venue sites keep their
    address and phone only there."""
    try:
        root = lxml_html.fromstring(html)
    except (ValueError, lxml_html.etree.ParserError):
        return ""
    for bad in root.xpath("//script|//style|//noscript"):
        bad.drop_tree()
    parts: list[str] = []
    for el in root.xpath("//footer|//*[contains(translate(@id, 'FOTER', 'foter'), 'footer')]"
                         "|//*[contains(translate(@class, 'FOTER', 'foter'), 'footer')]"):
        text = " ".join(" ".join(el.itertext()).split())
        if text and not any(text in p for p in parts):
            parts = [p for p in parts if p not in text] + [text]
    return "\n".join(parts)[:800]


def with_footer(text: str, html: str) -> str:
    """Page text plus its footer, labelled so the extractor can tell it is page-wide."""
    foot = footer_text(html)
    if foot and foot not in text:
        return text + "\n\nFooter of the page (address, phone and venue name here apply to every event listed above):\n" + foot
    return text


LABEL_ATTR = re.compile(r"""(?:aria-label|title|alt|data-[\w-]+)=["']([^"']*\$\s?\d[^"']*)["']""", re.I)
TIME_PREFIX = re.compile(r"^\s*\d{1,2}:\d{2}\s*[ap]m\s*", re.I)
NOT_VENUE = re.compile(r"apps\.apple\.com|play\.google\.com|facebook\.|instagram\.|twitter\.|x\.com|tiktok\.|youtube\.|maps\.", re.I)
MAPS_LINK = re.compile(r"""https?://(?:maps\.app\.goo\.gl|goo\.gl/maps|(?:www\.)?google\.com/maps|maps\.apple\.com)[^"'<> )]+""", re.I)


def price_labels(html: str) -> str:
    """Prices that live in element labels (ticket selectors) and never reach the page text."""
    seen: dict[str, str] = {}
    for raw in LABEL_ATTR.findall(html):
        label = " ".join(htmllib.unescape(raw).split())
        seen.setdefault(TIME_PREFIX.sub("", label), label)
    return "\n".join(list(seen)[:30])


def maps_point(html: str, out: dict) -> tuple[float, float, str] | None:
    """Coordinates behind the page's own Get directions / map link."""
    for link in dict.fromkeys(MAPS_LINK.findall(html)):
        try:
            final, mh = maps_links.expand_and_parse(htmllib.unescape(link))
        except Exception as e:
            out["flags"].append(f"maps link failed: {type(e).__name__}")
            continue
        if mh.lat is not None:
            return mh.lat, mh.lon, "Google Maps link"
    return None


def _hour_on_page(hhmm: str, text: str) -> bool:
    """18:00 is backed by '6 pm', '18:00' or a bare 6 in a range like '6 to 10 pm'."""
    if verify.time_supported(hhmm, text):
        return True
    h, m = (int(x) for x in hhmm.split(":"))
    return m == 0 and any(re.search(rf"(?<![\d:]){x}(?![\d:])", text) for x in {h, h % 12 or 12})


HOURS_FIX_SYSTEM = """Rewrite opening hours in OpenStreetMap opening_hours syntax.
Examples: "Mo-Fr 09:00-17:00; Sa 10:00-14:00; Su off" and "We,Th 18:00-22:00; Fr,Sa 17:00-23:00; Su 17:00-22:00".
Use Mo Tu We Th Fr Sa Su, a 24 hour clock, rules separated by "; ". Use only the days and times in the text, nothing else.
Return null if the text does not give regular weekly hours."""
HOURS_FIX_SCHEMA = {"type": "object", "properties": {"opening_hours": {"type": ["string", "null"]}}, "required": ["opening_hours"]}


def check_hours(spec: str | None, text: str, written: str | None = None) -> tuple[str | None, str | None]:
    """Keep an OSM hours string only when it parses and every time in it is on the page.
    A string that does not parse gets one rewrite from the hours as the site words them."""
    if not spec and not written:
        return None, None
    note = None
    if spec and hours.parse(spec) is None:
        note, spec = "hours string was not valid, rewritten", None
    if not spec and written:
        try:
            spec = (chat_json(HOURS_FIX_SYSTEM, written, HOURS_FIX_SCHEMA).get("opening_hours") or "").strip() or None
        except LLMError:
            spec = None
        if spec and hours.parse(spec) is None:
            return None, "hours could not be written in a valid form"
    if not spec:
        return None, note
    bad = [t for t in set(re.findall(r"\d{1,2}:\d{2}", spec)) if t not in ("00:00", "24:00") and not _hour_on_page(t, text)]
    if bad:
        return None, f"hours dropped, times not on the page: {', '.join(sorted(bad))}"
    return spec, note


def street_part(address: str) -> str:
    """'Kinn Studio - 150 Horizon Ave, Venice' -> '150 Horizon Ave, Venice'; an address that already starts
    with a number, or has no number after a separator, comes back as it was."""
    a = address.strip()
    if re.match(r"\d", a):
        return a
    m = re.search(r"(?:\s[-–—:|]\s+|,\s*)(\d{1,6}[A-Za-z]?\s+[A-Za-z].*)$", a)
    return m.group(1).strip() if m else a


def has_number(address: str | None) -> bool:
    return bool(address and re.match(r"\s*\d", address))


def read_facts(pages: list[dict], out: dict) -> dict:
    blob = "\n\n".join(f"## {p['url']}\n{p['text'][:PAGE_TEXT]}" for p in pages)[:16000]
    out["facts_input_chars"] = len(blob)
    try:
        raw = chat_json(FACTS_SYSTEM, blob, FACTS_SCHEMA)
    except LLMError as e:
        out["flags"].append(f"model could not read the site: {e}")
        return {}
    full = " ".join(p["text"] for p in pages)
    nums = verify.numbers_in(full)
    facts = {"address": (raw.get("address") or "").strip() or None, "phone": (raw.get("phone") or "").strip() or None,
             "hours_text": (raw.get("hours_text") or "").strip() or None,
             "price_text": (raw.get("price_text") or "").strip() or None, "is_free": raw.get("is_free")}
    if facts["address"]:
        facts["address"] = street_part(facts["address"])
    if facts["address"] and not has_number(facts["address"]):
        out["flags"].append(f"address dropped, no street number: {facts['address']}")
        facts["address"] = None
    if facts["address"] and not verify.address_supported(facts["address"], full):
        out["flags"].append(f"address dropped, not on the page: {facts['address']}")
        facts["address"] = None
    if facts["phone"]:
        digits = re.sub(r"\D", "", facts["phone"])
        if len(digits) < 7 or digits[-10:] not in re.sub(r"\D", "", full):
            out["flags"].append(f"phone dropped, not on the page: {facts['phone']}")
            facts["phone"] = None
    facts["opening_hours"], why = check_hours(raw.get("opening_hours"), full, facts["hours_text"])
    if why:
        out["flags"].append(why)
    tiers = []
    for t in raw.get("price_tiers") or []:
        if t.get("price") is not None and not verify.price_supported(t["price"], nums):
            out["flags"].append(f"price dropped, not on the page: {t.get('label')} ${t['price']}")
            continue
        tiers.append({"label": t.get("label"), "price": t.get("price"), "note": t.get("note")})
    facts["price_tiers"] = tiers
    if facts["is_free"] is not True or not re.search(r"free|no cover", full, re.I):
        facts["is_free"] = None
    return facts


PHONE_RE = re.compile(r"(?<!\d)\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}(?!\d)")


def other_pages(hint: ItemHint, site_url: str, out: dict) -> list[dict]:
    """Up to two other non-aggregator search results that name the venue and show a phone number
    (used for a phone the official site lacks)."""
    pages = []
    for r in out.get("search_results") or []:
        u = r["url"]
        if r.get("aggregator") or _same_site(u, site_url) or NOT_VENUE.search(u) or any(p["url"] == u for p in pages):
            continue
        try:
            final, body = fetch_text(u)
        except Exception:
            continue
        text = parse_page(final, body).text
        found = list(PHONE_RE.finditer(text))
        if found and _mentions(text, hint.name):
            # Only the lines around each number: the phone is often past the part of a long page the model gets
            snippets = [text[max(0, m.start() - 250):m.end() + 100] for m in found[:3]]
            pages.append({"url": final, "text": " ... ".join(snippets)})
        if len(pages) == 2:
            break
    return pages


def _pin_rank(e: dict) -> int:
    """The site's structured data first, then a map link the owner put on the page, then an exact house-number
    geocode, then the site's map embed (its centre often sits on the building next door), then a street-only
    geocode."""
    m = e["method"]
    return (0 if "structured data" in m else 3 if "embed" in m else 4 if "street only" in m
            else 2 if "exact house" in m else 1)


def locate(db: Session | None, home: tuple[float, float], hint: ItemHint, address: str | None,
           jsonld: ItemHint | None, mp, out: dict) -> dict:
    """Best point for the venue and the evidence for it."""
    evidence = []
    if jsonld and jsonld.lat is not None:
        evidence.append({"method": "site structured data (geo)", "lat": jsonld.lat, "lon": jsonld.lon})
    for m in mp or []:
        evidence.append({"method": f"site {m[2]}", "lat": m[0], "lon": m[1]})
    if address:
        try:
            c = resolver._geocode_address(db, address, home, hint.area)
        except Exception as e:
            c = None
            out["flags"].append(f"geocoder failed: {type(e).__name__}")
        if c:
            evidence.append({"method": "address geocoded" + (" (exact house)" if c.extra.get("house_match") else " (street only)"),
                             "lat": c.lat, "lon": c.lon, "matched": c.address_text})
    if not evidence:
        return {"lat": None, "lon": None, "method": None, "evidence": [], "agreement_km": None}
    best = min(evidence, key=_pin_rank)
    far = max((km(best["lat"], best["lon"], e["lat"], e["lon"]) for e in evidence), default=0)
    return {"lat": best["lat"], "lon": best["lon"], "method": best["method"], "evidence": evidence,
            "agreement_km": round(far, 3)}


def lookup(db: Session | None, hint: ItemHint, home: tuple[float, float], stage=lambda s: None) -> dict:
    """Everything the venue's own website says. Never raises for web problems: gaps come back as flags."""
    t0 = time.time()
    out: dict = {"name": hint.name, "flags": [], "pages": [], "website": None}
    stage(f"finding the website of {hint.name}")
    site = known_site(hint, out) or find_site(db, hint, out)
    if site is None:
        out["location"] = locate(db, home, hint, hint.address, None, [], out)
        out["elapsed"] = round(time.time() - t0, 1)
        return out
    url, home_html = site
    out["website"] = url
    stage(f"reading {urlsplit(url).hostname}")
    pages, htmls = [], {url: home_html}
    ticket_pages = [u for u in pricing.ticket_links(home_html, url, {url}) if not _same_site(u, url) and not NOT_VENUE.search(u)][:2]
    out["ticket_links"] = ticket_pages
    for u in page_links(home_html, url) + ticket_pages:
        try:
            final, body = fetch_text(u)
            htmls[final] = body
        except Exception as e:
            out["pages_failed"] = out.get("pages_failed", []) + [{"url": u, "why": type(e).__name__}]
    jsonld = None
    for u, body in htmls.items():
        pg = parse_page(u, body)
        text = pg.text
        if len(text) < 200 and browser.available():
            try:
                _, rendered = browser.render(u)
                body, pg = rendered, parse_page(u, rendered)
                text = pg.text
                htmls[u] = body
                out["pages"].append({"url": u, "via": "browser"})
            except Exception:
                out["pages"].append({"url": u, "via": "plain"})
        else:
            out["pages"].append({"url": u, "via": "plain"})
        foot = footer_text(body)
        if foot and foot not in text:
            text += "\n\nFooter of the page:\n" + foot
        labels = price_labels(body)
        if labels:
            text += "\n\nPrice labels on the page:\n" + labels
        pages.append({"url": u, "text": text})
        jsonld = jsonld or next((i for i in pg.items if i.kind == "place"), None)
    out["pages"] = list({p["url"]: p for p in out["pages"]}.values())
    stage("reading hours, prices and contact details")
    facts = read_facts(pages, out)

    if not facts.get("phone") and not (jsonld and jsonld.phone):
        extra = other_pages(hint, url, out)
        if extra:
            out["phone_pages"] = [p["url"] for p in extra]
            facts["phone"] = read_facts(pages + extra, out).get("phone")
            if facts["phone"]:
                out["flags"].append("phone from other pages that name the venue")

    # Structured data on the site beats the model's reading of the text
    address = (jsonld.address if jsonld and jsonld.address else None) or facts.get("address")
    phone = (jsonld.phone if jsonld and jsonld.phone else None) or facts.get("phone")
    spec = None
    full = " ".join(p["text"] for p in pages)
    if jsonld and jsonld.opening_hours:
        spec, _ = check_hours(jsonld.opening_hours, full + " " + jsonld.opening_hours)
    spec = spec or facts.get("opening_hours")
    out.update(address=address, phone=phone, opening_hours=spec, hours_text=facts.get("hours_text"),
               price_tiers=facts.get("price_tiers", []), is_free=facts.get("is_free"), price_text=facts.get("price_text"),
               price_level=jsonld.price_level if jsonld else None,
               sources={"address": "site structured data" if jsonld and jsonld.address else "model, checked against page" if address else None,
                        "phone": "site structured data" if jsonld and jsonld.phone else "model, checked against page" if phone else None,
                        "opening_hours": "site structured data" if jsonld and jsonld.opening_hours and spec == jsonld.opening_hours
                        else "model, checked against page" if spec else None})

    stage("collecting photos and map location")
    images: list[str] = []
    for u, body in htmls.items():
        for img in page_photos(body, u):
            if img not in images:
                images.append(img)
    if jsonld and jsonld.image_url:
        images.insert(0, urljoin(url, jsonld.image_url))
    out["images"] = list(dict.fromkeys(images))[:MAX_IMAGES]
    mp = next((m for m in (map_point(b) for b in htmls.values()) if m), None)
    mp2 = next((m for m in (maps_point(b, out) for b in list(htmls.values())[:1]) if m), None)
    out["location"] = locate(db, home, hint, address or hint.address, jsonld, [m for m in (mp, mp2) if m], out)
    out["elapsed"] = round(time.time() - t0, 1)
    return out


def site_pin(v: dict) -> tuple[float, float, str] | None:
    """A point the venue's own site vouches for: structured data or its map link, else an exact-house
    geocode of the address the site states. None when the site gave nothing usable."""
    ev = sorted((v.get("location") or {}).get("evidence") or [], key=_pin_rank)
    own = next((e for e in ev if _pin_rank(e) <= 3), None)
    return (own["lat"], own["lon"], own["method"]) if own else None


def apply(hint: ItemHint, v: dict) -> None:
    """Fill empty fields of the item from what the site said."""
    def fill(attr, val):
        if val not in (None, "", []) and not getattr(hint, attr):
            setattr(hint, attr, val)
            hint.flags.append(f"{attr} from website")
    fill("website", v.get("website"))
    fill("phone", v.get("phone"))
    fill("opening_hours", v.get("opening_hours"))
    fill("hours_text", v.get("hours_text"))
    if has_number(v.get("address")) and hint.address and not has_number(hint.address):
        hint.address = v["address"]  # "Los Angeles" or "Aquarium Way" -> the street address the site gives
        hint.flags.append("address from website (replaced a vague one)")
    fill("address", v.get("address"))
    fill("price_level", v.get("price_level"))
    if hint.kind == "place":
        fill("images", v.get("images"))
        fill("price_tiers", v.get("price_tiers"))
        fill("price_text", v.get("price_text"))
        if v.get("is_free") and hint.is_free is None:
            hint.is_free = True
