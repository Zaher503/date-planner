"""A real browser for pages the plain fetchers cannot read (bot walls, pages built by JavaScript).

The browser runs in its own container (Playwright's run-server); this module drives it over a
websocket. Every request the page makes, including redirects and subresources, is checked with
net.check_url, so a page can never make the browser reach the LAN or the stack's services.
"""
import logging
import re
from contextlib import contextmanager
from urllib.parse import urlsplit

from app.config import get_settings
from app.net import BROWSER_UA, BlockedURL, check_url

log = logging.getLogger(__name__)

NAV_TIMEOUT_MS = 25_000
# Pictures, video and fonts are not needed to read a page and make it slower to load
SKIP_TYPES = {"image", "media", "font"}


class BrowserUnavailable(RuntimeError):
    pass


def available() -> bool:
    return bool(get_settings().browser_url)


def _guard(route) -> None:
    req = route.request
    if req.resource_type in SKIP_TYPES:
        return route.abort()
    scheme = urlsplit(req.url).scheme
    if scheme in ("data", "blob", "about"):
        return route.continue_()
    try:
        check_url(req.url)
    except BlockedURL:
        return route.abort()
    return route.continue_()


@contextmanager
def page():
    """One fresh browser context and tab, closed afterwards. Raises BrowserUnavailable."""
    url = get_settings().browser_url
    if not url:
        raise BrowserUnavailable("no browser configured")
    from playwright.sync_api import Error, sync_playwright

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect(url, timeout=10_000)
        except Error as e:
            raise BrowserUnavailable(str(e).splitlines()[0]) from e
        ctx = browser.new_context(user_agent=BROWSER_UA, locale="en-US", viewport={"width": 1280, "height": 900},
                                  java_script_enabled=True)
        ctx.route("**/*", _guard)
        ctx.set_default_navigation_timeout(NAV_TIMEOUT_MS)
        ctx.set_default_timeout(8_000)
        try:
            yield ctx.new_page()
        finally:
            ctx.close()
            browser.close()


def goto(pg, url: str) -> str:
    """Open a URL and give the page a moment to build itself. Returns the final URL."""
    check_url(url)
    resp = pg.goto(url, wait_until="domcontentloaded")
    try:
        pg.wait_for_load_state("networkidle", timeout=6_000)
    except Exception:  # chatty pages never go idle; what has loaded is enough
        pass
    if resp is not None and resp.status in (403, 429, 503):
        # A bot check often resolves itself after a few seconds
        pg.wait_for_timeout(4_000)
    if bot_check(pg):
        raise BlockedURL("the site shows a bot check that needs a person")
    return pg.url


BOT_MARKERS = ("captcha-delivery.com", "cf-challenge", "challenge-platform", "px-captcha", "are you a human",
               "verify you are human", "unusual traffic")


def bot_check(pg) -> bool:
    """True when the page is a CAPTCHA or challenge wall rather than the page asked for. These are
    not solved or bypassed: the link is reported as blocked."""
    title = pg.title().lower()
    if "just a moment" in title or "attention required" in title or "access denied" in title:
        return True
    html = pg.content()
    low = html.lower()
    return len(html) < 6000 and any(m in low for m in BOT_MARKERS)


def render(url: str) -> tuple[str, str]:
    """Final URL and rendered HTML of a page."""
    with page() as pg:
        final = goto(pg, url)
        return final, pg.content()


# Clickable things on the page, each tagged so it can be found again after the model picks one
LIST_CLICKABLES = """
() => {
  const out = [];
  let i = 0;
  for (const el of document.querySelectorAll('a[href], button, [role="button"], input[type="submit"]')) {
    const r = el.getBoundingClientRect();
    if (r.width < 4 || r.height < 4 || getComputedStyle(el).visibility === 'hidden') continue;
    const text = (el.innerText || el.value || el.getAttribute('aria-label') || el.title || '').replace(/\\s+/g, ' ').trim();
    if (!text || text.length > 80) continue;
    el.setAttribute('data-dp-i', String(i));
    out.push({ i: i++, tag: el.tagName.toLowerCase(), text, href: el.getAttribute('href') || '' });
    if (i >= 150) break;
  }
  return out;
}
"""
INTEREST = re.compile(r"ticket|book|buy|reserve|rsvp|register|admission|pricing|price|checkout|get\s+in|cover|pass|order|"
                      r"select|choose|continue|see\s+(dates|times|options)|general", re.I)


def clickables(pg) -> list[dict]:
    items = pg.evaluate(LIST_CLICKABLES)
    seen, out = set(), []
    for it in items:
        key = it["text"].lower()
        if key in seen or not INTEREST.search(it["text"] + " " + it["href"]):
            continue
        seen.add(key)
        out.append(it)
    return out[:30]


def click(pg, index: int):
    """Click a tagged element. Returns the tab to read next: a new one if the click opened one."""
    ctx = pg.context
    before = len(ctx.pages)
    pg.locator(f'[data-dp-i="{index}"]').first.click(timeout=6_000)
    pg.wait_for_timeout(1_200)
    target = ctx.pages[-1] if len(ctx.pages) > before else pg
    try:
        target.wait_for_load_state("domcontentloaded", timeout=6_000)
        target.wait_for_load_state("networkidle", timeout=4_000)
    except Exception:
        pass
    return target
