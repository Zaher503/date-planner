from datetime import datetime, timezone

from app.ingest.items import ItemHint
from app.ingest.pipeline import tidy

NOW = datetime(2026, 10, 10, tzinfo=timezone.utc)


def test_dateless_event_becomes_place():
    h = tidy(ItemHint("event", "Graveline Tours", flags=["event with no date"]), NOW)
    assert h.kind == "place" and "event with no date" not in h.flags


def test_recurring_event_kept():
    h = tidy(ItemHint("event", "Melrose Trading Post", recurrence="every Sunday"), NOW)
    assert h.kind == "event"


def test_long_running_series_is_recurring_not_dated():
    h = tidy(ItemHint("event", "Bar Lis", event_title="Jazz Eclectic LA",
                      starts_at=datetime(2021, 8, 31, tzinfo=timezone.utc),
                      ends_at=datetime(2026, 12, 30, tzinfo=timezone.utc)), NOW)
    assert h.kind == "event" and h.starts_at is None
    assert h.recurrence == "ongoing until 2026-12-30"
    assert "recurring series, dates unclear" in h.flags


def test_event_without_venue_uses_title():
    h = tidy(ItemHint("event", "", event_title="Candlelight Concert",
                      starts_at=datetime(2026, 10, 20, tzinfo=timezone.utc)), NOW)
    assert h.name == "Candlelight Concert" and "not a specific venue" in h.flags


def test_readable_handle():
    from app.ingest.pipeline import readable_handle
    assert readable_handle("nightmarket_elgato", ["nightmarketelgato", "nightmarket_elgato"]) == "Nightmarket Elgato"
    assert readable_handle("Zaya", ["nate_eatz", "zayadtla"]) == "Zaya"


def test_prune_vague_items_in_single_place_posts():
    from app.ingest.pipeline import prune
    hints = [ItemHint("place", "Downtown LA", flags=["not a specific venue"]), ItemHint("place", "Pacific Seas")]
    assert [h.name for h in prune(hints, is_list=False)] == ["Pacific Seas"]
    assert len(prune(hints, is_list=True)) == 2


def test_dateless_event_at_a_venue_stays_an_event():
    h = tidy(ItemHint("event", "Academy Museum", event_title="Cup Candle Making"), NOW)
    assert h.kind == "event" and h.event_title == "Cup Candle Making"


def test_reread_never_ties_an_event_to_a_place_named_after_it():
    from types import SimpleNamespace as NS
    from app.ingest.pipeline import _reuse

    place = NS(name="Cup Candle Making", id=1)
    hint = ItemHint("event", "Academy Museum", event_title="Cup Candle Making")
    assert _reuse(None, hint, (place, None), True) == (None, None)
    assert _reuse(None, ItemHint("place", "Cup Candle Making"), (place, None), True) == (place, None)


def test_past_event_is_flagged():
    h = tidy(ItemHint("event", "El Cid", event_title="DONUTS",
                      starts_at=datetime(2025, 11, 8, tzinfo=timezone.utc),
                      ends_at=datetime(2025, 11, 9, tzinfo=timezone.utc)), NOW)
    assert "event already happened" in h.flags


def test_upcoming_event_not_flagged():
    h = tidy(ItemHint("event", "El Cid", event_title="DONUTS",
                      starts_at=datetime(2026, 11, 8, tzinfo=timezone.utc)), NOW)
    assert "event already happened" not in h.flags


def test_dateless_offerings_on_a_home_page_become_the_venue_place():
    from app.ingest.pipeline import demote_offerings
    hints = [ItemHint("event", "Tutu Fun", event_title=t, address="10250 Santa Monica Blvd")
             for t in ("Rug Tufting", "Pouring Arts")]
    out = demote_offerings(hints, "https://tutufuncc.com/")
    assert [h.kind for h in out] == ["place"]
    assert out[0].name == "Tutu Fun" and out[0].address == "10250 Santa Monica Blvd"
    assert "Rug Tufting" in out[0].description and "Pouring Arts" in out[0].description


def test_three_dateless_events_at_one_venue_become_offerings_anywhere():
    from app.ingest.pipeline import demote_offerings
    hints = [ItemHint("event", "Lumee", event_title=f"Workshop {i}") for i in range(3)]
    assert [h.kind for h in demote_offerings(hints, "https://example.com/workshops")] == ["place"]


def test_a_single_dateless_event_on_an_inner_page_stays():
    from app.ingest.pipeline import demote_offerings
    hints = [ItemHint("event", "Academy Museum", event_title="Cup Candle Making")]
    assert demote_offerings(hints, "https://example.com/events/candle") == hints


def test_dated_and_recurring_events_are_never_demoted():
    from app.ingest.pipeline import demote_offerings
    hints = [ItemHint("event", "Museum", event_title="A", starts_at=NOW),
             ItemHint("event", "Museum", event_title="B", recurrence="every Sunday"),
             ItemHint("place", "Museum")]
    assert demote_offerings(hints, "https://museum.org/") == hints


def test_offerings_join_an_existing_place_of_the_same_name():
    from app.ingest.pipeline import demote_offerings
    place = ItemHint("place", "Aquarium of the Pacific", description="Big aquarium.")
    out = demote_offerings([place, ItemHint("event", "Aquarium of the Pacific", event_title="Jelly Dreamscapes")],
                           "https://www.aquariumofpacific.org/")
    assert out == [place] and place.description == "Big aquarium. Offers: Jelly Dreamscapes"
