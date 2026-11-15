from app.ingest import free, links, names

PAGE = """
<a href="/tickets?a=1&amp;b=2#top"><span>Buy</span> Tickets &amp; more</a>
<a href="#only-fragment">skip</a>
<a href="/img/photo.JPG">image</a>
<a href="/menu.pdf?x=1">file</a>
<a href="mailto:a@b.com">mail</a>
<a href="tel:123">phone</a>
<a href="javascript:void(0)">js</a>
<a href="ftp://example.com/x">ftp</a>
<a href="https://other.com/page">Other</a>
"""


def test_anchors_skip_and_clean():
    got = list(links.anchors(PAGE, "https://www.example.com/home"))
    assert got == [("https://www.example.com/tickets?a=1&b=2", "Buy  Tickets & more"),
                   ("https://other.com/page", "Other")]


def test_anchors_without_unescape_keeps_entities():
    got = list(links.anchors(PAGE, "https://www.example.com/home", unescape=False))
    assert got[0] == ("https://www.example.com/tickets?a=1&amp;b=2", "Buy  Tickets &amp; more")


def test_same_site():
    assert links.same_site("https://www.a.com/x", "https://a.com/")
    assert links.same_site("https://shop.a.com/", "https://a.com/")
    assert not links.same_site("https://a.com/", "https://b.com/")


def test_names_words_and_tokens():
    assert names.words("The Roxy, 2nd St!") == ["the", "roxy", "2nd", "st"]
    assert names.tokens("The Bar and Grill of LA") == ["bar", "grill"]
    assert names.squash("A-b c_9") == "abc9"


def test_names_mentions_and_host():
    assert names.mentions("Welcome to The Academy-Museum!", "Academy Museum")
    assert not names.mentions("Welcome", "Academy Museum")
    assert not names.mentions("anything", "A of")
    assert names.host_label("https://www.My-Site.com/x") == "mysite"
    assert names.host_label("not a url") == ""


def test_names_domain_matches_and_is_host_name():
    assert names.domain_matches("https://www.academymuseum.org/", "Academy Museum of Motion Pictures")
    assert not names.domain_matches("https://roxy.com/", "The Roxy")  # label under 5 letters
    assert names.is_host_name("Losangelesmuseumoflove", "https://losangelesmuseumoflove.com/")
    assert not names.is_host_name("Los Angeles Museum", "https://losangelesmuseum.com/")
    assert not names.is_host_name(None, "https://x.com/")


def test_jsonld_is_free():
    assert free.jsonld_is_free(True, [10.0]) is True
    assert free.jsonld_is_free("true", []) is True
    assert free.jsonld_is_free(None, [0.0, 0.0]) is True
    assert free.jsonld_is_free(None, [0.0, 5.0]) is False
    assert free.jsonld_is_free(False, []) is None


def test_hint_is_free():
    assert free.hint_is_free(True, None, None, "Free entry") is True
    assert free.hint_is_free(True, None, None, "Entry is on us") is None
    assert free.hint_is_free(True, 5.0, 10.0, "Kids free, adults $10") is None
    assert free.hint_is_free(False, None, None, "no prices here") is None
    assert free.hint_is_free(False, None, None, "costs $20") is False
    assert free.hint_is_free(False, 20.0, None, "text") is False


def test_page_price_free():
    out = {"price_min": 0.0, "price_max": 0.0, "is_free": True, "price_text": "free donuts"}
    free.page_price_free(out, "Free donuts for all guests")
    assert out == {"price_min": None, "price_max": None, "is_free": None, "price_text": None}
    out = {"price_min": None, "price_max": None, "is_free": True, "price_text": "x"}
    assert free.page_price_free(out, "Free entry")["is_free"] is True
    out = {"price_min": 5.0, "price_max": 5.0, "is_free": True, "price_text": "x"}
    assert free.page_price_free(out, "Free entry, $5 parking")["is_free"] is None
    assert out["price_min"] == 5.0


def test_site_is_free():
    assert free.site_is_free(True, "No cover before 9") is True
    assert free.site_is_free(True, "Tickets $20") is None
    assert free.site_is_free(False, "free") is None
    assert free.site_is_free(None, "free") is None
