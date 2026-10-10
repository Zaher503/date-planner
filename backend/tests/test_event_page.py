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
