import pytest

from app.ingest import age
from app.ingest.event_page import parse_page
from app.ingest.items import ItemHint


@pytest.mark.parametrize("text,want", [
    ("This is a 21+ event", 21),
    ("Presented by El Cid. 21 and over only.", 21),
    ("Ages 18 and up welcome", 18),
    ("Must be 21 or older with valid ID", 21),
    ("Doors 9pm | +21", 21),
    ("18+ event", 18),
    ("18 plus", 18),
    ("Age: 21", 21),
    ("18+ to enter, 21+ to drink", None),
    ("All ages show", None),
    ("All ages, 21+ bar", None),
    ("Tickets $21 each, 2 for $18", None),
    ("Open since 2018, 1821 Main St", None),
    ("Starts at 21:00", None),
    ("", None),
    (None, None),
])
def test_min_age(text, want):
    assert age.min_age(text) == want


def event(**kw):
    return ItemHint(kind="event", name="El Cid", **kw)


def test_apply_sets_the_only_event():
    h = [event()]
    age.apply(h, "A disco night.", "This is a 21+ event")
    assert h[0].min_age == 21


def test_apply_skips_listings_and_keeps_stated_age():
    two = [event(), event()]
    age.apply(two, "21+ event")
    assert [h.min_age for h in two] == [None, None]
    one = [event(min_age=18)]
    age.apply(one, "21+ event")
    assert one[0].min_age == 18
    place = [ItemHint(kind="place", name="Bar")]
    age.apply(place, "21+")
    assert place[0].min_age is None


def test_jsonld_typical_age_range():
    html = ('<html><script type="application/ld+json">{"@context":"https://schema.org","@type":"Event",'
            '"name":"Late Show","startDate":"2026-11-08T21:00:00-08:00","typicalAgeRange":"21+",'
            '"location":{"@type":"Place","name":"El Cid","address":"4212 Sunset Blvd, Los Angeles, CA"}}</script></html>')
    assert parse_page("https://example.com/e", html).items[0].min_age == 21
