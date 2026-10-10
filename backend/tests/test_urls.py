from app.ingest.urls import classify, first_url, normalize


def test_first_url_from_shared_text():
    text = "Check this out! https://www.tiktok.com/@foodie/video/7412345678901234567?is_from_webapp=1. so good"
    assert first_url(text) == "https://www.tiktok.com/@foodie/video/7412345678901234567?is_from_webapp=1"


def test_first_url_none():
    assert first_url("jazz night at the Blue Whale friday 8pm") is None


def test_classify():
    assert classify("https://vm.tiktok.com/ZMabc123/") == "tiktok"
    assert classify("https://youtu.be/abc") == "youtube"
    assert classify("https://maps.app.goo.gl/xyz") == "gmaps"
    assert classify("https://www.google.com/maps/place/Bestia/@34.03,-118.23,17z") == "gmaps"
    assert classify("https://maps.apple.com/?q=Bestia&ll=34.03,-118.23") == "applemaps"
    assert classify("https://www.instagram.com/reel/abc/") == "instagram"
    assert classify("https://www.eventbrite.com/e/jazz-night-tickets-123") == "event_page"
    assert classify("https://notgoogle.com/maps/x") == "event_page"


def test_normalize_tiktok_drops_query():
    a = normalize("https://tiktok.com/@foodie/video/123?is_from_webapp=1&sender_device=pc")
    b = normalize("https://www.tiktok.com/@foodie/video/123/")
    assert a == b == "https://www.tiktok.com/@foodie/video/123"


def test_normalize_strips_tracking_keeps_meaningful():
    assert normalize("https://www.eventbrite.com/e/x-123?aff=ebdssbdestsearch&utm_source=ig") == \
        "https://www.eventbrite.com/e/x-123"
    assert normalize("https://example.com/events?id=5&utm_medium=x#top") == "https://example.com/events?id=5"
    assert normalize("https://www.youtube.com/watch?v=abc&si=xyz&t=30") == "https://www.youtube.com/watch?v=abc"


def test_normalize_apple_maps_keeps_place_params():
    n = normalize("https://maps.apple.com/?q=Bestia&ll=34.0336,-118.2316&t=m")
    assert "q=Bestia" in n and "ll=34.0336" in n and "t=m" in n
