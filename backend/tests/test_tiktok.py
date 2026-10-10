from pathlib import Path

import pytest

from app.ingest.tiktok import build_post, parse_item, poi_of, vtt_to_text

FIX = Path(__file__).parent / "fixtures"


def load(name: str):
    html = (FIX / f"tiktok_{name}.html").read_text(encoding="utf-8")
    return build_post(f"https://www.tiktok.com/@x/video/{name}", parse_item(html))


def test_single_place_caption_and_stickers():
    p = load("perch")
    assert p.caption.startswith("Perch Rooftop Bar")
    assert any("Perch rooftop bar" in s for s in p.stickers)
    assert p.poi is None  # tagged only as the city "Los Angeles"
    assert "rooftop" in p.hashtags
    assert p.author == "briancatalann"
    assert p.duration_s == 17
    assert p.caption_url is None


def test_address_in_caption_and_mentions():
    p = load("zaya")
    assert "515 W 7th St" in p.caption
    assert "zayadtla" in p.mentions
    assert any("zaya" in s.lower() for s in p.suggested)
    assert p.caption_url


def test_list_video_stickers_and_transcript():
    p = load("dateideas")
    joined = "\n".join(p.stickers)
    assert "1. Melrose Trading Post" in joined and "10. El Matador Beach" in joined
    text = vtt_to_text((FIX / "tiktok_dateideas.vtt").read_text(encoding="utf-8"))
    assert "Melrose Trading Post which happens every Sunday" in text
    assert "-->" not in text and "WEBVTT" not in text
    p.transcript = text
    out = p.as_text()
    assert out.startswith("Caption: 10 Unique date ideas") and "Spoken (auto-captions):" in out


def test_specific_poi_kept():
    item = {"poi": {"name": "Perch", "address": "448 S Hill St, Los Angeles", "ttTypeNameTiny": "Bar",
                    "ttTypeNameMedium": "Food and drink", "id": "1"}}
    assert poi_of(item)["name"] == "Perch"


def test_unavailable_page():
    with pytest.raises(ValueError):
        parse_item("<html>blocked</html>")
