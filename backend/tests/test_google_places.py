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


class FakeDB:
    def __init__(self, existing=None):
        self.existing, self.added, self.committed = existing, [], False

    def scalars(self, _):
        return self

    def first(self):
        return self.existing

    def add(self, row):
        self.added.append(row)

    def commit(self):
        self.committed = True


def test_first_google_photo_is_kept_as_the_hero(monkeypatch, tmp_path):
    from app.api import google
    from app.ingest import media
    monkeypatch.setattr(media, "media_root", lambda: tmp_path)
    import uuid
    db = FakeDB()
    assert google.save_hero(db, "place", uuid.uuid4(), b"img", "image/jpeg", "Sam")
    row = db.added[0]
    assert row.kind == "google" and row.chosen and row.attribution == "Sam" and row.source_id is None
    assert (tmp_path / row.path).read_bytes() == b"img" and db.committed


def test_hero_is_not_saved_when_the_item_has_a_picture_or_the_switch_is_off(monkeypatch, tmp_path):
    from app.api import google
    from app.ingest import media
    import uuid
    monkeypatch.setattr(media, "media_root", lambda: tmp_path)
    busy = FakeDB(existing=1)
    assert not google.save_hero(busy, "place", uuid.uuid4(), b"img", "image/jpeg", None) and not busy.added
    monkeypatch.setattr(get_settings(), "google_save_hero", False)
    assert not google.save_hero(FakeDB(), "place", uuid.uuid4(), b"img", "image/jpeg", None)


def test_a_dead_picture_link_is_no_picture():
    import httpx as hx

    from app.api.common import image_url
    from app.api.media import NotImage, gone
    from app.db.models import Source

    raw = {"page": {"image": "http://x.test/logo.png"}}
    assert image_url(raw) == "http://x.test/logo.png"
    assert image_url({**raw, "image_dead": True}) is None
    page = Source(kind="event_page", raw=raw)
    not_found = hx.HTTPStatusError("x", request=hx.Request("GET", "http://x.test"), response=hx.Response(404))
    assert gone(page, not_found) and gone(page, NotImage("html"))
    assert not gone(page, hx.ReadTimeout("slow")) and not gone(Source(kind="tiktok", raw=raw), not_found)


def test_a_picked_google_photo_replaces_the_hero(monkeypatch, tmp_path):
    import uuid

    from app.api import google
    from app.db.models import ItemImage
    from app.ingest import media
    monkeypatch.setattr(media, "media_root", lambda: tmp_path)
    old_file = tmp_path / "item-images" / "google-old.jpg"
    old_file.parent.mkdir(parents=True)
    old_file.write_bytes(b"old")
    old_google = ItemImage(kind="google", path="item-images/google-old.jpg", chosen=True)
    page = ItemImage(kind="page", url="http://x.test/a.jpg", chosen=False)
    other = ItemImage(kind="page", url="http://x.test/b.jpg", chosen=True)

    class DB(FakeDB):
        deleted = []

        def all(self):
            return [old_google, page, other]

        def delete(self, row):
            self.deleted.append(row)

    db = DB(existing=1)
    assert google.save_hero(db, "place", uuid.uuid4(), b"new", "image/jpeg", "Sam", replace=True)
    assert db.deleted == [old_google] and not old_file.exists()
    assert other.chosen is False and db.added[0].chosen and db.added[0].attribution == "Sam"
