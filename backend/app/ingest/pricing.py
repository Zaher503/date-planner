"""Find a ticket price a page does not state itself.

Event listings often say "Tickets" or "Book now" and keep the price one or two pages deeper. For an
event with no price yet, follow the most ticket-like links (at most two pages deep), read each page's
structured data first and the local model second, and stop at the first price found.
"""
import html as htmllib
import logging
import re
from urllib.parse import urljoin, urlsplit

from app.ingest.event_page import jsonld_nodes, parse_page
from app.ingest.items import ItemHint
from app.llm import verify
from app import browser
from app.llm.ollama import LLMError, chat_json
from app.net import BlockedURL, fetch_text

log = logging.getLogger(__name__)

MAX_DEPTH = 2
MAX_PAGES = 5
LINK = re.compile(r'<a\b[^>]*?href=["\']([^"\'#][^"\']*)["\'][^>]*>(.*?)</a>', re.S | re.I)
TAGS = re.compile(r"<[^>]+>")
# Words on the link or in its address, strongest first
SIGNALS = (
    (r"buy\s+tickets?|get\s+tickets?|book\s+now|book\s+tickets?|reserve|rsvp|register|purchase", 5),
    (r"tickets?|admission|pricing|prices|book", 3),
    (r"checkout|cart|order|pass", 1),
)
VENDORS = ("eventbrite", "ticketmaster", "axs.com", "seetickets", "dice.fm", "tixr", "etix", "universe.com",
           "luma", "lu.ma", "posh.vip", "ra.co", "opentable", "resy", "tock", "fever", "showclix", "eventim")
SKIP = re.compile(r"\.(png|jpe?g|gif|svg|webp|pdf|css|js)(\?|$)|^(mailto|tel|javascript):", re.I)

SYSTEM = """You read a web page about an event and report what attending costs.
Rules:
- Use only prices written in the text. Never guess or invent one.
- price_min and price_max are per person in dollars. A single price sets both. Fees and tax can be left out.
- is_free is true only when the text says the event is free (free entry, no cover, $0).
- found is false when the text does not say what it costs."""
SCHEMA = {
    "type": "object",
    "properties": {
        "found": {"type": "boolean"},
        "price_min": {"type": ["number", "null"]},
        "price_max": {"type": ["number", "null"]},
        "is_free": {"type": ["boolean", "null"]},
        "price_text": {"type": ["string", "null"]},
    },
    "required": ["found", "price_min", "price_max", "is_free", "price_text"],
}


def has_price(h: ItemHint) -> bool:
    return h.price_min is not None or h.price_max is not None or h.is_free is not None or bool(h.price_text)


def ticket_links(html: str, base: str, seen: set[str]) -> list[str]:
    """Links that look like they lead to tickets or prices, best first."""
    scored: dict[str, int] = {}
    for href, inner in LINK.findall(html):
        if SKIP.search(href):
            continue
        url = urljoin(base, htmllib.unescape(href)).split("#")[0]
        if urlsplit(url).scheme not in ("http", "https") or url in seen:
            continue
        label = htmllib.unescape(TAGS.sub(" ", inner)).strip().lower()[:80]
        text = f"{label} {url.lower()}"
        score = max((w for pat, w in SIGNALS if re.search(pat, label)), default=0)
        score += max((w for pat, w in SIGNALS if re.search(pat, url.lower())), default=0) // 2
        if any(v in url.lower() for v in VENDORS):
            score += 2
        if score >= 3 and text.strip():
            scored[url] = max(scored.get(url, 0), score)
    return [u for u, _ in sorted(scored.items(), key=lambda kv: -kv[1])][:3]


def read_price(html: str, url: str) -> dict | None:
    """Price from the page's structured data, else from its text with the local model."""
    page = parse_page(url, html)
    for item in page.items:
        if item.kind == "event" and (item.price_min is not None or item.is_free is not None):
            return {"price_min": item.price_min, "price_max": item.price_max, "is_free": item.is_free,
                    "currency": item.currency, "price_text": None}
    text = page.text[:5000]
    if not re.search(r"\$\s?\d|free|no cover|\d+\s?usd", text, re.I):
        return None
    try:
        raw = chat_json(SYSTEM, f"Page: {page.title or url}\n\n{text}", SCHEMA)
    except LLMError as e:
        log.info("price read failed for %s: %s", url, e)
        return None
    if not raw.get("found"):
        return None
    nums = verify.numbers_in(text)
    out = {"price_min": raw.get("price_min"), "price_max": raw.get("price_max"),
           "is_free": raw.get("is_free"), "currency": None, "price_text": (raw.get("price_text") or "")[:300] or None}
    for k in ("price_min", "price_max"):
        if out[k] is not None and not verify.price_supported(out[k], nums):
            out[k] = None
    if out["is_free"] and "free" not in text.lower() and "no cover" not in text.lower():
        out["is_free"] = None
    if out["price_min"] is None and out["price_max"] is None and out["is_free"] is None:
        return None
    return out


