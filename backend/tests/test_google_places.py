import httpx
import pytest

from app import google_places
from app.config import get_settings


@pytest.fixture(autouse=True)
def fresh(monkeypatch, tmp_path):
    s = get_settings()
    monkeypatch.setattr(s, "google_places_key", "k")
    monkeypatch.setattr(s, "data_dir", tmp_path)
    monkeypatch.setattr(s, "google_photo_daily_cap", 2)
    google_places._place_ids.clear()


def test_off_without_a_key(monkeypatch):
    monkeypatch.setattr(get_settings(), "google_places_key", "")
    assert google_places.photos_for("The Magic Castle 7001 Franklin Avenue") == []


def test_lookup_uses_only_free_field_masks(monkeypatch):
    seen = []

    def post(url, headers, json, timeout):
        seen.append(headers["X-Goog-FieldMask"])
        return httpx.Response(200, json={"places": [{"id": "p1"}]}, request=httpx.Request("POST", url))

    def get(url, headers, timeout):
        seen.append(headers["X-Goog-FieldMask"])
        body = {"photos": [{"name": f"places/p1/photos/{i}"} for i in range(8)]}
        body["photos"][0]["authorAttributions"] = [{"displayName": "Sam"}]
        return httpx.Response(200, json=body, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "post", post)
    monkeypatch.setattr(httpx, "get", get)
    got = google_places.photos_for("Pantages Hollywood")
    assert seen == ["places.id", "photos"]
    assert len(got) == 5 and got[0]["author"] == "Sam"
    google_places.photos_for("Pantages Hollywood")
    assert seen == ["places.id", "photos", "photos"]  # the place id is remembered, photo names are not


def test_downloads_stop_at_the_daily_cap(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda url, **kw: httpx.Response(
        200, content=b"img", headers={"content-type": "image/jpeg"}, request=httpx.Request("GET", url)))
    assert google_places.fetch_photo("places/p1/photos/a") is not None
    assert google_places.fetch_photo("places/p1/photos/a") is not None
    assert google_places.capped()
    assert google_places.fetch_photo("places/p1/photos/a") is None
    assert google_places.photos_for("anything") == []
