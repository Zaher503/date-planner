import httpx

from app import google_places
from app.config import get_settings


def test_off_without_a_key(monkeypatch):
    monkeypatch.setattr(get_settings(), "google_places_key", "")
    assert google_places.photos_for("The Magic Castle 7001 Franklin Avenue") == []


def test_photos_come_from_the_first_match(monkeypatch):
    monkeypatch.setattr(get_settings(), "google_places_key", "k")
    google_places._names.clear()
    calls = []

    def fake_post(url, headers, json, timeout):
        calls.append(json["textQuery"])
        body = {"places": [{"id": "p1", "photos": [{"name": "places/p1/photos/a", "authorAttributions": [{"displayName": "Sam"}]},
                                                  {"name": "places/p1/photos/b"}]}]}
        return httpx.Response(200, json=body, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    got = google_places.photos_for("Pantages Hollywood")
    assert [p["name"] for p in got] == ["places/p1/photos/a", "places/p1/photos/b"]
    assert got[0]["author"] == "Sam" and got[1]["author"] is None
    google_places.photos_for("Pantages Hollywood")
    assert len(calls) == 1  # the second look-up is remembered
