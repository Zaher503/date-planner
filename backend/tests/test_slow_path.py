"""Slow path helpers: when to use it, frame spacing, text clean-up, upload sniffing."""
from types import SimpleNamespace

from app.api.add import sniff_image
from app.ingest.items import ItemHint
from app.ingest.ocr import dedupe_lines, frame_interval
from app.ingest.pipeline import strength, weak, youtube_text
from app.ingest.transcribe import clean_segments


def res(conf: float, review: bool, kind: str = "poi", osm_value: str = "restaurant"):
    best = SimpleNamespace(kind=kind, osm_value=osm_value)
    return SimpleNamespace(best=best, confidence=conf, needs_review=review)


H = ItemHint(kind="place", name="x")


def test_weak_when_nothing_confident():
    assert weak([])
    assert weak([(H, res(0.5, True))])
    assert weak([(H, SimpleNamespace(best=None, confidence=0, needs_review=True))])
    # A whole-city pin does not count as placed
    assert weak([(H, res(0.95, False, kind="area", osm_value="city"))])
    assert not weak([(H, res(0.5, True)), (H, res(0.9, False))])


def test_strength_prefers_more_confident_pins():
    one = [(H, res(0.9, False))]
    two_unsure = [(H, res(0.6, True)), (H, res(0.6, True))]
    assert strength(one) > strength(two_unsure)
    assert strength([(H, res(0.9, False)), (H, res(0.8, False))]) > strength(one)


def test_frames_spread_over_long_videos():
    assert frame_interval(30) == 2.0
    assert frame_interval(0) == 2.0
    assert frame_interval(120) == 6.0


def test_dedupe_lines_ignores_case_and_punctuation():
    out = dedupe_lines(["Perch\n448 S Hill St", "PERCH!", "448 s hill st", "", "Sat 8pm"])
    assert out.splitlines() == ["Perch", "448 S Hill St", "Sat 8pm"]


def test_whisper_junk_is_dropped():
    seg = lambda t, nsp=0.1, lp=-0.3: SimpleNamespace(text=t, no_speech_prob=nsp, avg_logprob=lp)
    text = clean_segments([seg(" We went to Perch "), seg("Thanks for watching!"), seg("hmm", nsp=0.9),
                           seg("garbled", lp=-1.5), seg("Get the burrata.")])
    assert text == "We went to Perch Get the burrata."


def test_youtube_text_labels_parts():
    t = youtube_text({"title": "LA date ideas", "description": "1. Perch", "uploader": "someone"}, "we love it")
    assert t.startswith("Title: LA date ideas")
    assert "Description: 1. Perch" in t and "Channel: someone" in t and "Spoken (captions):\nwe love it" in t


def test_sniff_image():
    assert sniff_image(b"\x89PNG\r\n\x1a\n" + b"0" * 8) == "image/png"
    assert sniff_image(b"\xff\xd8\xff\xe0" + b"0" * 12) == "image/jpeg"
    assert sniff_image(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "image/webp"
    assert sniff_image(b"<svg xmlns=") is None
