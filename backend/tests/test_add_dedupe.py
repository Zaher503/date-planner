from app.api import add
from app.api.add import AddIn, add_item
from app.ingest.urls import identity_of, is_short_link


def test_short_link_detection():
    assert is_short_link("https://www.tiktok.com/t/ZTytUBgaK/")
    assert is_short_link("https://vm.tiktok.com/ZMabc/")
    assert is_short_link("https://maps.app.goo.gl/xyz")
    assert not is_short_link("https://www.tiktok.com/@x/video/123")
    assert not is_short_link("https://www.eventbrite.com/e/jazz-123")


def test_identity_is_the_video_id():
    a = identity_of("https://www.tiktok.com/@foodie/video/7412345678901234567?_r=1")
    b = identity_of("https://m.tiktok.com/@other/video/7412345678901234567")
    assert a == b == "tiktok:7412345678901234567"
    assert identity_of("https://www.tiktok.com/login") is None


class FakeDB:
    """Just enough Session for add_item: first() returns what the test planted."""
    def __init__(self, existing=None):
        self.existing, self.added = existing, []

    def scalars(self, _stmt):
        return self

    def first(self):
        return self.existing

    def add(self, obj):
        self.added.append(obj)

    def flush(self): ...
    def commit(self): ...
    def rollback(self): ...


class Row:
    id, kind = "11111111-1111-1111-1111-111111111111", "tiktok"


def test_two_share_codes_for_one_video_dedupe_before_queueing(monkeypatch):
    monkeypatch.setattr(add, "resolve_redirects",
                        lambda url, timeout=6: "https://www.tiktok.com/@x/video/99?share=1")
    queued = []
    monkeypatch.setattr(add.jobs, "enqueue", lambda *a, **k: queued.append(1))
    # The lookup finds the earlier source for the second code: no new source, no job
    out = add_item(FakeDB(existing=Row()), AddIn(url="https://www.tiktok.com/t/ZTytUFjaL/"), None)
    assert out.status == "exists" and not queued


def test_resolve_failure_falls_back_to_queueing(monkeypatch):
    def boom(url, timeout=6):
        raise OSError("down")
    monkeypatch.setattr(add, "resolve_redirects", boom)
    assert add.link_identity("https://www.tiktok.com/t/abc/") is None
