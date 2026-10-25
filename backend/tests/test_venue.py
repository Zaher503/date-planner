from types import SimpleNamespace

from app.api.common import place_price_label, tiers_label
from app.ingest import pipeline, venue
from app.ingest.items import ItemHint
from app.resolve.candidates import Candidate

HOME_PAGE = """<html><head><title>Glow or Go LA</title>
<meta property="og:image" content="/img/hero.jpg"></head><body>
<a href="/contact-us/">Contact</a><a href="/faq/">FAQ</a><a href="/blog/">Blog</a>
<a href="https://tickets.example.com/m/1">TICKETS</a><a href="https://apps.apple.com/app/x">App</a>
<a href="https://maps.app.goo.gl/abc">GET DIRECTIONS</a>
<div aria-label="2:00 pm Mini Glow (2 - 3 people) $32.00"></div>
<div aria-label="4:00 pm Mini Glow (2 - 3 people) $32.00"></div>
<div aria-label="2:00 pm Mega Glow (4 - 6 people) $28.00"></div>
<img src="/img/room.jpg" width="800" height="600"><img src="/img/logo.svg"><img src="/img/tiny.png" width="20" height="20">
<p>Glow or Go is at 8500 Beverly Blvd, Los Angeles. Call (310) 555-0142. Open Wed-Thu 6 to 10 pm.</p>
</body></html>"""


def test_page_links_same_site_and_useful():
    links = venue.page_links(HOME_PAGE, "https://glow.example.com/")
    assert "https://glow.example.com/contact-us/" in links
    assert "https://glow.example.com/blog/" not in links
    assert all("example.com" in u and "tickets.example.com" not in u for u in links)


def test_price_labels_dedupe_by_tier_not_time():
    text = venue.price_labels(HOME_PAGE)
    assert text.count("Mini Glow") == 1
    assert "Mega Glow (4 - 6 people) $28.00" in text


def test_page_photos_skip_logos_and_thumbnails():
    photos = venue.page_photos(HOME_PAGE, "https://glow.example.com/")
    assert photos[0] == "https://glow.example.com/img/hero.jpg"
    assert "https://glow.example.com/img/room.jpg" in photos
    assert not any("logo" in p or "tiny" in p for p in photos)


def test_map_point_from_embed_and_link():
    embed = '<iframe src="https://www.google.com/maps/embed?pb=!1m18!2d-118.3773546!3d34.0751706!2m3"></iframe>'
    assert venue.map_point(embed)[:2] == (34.0751706, -118.3773546)
    link = '<a href="https://maps.google.com/?q=34.07,-118.37">x</a>'
    assert venue.map_point(link)[:2] == (34.07, -118.37)
    assert venue.map_point("<p>nothing</p>") is None


def test_check_hours_accepts_range_wording_and_rejects_invented_times():
    text = "Open 6 to 10 pm Wednesday and Thursday"
    assert venue.check_hours("We,Th 18:00-22:00", text)[0] == "We,Th 18:00-22:00"
    spec, why = venue.check_hours("We,Th 18:00-23:30", text)
    assert spec is None and "23:30" in why


def test_check_hours_rewrites_invalid_string(monkeypatch):
    monkeypatch.setattr(venue, "chat_json", lambda *a, **k: {"opening_hours": "We,Th 18:00-22:00"})
    spec, note = venue.check_hours("Wednesday to Thursday evenings", "Open 6 to 10 pm Wed-Thu", "6 to 10 pm Wed-Thu")
    assert spec == "We,Th 18:00-22:00" and "rewritten" in note


def test_read_facts_drops_what_the_page_does_not_say(monkeypatch):
    raw = {"address": "Beverly Center", "phone": "(310) 999-0000", "opening_hours": None, "hours_text": None,
           "price_tiers": [{"label": "Adult", "price": 32, "note": None}, {"label": "VIP", "price": 99, "note": None}],
           "is_free": False, "price_text": None}
    monkeypatch.setattr(venue, "chat_json", lambda *a, **k: raw)
    out = {"flags": []}
    facts = venue.read_facts([{"url": "u", "text": "Tickets $32. Call (310) 555-0142. 8500 Beverly Blvd"}], out)
    assert facts["address"] is None  # no street number
    assert facts["phone"] is None  # not on the page
    assert [t["label"] for t in facts["price_tiers"]] == ["Adult"]  # $99 never appears
    assert facts["is_free"] is None
    assert len(out["flags"]) == 3


