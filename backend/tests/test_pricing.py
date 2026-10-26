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


def test_fetch_falls_through_to_browser(monkeypatch):
    import httpx

    from app import browser, net

    def refuse(url, client=None):
        raise httpx.HTTPStatusError("403", request=httpx.Request("GET", url), response=httpx.Response(403))

    monkeypatch.setattr(net, "_fetch_plain", refuse)
    monkeypatch.setattr(net, "_fetch_impersonated", refuse)
    monkeypatch.setattr(browser, "available", lambda: True)
    monkeypatch.setattr(browser, "render", lambda url: (url, "<html>rendered</html>"))
    assert net.fetch_text("https://x.example/e")[1] == "<html>rendered</html>"


def test_fetch_reports_original_refusal_without_browser(monkeypatch):
    import httpx
    import pytest

    from app import browser, net

    def refuse(url, client=None):
        raise httpx.HTTPStatusError("403", request=httpx.Request("GET", url), response=httpx.Response(403))

    monkeypatch.setattr(net, "_fetch_plain", refuse)
    monkeypatch.setattr(net, "_fetch_impersonated", refuse)
    monkeypatch.setattr(browser, "available", lambda: False)
    with pytest.raises(httpx.HTTPStatusError):
        net.fetch_text("https://x.example/e")


LISTING = (
    '<a href="https://eb.com/e/classic-cinema-night-tickets-1">Tickets</a>'
    '<a href="https://eb.com/e/down-the-rabbit-hole-tickets-2?aff=x">Tickets</a>'
)


def test_listing_events_get_their_own_ticket_link(monkeypatch):
    seen = []

    def find(url, html=None):
        seen.append(url)
        return {"price_min": 40.0, "price_max": 40.0, "is_free": False, "currency": None, "price_text": None}, url

    monkeypatch.setattr(pricing, "find_price", find)
    monkeypatch.setattr(pricing, "browse_for_price", lambda u: (None, None))
    rabbit = ItemHint(kind="event", name="Cinegrill", event_title="Down the Rabbit Hole")
    chess = ItemHint(kind="event", name="Spare Room", event_title="Chess and Jazz")
    assert pricing.enrich([rabbit, chess], "https://venue.com/cal", LISTING) == 1
    assert rabbit.ticket_url == "https://eb.com/e/down-the-rabbit-hole-tickets-2?aff=x"
    assert chess.ticket_url is None and chess.price_min is None
    assert seen == [rabbit.ticket_url]


def test_free_donuts_is_not_free_entry():
    from app.ingest.pricing import FREE_ENTRY
    assert not FREE_ENTRY.search("Come for the free donuts, stay for the dance floor! Free parking nearby.")
    assert FREE_ENTRY.search("Free entry before 11pm") and FREE_ENTRY.search("No cover")
    assert FREE_ENTRY.search("Admission: Free") and FREE_ENTRY.search("This event is free.")


def test_zero_price_from_free_donuts_is_dropped(monkeypatch):
    html = "<html><body><p>A disco party. Come for the free donuts, stay for the dance floor! Doors 9:30 PM.</p></body></html>"
    monkeypatch.setattr(pricing, "chat_json", lambda *a, **k: {
        "found": True, "price_min": 0, "price_max": 0, "is_free": True, "price_text": "free"})
    assert pricing.read_price(html, "https://example.com/e") is None


def test_free_toddlers_do_not_make_the_venue_free(monkeypatch):
    html = ("<html><body><p>Ticket Prices</p><p>General Admission (12 and older) $14.00</p>"
            "<p>Children (Ages 3-11) $7.00</p><p>Toddlers (2 and under)</p><p>Free</p></body></html>")
    monkeypatch.setattr(pricing, "chat_json", lambda *a, **k: {
        "found": True, "price_min": 0, "price_max": 14, "is_free": True, "price_text": "$14.00"})
    out = pricing.read_price(html, "https://example.com/now-playing")
    assert out["is_free"] is None and out["price_max"] == 14
