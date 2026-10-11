"""Photos next to each listing on an article (a "best rooftop bars" list), matched by heading."""
import re
from urllib.parse import urljoin

from lxml import html as lxml_html
from rapidfuzz import fuzz

from app.ingest.items import ItemHint

HEADINGS = {"h1", "h2", "h3", "h4", "h5"}
SKIP_URL = re.compile(r"logo|avatar|icon|sprite|pixel|tracking|badge|banner|/ads?/|gravatar|\.svg|\.gif|^data:", re.I)
MIN_SIDE = 150
MIN_SCORE = 85
PER_LISTING = 5


def _side(img, attr: str) -> int:
    m = re.match(r"\d+", img.get(attr) or "")
    return int(m.group()) if m else MIN_SIDE


def _src(img) -> str | None:
    for attr in ("data-src", "data-lazy-src", "data-original"):
        if img.get(attr):
            return img.get(attr).strip()
    srcset = img.get("data-srcset") or img.get("srcset")
    if srcset:
        parts = [p.strip().split() for p in srcset.split(",") if p.strip()]
        best = max(parts, key=lambda p: int(re.sub(r"\D", "", p[1]) or 0) if len(p) > 1 else 0, default=None)
        if best:
            return best[0]
    return (img.get("src") or "").strip() or None


def photos_by_heading(html: str, base_url: str) -> list[tuple[str, list[str]]]:
    """[(heading text, image URLs that follow it before the next heading)] in page order."""
    try:
        root = lxml_html.fromstring(html)
    except (ValueError, lxml_html.etree.ParserError):
        return []
    for bad in root.xpath("//script|//style|//nav|//header|//footer|//aside|//noscript"):
        bad.drop_tree()
    sections: list[tuple[str, list[str]]] = []
    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        if el.tag in HEADINGS:
            sections.append((" ".join(el.text_content().split()), []))
        elif el.tag == "img" and sections:
            raw = _src(el)
            if not raw or SKIP_URL.search(raw) or _side(el, "width") < MIN_SIDE or _side(el, "height") < MIN_SIDE:
                continue
            url = urljoin(base_url, raw)
            if url.startswith(("http://", "https://")) and url not in sections[-1][1]:
                sections[-1][1].append(url)
    seen: dict[str, int] = {}
    for _, urls in sections:
        for u in urls:
            seen[u] = seen.get(u, 0) + 1
    # A picture repeated under several headings is page furniture, not a listing photo
    return [(h, [u for u in urls if seen[u] == 1][:PER_LISTING]) for h, urls in sections if h]


def attach(hints: list[ItemHint], html: str, base_url: str) -> None:
    """Fill hint.images with the photos under the heading that names each hint."""
    sections = photos_by_heading(html, base_url)
    if not sections:
        return
    used: set[int] = set()
    for hint in hints:
        names = [n.lower() for n in (hint.event_title, hint.name) if n]
        best, best_score = None, 0.0
        for i, (heading, urls) in enumerate(sections):
            if i in used or not urls:
                continue
            h = heading.lower()
            score = max((fuzz.partial_ratio(n, h) for n in names if len(n) >= 4), default=0)
            if score > best_score:
                best, best_score = i, score
        if best is not None and best_score >= MIN_SCORE:
            used.add(best)
            hint.images = sections[best][1]