def _fake_web(monkeypatch, pages):
    monkeypatch.setattr(venue.cands, "searx", lambda db, q: [
        {"title": "Yelp", "url": "https://www.yelp.com/biz/glow", "content": ""},
        {"title": "Glow or Go LA", "url": "https://glow.example.com/", "content": "8500 Beverly Blvd"}])
    monkeypatch.setattr(venue, "fetch_text", lambda u: (u, pages[u]))
    monkeypatch.setattr(venue.pricing, "ticket_links", lambda html, base, seen: ["https://tickets.example.com/m/1"])
    monkeypatch.setattr(venue.browser, "available", lambda: False)
    monkeypatch.setattr(venue, "maps_point", lambda html, out: (34.0751706, -118.3773546, "Google Maps link"))
    monkeypatch.setattr(venue.resolver, "_geocode_address", lambda db, a, home, area: Candidate(
        provider="address", name="", lat=34.0736, lon=-118.3775, address_text="8500 Beverly Boulevard", kind="address",
        extra={"house_match": True}))

    def fake_chat(system, user, schema, **k):
        if "official website" in system:
            return {"picks": [0], "why": "own domain"}
        return {"address": "8500 Beverly Blvd, Los Angeles", "phone": "(310) 555-0142", "opening_hours": "We,Th 18:00-22:00",
                "hours_text": "6 to 10 pm Wed-Thu", "price_tiers": [{"label": "Mini Glow", "price": 32, "note": None}],
                "is_free": None, "price_text": "Price depends on group size"}
    monkeypatch.setattr(venue, "chat_json", fake_chat)


def test_lookup_collects_site_facts(monkeypatch):
    pages = {"https://glow.example.com/": HOME_PAGE, "https://glow.example.com/contact-us/": "<p>Call (310) 555-0142</p>",
             "https://glow.example.com/faq/": "<p>FAQ</p>", "https://tickets.example.com/m/1": HOME_PAGE}
    _fake_web(monkeypatch, pages)
    hint = ItemHint(kind="place", name="Glow or Go", address="8500 Beverly Blvd", area="Los Angeles", inside="Beverly Center")
    v = venue.lookup(None, hint, (34.05, -118.24))
    assert v["website"] == "https://glow.example.com/"
    assert v["phone"] == "(310) 555-0142" and v["opening_hours"] == "We,Th 18:00-22:00"
    assert [t["label"] for t in v["price_tiers"]] == ["Mini Glow"]
    assert v["location"]["method"] == "site Google Maps link"
    assert venue.site_pin(v)[2] == "site Google Maps link"
    venue.apply(hint, v)
    assert hint.website and hint.phone and hint.images and hint.price_tiers and hint.hours_text


def test_apply_does_not_overwrite_or_leak_venue_data_into_events():
    event = ItemHint(kind="event", name="Venue", phone="111", price_min=10)
    venue.apply(event, {"phone": "222", "images": ["https://x/a.jpg"], "price_tiers": [{"label": "A", "price": 1}],
                        "website": "https://v.example.com"})
    assert event.phone == "111" and event.website == "https://v.example.com"
    assert event.images == [] and event.price_tiers == []


def test_site_pin_prefers_site_evidence_then_exact_geocode():
    v = {"location": {"evidence": [{"method": "address geocoded (exact house)", "lat": 1, "lon": 2},
                                   {"method": "site Google Maps link", "lat": 3, "lon": 4}]}}
    assert venue.site_pin(v) == (3, 4, "site Google Maps link")
    v["location"]["evidence"].pop()
    assert venue.site_pin(v)[:2] == (1, 2)
    assert venue.site_pin({"location": {"evidence": [{"method": "address geocoded (street only)", "lat": 1, "lon": 2}]}}) is None


