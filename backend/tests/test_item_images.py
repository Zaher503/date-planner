from app.ingest.images import frame_times
from app.ingest.items import ItemHint
from app.ingest.page_images import attach
from app.ingest.timing import mention_time, spread, vtt_cues

VTT = """WEBVTT

00:00:01.000 --> 00:00:03.000
Here are my favorite date spots in LA

00:00:03.000 --> 00:00:06.000
Number one is <c>Bar Lis</c> in Hollywood

00:00:06.000 --> 00:00:06.500
Number one is Bar Lis in Hollywood

00:01:10.500 --> 00:01:14.000
Next up, the Griffith Observatory
at sunset
"""


def test_vtt_cues_collapse_repeats_and_parse_minutes():
    cues = vtt_cues(VTT)
    assert cues == [(1.0, "Here are my favorite date spots in LA"), (3.0, "Number one is Bar Lis in Hollywood"),
                    (70.5, "Next up, the Griffith Observatory at sunset")]


def test_mention_time_matches_names():
    cues = vtt_cues(VTT)
    assert mention_time(["Bar Lis"], cues) == 3.0
    assert mention_time(["Griffith Observatory"], cues) == 70.5
    assert mention_time(["Observatory at Griffith Park"], cues) == 70.5
    assert mention_time(["Nowhere Cafe"], cues) is None
    assert mention_time(["Bar Lis"], []) is None


def test_spread_is_even():
    assert spread(0, 4, 80) == 10 and spread(3, 4, 80) == 70


def test_frame_times_clamped_and_unique():
    assert frame_times(10, 100) == [10.0, 12.0, 14.0, 8.0, 16.0]
    assert frame_times(0.5, 3) == [0.5, 2.5, 0.0]
    assert frame_times(0, 0) == [0.0]


ARTICLE = """<html><body>
<img src="/logo.png" width="300" height="300">
<h2>1. Bar Lis</h2><p>Rooftop</p><img src="/img/barlis.jpg" width="800" height="600">
<img data-src="/img/barlis2.jpg" width="800" height="600">
<h2>2. Griffith Observatory</h2><img src="https://cdn.example.com/obs.jpg" width="800" height="600">
<h2>3. Hidden Gem</h2><p>No photo</p>
<h2>Related</h2><img src="/img/barlis.jpg" width="800" height="600">
</body></html>"""


def test_article_photos_follow_their_heading():
    hints = [ItemHint(kind="place", name="Griffith Observatory"), ItemHint(kind="place", name="Bar Lis"),
             ItemHint(kind="place", name="Hidden Gem")]
    attach(hints, ARTICLE, "https://example.com/best-dates")
    obs, bar, gem = hints
    assert obs.images == ["https://cdn.example.com/obs.jpg"]
    # barlis.jpg is repeated under "Related", so only the unique photo remains
    assert bar.images == ["https://example.com/img/barlis2.jpg"]
    assert gem.images == []
