from app.ingest import pricing
from app.ingest.items import ItemHint

HOME = '<a href="/about">About</a><a href="/tickets/123">Buy Tickets</a><a href="/img/a.png">x</a><a href="https://x.com/book">Book now</a>'


def test_ticket_links_ranked_and_filtered():
    links = pricing.ticket_links(HOME, "https://venue.com/e/1", {"https://venue.com/e/1"})
    assert links[0] == "https://venue.com/tickets/123"
    assert "https://venue.com/about" not in links
    assert all(not l.endswith(".png") for l in links)


def test_find_price_follows_ticket_link(monkeypatch):
    pages = {
        "https://venue.com/e/1": "<html><body><a href='/tickets/123'>Get tickets</a></body></html>",
        "https://venue.com/tickets/123": "<html><body>General admission $25</body></html>",
    }
    monkeypatch.setattr(pricing, "fetch_text", lambda u: (u, pages[u]))
    monkeypatch.setattr(pricing, "read_price", lambda html, url: {"price_min": 25.0, "price_max": 25.0, "is_free": False, "currency": None, "price_text": None} if "$25" in html else None)
    price, at = pricing.find_price("https://venue.com/e/1")
    assert price["price_min"] == 25.0 and at.endswith("/tickets/123")


def test_enrich_skips_priced_events():
    h = ItemHint(kind="event", name="v", price_min=10)
    assert pricing.enrich([h], "https://venue.com") == 0