def _resolved(lat, lon):
    cand = Candidate(provider="address", name="Glow or Go", lat=lat, lon=lon, kind="poi")
    return [(ItemHint(kind="place", name="Glow or Go"), SimpleNamespace(best=cand, method="address", confidence=0.9))]


def _run_sites(monkeypatch, resolved, site_lat, site_lon):
    monkeypatch.setattr(pipeline.store, "find_place", lambda db, cand, name: None)
    monkeypatch.setattr(pipeline.jobs, "set_stage", lambda *a, **k: None)
    monkeypatch.setattr(pipeline, "too_vague", lambda res: False)
    v = {"website": "https://glow.example.com/", "price_tiers": [], "location": {"evidence": [
        {"method": "site Google Maps link", "lat": site_lat, "lon": site_lon}]}}
    monkeypatch.setattr(pipeline.venue, "lookup", lambda db, hint, home, stage=None: v)
    pipeline._look_up_sites(None, SimpleNamespace(id=1), resolved, (34.05, -118.24), (90, 93))


def test_site_pin_moves_nearby_map_match(monkeypatch):
    resolved = _resolved(34.0736, -118.3775)
    _run_sites(monkeypatch, resolved, 34.0751, -118.3773)
    hint, res = resolved[0]
    assert (res.best.lat, res.best.lon) == (34.0751, -118.3773)
    assert res.best.extra["site_pin"] == "site Google Maps link"
    assert hint.website == "https://glow.example.com/"


def test_site_pin_far_away_is_flagged_not_used(monkeypatch):
    resolved = _resolved(34.0736, -118.3775)
    _run_sites(monkeypatch, resolved, 34.2, -118.3775)
    hint, res = resolved[0]
    assert (res.best.lat, res.best.lon) == (34.0736, -118.3775)
    assert any("website pin is" in f for f in hint.flags)


def test_price_labels_for_places():
    tiers = [{"label": "A", "price": 23}, {"label": "B", "price": 32.0}, {"label": "C", "price": None}]
    assert tiers_label(tiers) == "$23-32"
    assert tiers_label([{"label": "A", "price": 20}]) == "$20"
    assert place_price_label(None, tiers) == "$23-32"
    assert place_price_label(2, tiers) == "$$"
    assert place_price_label(None) is None


def test_other_pages_found_only_when_they_name_the_venue(monkeypatch):
    pages = {"https://blog.example.com/a": "<html><body><article><p>Sunset Ranch Hollywood runs guided trail rides every day of the week. Call (323) 469-5450 for rides and bookings.</p></article></body></html>",
             "https://blog.example.com/b": "<html><body><article><p>A page about other stables entirely, with plenty of unrelated words in it so that the reader sees real text here. Sunset Ranch Hollywood is mentioned once.</p></article></body></html>"}
    monkeypatch.setattr(venue, "fetch_text", lambda u: (u, pages[u]))
    out = {"search_results": [
        {"url": "https://ranch.example.com/", "aggregator": False},
        {"url": "https://www.yelp.com/biz/x", "aggregator": True},
        {"url": "https://blog.example.com/b", "aggregator": False},
        {"url": "https://blog.example.com/a", "aggregator": False}]}
    got = venue.other_pages(ItemHint(kind="place", name="Sunset Ranch Hollywood"), "https://ranch.example.com/", out)
    assert [p["url"] for p in got] == ["https://blog.example.com/a"]


def test_footer_text_keeps_address_the_article_extractor_drops():
    html = ("<html><body><div id='content'><p>Now playing</p></div><div id='footer_contact'>"
            "<div class='footer_col'>Location 7770 Rosecrans Avenue<br/>Paramount, CA 90723</div>"
            "<div class='footer_col'>Contact 562.630.SHOW (7469)</div></div><script>x()</script></body></html>")
    foot = venue.footer_text(html)
    assert "7770 Rosecrans Avenue Paramount, CA 90723" in foot and "562.630.SHOW" in foot
    assert "Now playing" not in foot and "x()" not in foot
    assert venue.footer_text("<html><body><p>no footer</p></body></html>") == ""
