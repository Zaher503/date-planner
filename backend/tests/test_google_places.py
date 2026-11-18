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


def _search(monkeypatch, tmp_path, photos, existing=(), first_picture=False):
    import uuid

    from app.api import google
    from app.ingest import media
    monkeypatch.setattr(media, "media_root", lambda: tmp_path)
    db = FakeDB()
    new = google.save_search(db, "place", uuid.uuid4(), photos, list(existing), first_picture)
    return new, db


def test_every_photo_of_a_search_is_saved_in_googles_order(monkeypatch, tmp_path):
    photos = [(b"a", "image/jpeg", "Sam"), (b"b", "image/png", None), (b"c", "image/webp", "Ana")]
    new, db = _search(monkeypatch, tmp_path, photos, first_picture=True)
    assert new == 3 and db.committed
    assert [(r.kind, r.rank, r.attribution, r.source_id) for r in db.added] == [
        ("google", 0, "Sam", None), ("google", 1, None, None), ("google", 2, "Ana", None)]
    assert [(tmp_path / r.path).read_bytes() for r in db.added] == [b"a", b"b", b"c"]
    assert [r.chosen for r in db.added] == [True, False, False]  # an item with no picture gets the first


def test_a_new_search_goes_on_top_and_known_photos_are_not_saved_twice(monkeypatch, tmp_path):
    from app.db.models import ItemImage
    (tmp_path / "item-images").mkdir()
    for name, body in (("g1.jpg", b"old1"), ("g2.jpg", b"old2")):
        (tmp_path / "item-images" / name).write_bytes(body)
    old1 = ItemImage(kind="google", path="item-images/g1.jpg", rank=0, chosen=True)
    old2 = ItemImage(kind="google", path="item-images/g2.jpg", rank=1, chosen=False)
    new, db = _search(monkeypatch, tmp_path, [(b"fresh", "image/jpeg", None), (b"old2", "image/jpeg", None)],
                      existing=[old1, old2])
    assert new == 1 and len(db.added) == 1
    fresh = db.added[0]
    assert (fresh.rank, old2.rank, old1.rank) == (0, 1, 2)  # the search's photos first, in its order
    assert old1.chosen and not fresh.chosen  # the main picture stays as it was


def test_a_search_skips_files_that_are_not_pictures(monkeypatch, tmp_path):
    new, db = _search(monkeypatch, tmp_path, [(b"<html>", "text/html", None), (b"a", "image/jpeg", None)])
    assert new == 1 and db.added[0].rank == 0 and not db.added[0].chosen
