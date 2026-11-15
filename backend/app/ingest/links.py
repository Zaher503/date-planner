"""Anchors on a web page, shared by the venue link finder and the ticket link finder."""
import html as htmllib
import re
from collections.abc import Iterator
from urllib.parse import urljoin, urlsplit

ANCHOR = re.compile(r'<a\b[^>]*?href=["\']([^"\'#][^"\']*)["\'][^>]*>(.*?)</a>', re.S | re.I)
TAGS = re.compile(r"<[^>]+>")
SKIP = re.compile(r"\.(png|jpe?g|gif|svg|webp|pdf|css|js)(\?|$)|^(mailto|tel|javascript):", re.I)


def anchors(html: str, base: str, *, unescape: bool = True) -> Iterator[tuple[str, str]]:
    """(absolute url without fragment, label text) for each http(s) link on the page, in page order.
    Images, files, mailto:, tel: and javascript: links are left out. The label keeps its case and length.
    unescape=False leaves HTML entities in the href and label as written."""
    for href, inner in ANCHOR.findall(html):
        if SKIP.search(href):
            continue
        url = urljoin(base, htmllib.unescape(href) if unescape else href).split("#")[0]
        if urlsplit(url).scheme not in ("http", "https"):
            continue
        label = TAGS.sub(" ", inner)
        yield url, (htmllib.unescape(label) if unescape else label).strip()


def same_site(a: str, b: str) -> bool:
    """Same host, or one is a sub-domain of the other (www. ignored)."""
    ha, hb = (urlsplit(a).hostname or "").removeprefix("www."), (urlsplit(b).hostname or "").removeprefix("www.")
    return ha == hb or ha.endswith("." + hb) or hb.endswith("." + ha)