def find_price(start: str, html: str | None = None) -> tuple[dict | None, str | None]:
    """Walk from a page through its ticket links. Returns (price, url where it was found)."""
    seen: set[str] = {start}
    frontier: list[tuple[str, str | None, int]] = [(start, html, 0)]
    pages = 0
    while frontier and pages < MAX_PAGES:
        url, body, depth = frontier.pop(0)
        try:
            if body is None:
                url, body = fetch_text(url)
            pages += 1
        except Exception as e:  # a dead ticket link must not sink the import
            log.info("ticket page %s: %s", url, e)
            continue
        price = read_price(body, url)
        if price:
            return price, url
        if depth < MAX_DEPTH:
            for link in ticket_links(body, url, seen):
                seen.add(link)
                frontier.append((link, None, depth + 1))
    return None, None


PICK_SYSTEM = """You help find what an event costs by pressing buttons on its web page.
You get a list of clickable things on the page, each with a number and its text. Choose the one most likely to lead to
ticket prices (Buy Tickets, Book Now, Reserve, Get Tickets, RSVP, See pricing). Never choose anything that logs in, signs up for
a newsletter, shares, or pays. If nothing is likely to help, answer index -1."""
PICK_SCHEMA = {"type": "object", "properties": {"index": {"type": "integer"}, "why": {"type": "string"}},
               "required": ["index", "why"]}
MAX_CLICKS = 4


def browse_for_price(start: str) -> tuple[dict | None, str | None]:
    """Last resort for pages that only show a price after a click: a real browser, with the local
    model choosing which button to press (at most four presses)."""
    if not browser.available():
        return None, None
    try:
        with browser.page() as pg:
            browser.goto(pg, start)
            tried: set[str] = set()
            for _ in range(MAX_CLICKS + 1):
                price = read_price(pg.content(), pg.url)
                if price:
                    return price, pg.url
                options = [o for o in browser.clickables(pg) if o["text"].lower() not in tried]
                if not options or _ >= MAX_CLICKS:
                    return None, None
                lines = [f"{o['i']}: {o['text']}" + (f" -> {o['href'][:80]}" if o["href"] else "") for o in options]
                prompt = f"Page: {pg.title()}\n\nClickable things:\n" + "\n".join(lines)
                try:
                    pick = chat_json(PICK_SYSTEM, prompt, PICK_SCHEMA)
                except LLMError:
                    return None, None
                chosen = next((o for o in options if o["i"] == pick.get("index")), None)
                if chosen is None:
                    return None, None
                tried.add(chosen["text"].lower())
                log.info("price hunt: pressing %r (%s)", chosen["text"], pick.get("why"))
                pg = browser.click(pg, chosen["i"])
    except (browser.BrowserUnavailable, BlockedURL) as e:
        log.info("browser price hunt skipped: %s", e)
    except Exception as e:  # page-level failures (timeouts, closed tabs) just end the hunt
        log.info("browser price hunt for %s failed: %s", start, e)
    return None, None


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def own_ticket_link(h: ItemHint, html: str, base: str) -> str | None:
    """The link on a listing page whose address carries this event's whole title, if any."""
    want = _words(h.event_title or "")
    if not want:
        return None
    for href, _ in LINK.findall(html):
        if SKIP.search(href):
            continue
        url = urljoin(base, htmllib.unescape(href)).split("#")[0]
        if urlsplit(url).scheme not in ("http", "https"):
            continue
        slug = _words(urlsplit(url).path)
        if any(slug[i:i + len(want)] == want for i in range(len(slug))):
            return url
    return None


def enrich(hints: list[ItemHint], start_url: str | None, html: str | None = None) -> int:
    """Fill the price of events that have none. Returns how many were filled."""
    todo = [h for h in hints if h.kind == "event" and not has_price(h)]
    if not todo:
        return 0
    if start_url and html is None and any(not h.ticket_url for h in todo):
        try:
            _, html = fetch_text(start_url)
        except Exception as e:  # without the page, fall back to walking from the start url
            log.info("listing page %s: %s", start_url, e)
    filled = 0
    for h in todo:
        if not h.ticket_url and start_url and html:
            h.ticket_url = own_ticket_link(h, html, start_url)
            if not h.ticket_url and len(todo) > 1:
                # A listing of several events: its first ticket link belongs to some other event
                continue
        url = h.ticket_url or start_url
        if not url:
            continue
        try:
            price, found_at = find_price(url, html if url == start_url else None)
        except BlockedURL:
            continue
        if not price:
            price, found_at = browse_for_price(url)
        if not price:
            continue
        for k in ("price_min", "price_max", "is_free", "price_text", "currency"):
            if price.get(k) is not None:
                setattr(h, k, price[k])
        if not h.ticket_url and found_at:
            h.ticket_url = found_at
        h.flags.append("price found on a ticket page")
        filled += 1
    return filled
