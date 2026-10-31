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


def test_zero_price_range_without_availability_is_not_free():
    from app.ingest.event_page import _offers
    dice = {"offers": {"@type": "AggregateOffer", "priceCurrency": "USD", "lowPrice": "0.00", "highPrice": "0.00"}}
    out = _offers(dice)
    assert out["is_free"] is None and out["price_min"] is None
    sold = {"offers": [{"@type": "Offer", "price": "0", "availability": "https://schema.org/SoldOut"}]}
    assert _offers(sold)["is_free"] is None
    free = {"offers": [{"@type": "AggregateOffer", "lowPrice": "0.0", "highPrice": "0.0", "availability": "InStock"}]}
    assert _offers(free)["is_free"] is True
    paid = {"offers": [{"@type": "Offer", "price": "13.65", "availability": "https://schema.org/OutOfStock"}]}
    assert _offers(paid)["price_min"] == 13.65


def test_embedded_description_leads_the_page_text():
    html = ('<html><body><nav>Create your event page for free</nav><script>{"structuredContent":{"modules":'
            '[{"type":"text","text":"\u003cp\u003eTickets start at $35/per person\u003c/p\u003e'
            '\u003cp\u003eSeating at 7:30pm\u003c/p\u003e"}]},"x":1}</script></body></html>')
    text = parse_page("https://example.com/e", html).text
    assert text.startswith("Tickets start at $35/per person\nSeating at 7:30pm")
    assert "Create your event page for free" in text


def test_embedded_description_missing_is_harmless():
    assert parse_page("https://example.com/e", "<html><body><p>Hi there</p></body></html>").text.strip() in ("", "Hi there")


def test_domain_name_from_json_ld_is_replaced_by_the_site_name():
    html = ('<html><head><meta property="og:site_name" content="Los Angeles Museum of Love">'
            '<script type="application/ld+json">{"@type":"LocalBusiness","name":"Losangelesmuseumoflove",'
            '"address":"6000 Hollywood Blvd, Los Angeles"}</script></head><body><p>Hi</p></body></html>')
    items = parse_page("https://www.losangelesmuseumoflove.com/", html).items
    assert items and items[0].name == "Los Angeles Museum of Love"
    other = html.replace("Losangelesmuseumoflove", "Some Real Name")
    assert parse_page("https://www.losangelesmuseumoflove.com/", other).items[0].name == "Some Real Name"


def test_branch_name_takes_the_full_name_from_the_page_title():
    html = ('<html><head><title>Activate Culver City | Active Games in California</title>'
            '<script type="application/ld+json">{"@type":"EntertainmentBusiness","name":"Culver City",'
            '"address":"6000 Sepulveda Blvd., Culver City, CA 90230","telephone":"310-810-3373"}</script>'
            '</head></html>')
    assert parse_page("https://playactivate.com/culver-city", html).items[0].name == "Activate Culver City"


def test_branch_name_kept_when_title_does_not_end_with_it():
    html = ('<html><head><title>Visit Culver City Today | Home</title>'
            '<script type="application/ld+json">{"@type":"EntertainmentBusiness","name":"Culver City",'
            '"address":"6000 Sepulveda Blvd., Culver City, CA 90230"}</script></head></html>')
    assert parse_page("https://x.com/a", html).items[0].name == "Culver City"
