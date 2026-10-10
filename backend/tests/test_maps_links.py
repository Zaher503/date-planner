from app.ingest.maps_links import parse

G_PLACE = ("https://www.google.com/maps/place/Bestia/@34.0336,-118.2316,17z/data=!3m1!4b1!4m6!3m5"
           "!1s0x80c2c62c1ad3b0d5:0x8e0f1f2f3a4b5c6d!8m2!3d34.0337058!4d-118.2292076!16s%2Fg%2F11b6")


def test_google_place_prefers_pin_over_viewport():
    h = parse(G_PLACE)
    assert h.name == "Bestia"
    assert (h.lat, h.lon) == (34.0337058, -118.2292076)
    assert h.exact_pin


def test_google_place_name_with_plus_and_address():
    h = parse("https://www.google.com/maps/place/Bestia,+2121+E+7th+Pl,+Los+Angeles,+CA+90021/@34.03,-118.23,17z")
    assert h.name == "Bestia"
    assert h.address == "2121 E 7th Pl, Los Angeles, CA 90021"
    assert not h.exact_pin and h.lat == 34.03


def test_google_q_param_and_ftid():
    h = parse("https://maps.google.com/?q=Perch,+448+S+Hill+St,+Los+Angeles,+CA&ftid=0x80c2c7:0x1")
    assert (h.name, h.address) == ("Perch", "448 S Hill St, Los Angeles, CA")


def test_google_search_api():
    h = parse("https://www.google.com/maps/search/?api=1&query=Griffith+Observatory")
    assert h.name == "Griffith Observatory" and h.lat is None


def test_google_coordinates_only():
    h = parse("https://www.google.com/maps?q=34.1184,-118.3004")
    assert h.name is None and (h.lat, h.lon) == (34.1184, -118.3004) and h.exact_pin


def test_apple_place_link():
    h = parse("https://maps.apple.com/place?address=2121%20E%207th%20Pl,%20Los%20Angeles,%20CA%2090021"
              "&coordinate=34.0337,-118.2292&name=Bestia&place-id=I123")
    assert h.name == "Bestia"
    assert h.address.startswith("2121 E 7th Pl")
    assert (h.lat, h.lon) == (34.0337, -118.2292) and h.exact_pin


def test_apple_q_ll():
    h = parse("https://maps.apple.com/?q=Perch&ll=34.0489,-118.2513&t=m")
    assert h.name == "Perch" and h.lat == 34.0489 and h.usable
