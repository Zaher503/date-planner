from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.ingest.event_page import address_text, opening_hours, parse_page

FIX = Path(__file__).parent / "fixtures"


def page(name: str):
    return parse_page(f"https://example.com/{name}", (FIX / f"page_{name}.html").read_text(encoding="utf-8"))


def test_eventbrite_event():
    p = page("eventbrite")
    e = p.items[0]
    assert e.kind == "event" and e.event_title == "Jazz Eclectic LA" and e.name == "Bar Lis"
    assert e.address == "1541 Wilcox Avenue, Los Angeles, CA 90028"
    assert e.starts_at.utcoffset() == timedelta(hours=-7)
    assert e.is_free is True and e.provider == "jsonld"


def test_luma_event_with_coordinates():
    e = page("luma").items[0]
    assert e.event_title == "AI Safety Meet-up Los Angeles"
    assert round(e.lat, 3) == 33.981 and e.exact_pin
    assert e.starts_at == datetime(2025, 6, 20, 1, 0, tzinfo=timezone.utc)
    assert e.ends_at - e.starts_at == timedelta(hours=2)


def test_venue_site_local_business():
    p = page("perch")
    v = p.items[0]
    assert v.kind == "place" and v.name == "Perch LA"
    assert v.address.startswith("448 South Hill Street, Los Angeles, CA, 90013")
    assert v.opening_hours.startswith("Mo 16:00-01:00; Tu 16:00-01:00")
    assert v.opening_hours.endswith("Su 10:00-01:00")


def test_group_page_lists_several_events():
    items = page("meetup").items
    assert len(items) >= 3 and all(i.kind == "event" for i in items)


def test_opening_hours_specification():
    node = {"openingHoursSpecification": [
        {"dayOfWeek": ["https://schema.org/Monday", "https://schema.org/Tuesday"], "opens": "17:00:00", "closes": "22:00:00"},
        {"dayOfWeek": "Saturday", "opens": "10:00", "closes": "23:30"}]}
    assert opening_hours(node) == "Mo,Tu 17:00-22:00; Sa 10:00-23:30"


def test_address_variants():
    assert address_text("448 S Hill St\nLos Angeles, CA") == "448 S Hill St, Los Angeles, CA"
    assert address_text({"streetAddress": "2121 E 7th Pl", "addressLocality": "Los Angeles",
                         "addressRegion": "CA", "postalCode": "90021"}) == "2121 E 7th Pl, Los Angeles, CA 90021"
    assert address_text(None) is None


def test_event_subtype_festival():
    html = ('<html><script type="application/ld+json">{"@context":"https://schema.org","@type":"Festival",'
            '"name":"Haunted Mansion","startDate":"2026-10-24T02:00:00-07:00","endDate":"2026-10-25T12:00:00-07:00",'
            '"location":{"@type":"Place","name":"Catch One","address":{"@type":"PostalAddress",'
            '"streetAddress":"4067 West Pico Boulevard, Los Angeles, CA 90019"}},'
            '"offers":[{"@type":"AggregateOffer","lowPrice":"0.0","highPrice":"65.87","priceCurrency":"USD"}]}'
            '</script></html>')
    e = parse_page("https://example.com/x", html).items[0]
    assert e.kind == "event" and e.name == "Catch One" and e.event_title == "Haunted Mansion"
    assert e.starts_at is not None and e.price_max == 65.87


def test_venue_page_lists_each_event_inside_it():
    from app.ingest.event_page import items_from_jsonld

    venue = {"@type": "Museum", "name": "Academy Museum", "address": "6067 Wilshire Blvd, Los Angeles, CA",
             "event": [{"@type": "Event", "name": "Cup Candle Making", "startDate": "2026-10-20T18:00:00-07:00"},
                       {"@type": "EducationEvent", "name": "Film Editing Workshop",
                        "startDate": "2026-10-22T10:00:00-07:00"}]}
    items = items_from_jsonld([venue], "https://example.com/events")
    assert [i.event_title for i in items] == ["Cup Candle Making", "Film Editing Workshop"]
    assert {i.name for i in items} == {"Academy Museum"}
    assert all(i.address and "Wilshire" in i.address for i in items)


def test_event_without_a_location_uses_the_page_venue():
    from app.ingest.event_page import items_from_jsonld

    nodes = [{"@type": "Museum", "name": "Academy Museum", "address": "6067 Wilshire Blvd"},
             {"@type": "Event", "name": "Vampire Day", "startDate": "2026-10-31T10:00:00-07:00"}]
    items = items_from_jsonld(nodes, "https://example.com")
    assert len(items) == 1 and items[0].name == "Academy Museum" and items[0].event_title == "Vampire Day"
