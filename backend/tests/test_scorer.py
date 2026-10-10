from app.ingest.items import ItemHint
from app.resolve.candidates import Candidate
from app.resolve.scorer import AUTO_ACCEPT, name_similarity, score

HOME = (34.0461, -118.3265)


def test_same_place_different_wording():
    assert name_similarity("Perch Rooftop Bar", "Perch") >= 0.8
    assert name_similarity("Los Ángeles Night Market", "Los Angeles Night Market") == 1.0
    assert name_similarity("TreePeople", "Tree People") == 1.0
    assert name_similarity("Blue Note Los Angeles", "Blue Note Jazz Club") >= 0.6
    assert name_similarity("The Venice West", "Venice West") >= 0.9


def test_different_places_score_low():
    assert name_similarity("Perch Rooftop Bar", "The Rooftop Bar") < 0.4
    assert name_similarity("Zaya", "Zara") <= 0.5
    assert name_similarity("Bestia", "Bestea") <= 0.5
    assert name_similarity("Melrose Trading Post", "Trading Post") < 0.75
    assert name_similarity("Graveline Tours", "Saint Martin of Tours Church") < 0.4


def cand(name, lat, lon, kind="poi", **kw):
    return Candidate(provider="photon", name=name, lat=lat, lon=lon, kind=kind, **kw)


def test_far_namesake_is_capped():
    c = score(cand("Tree People", 47.04, -122.9), ItemHint("place", "TreePeople"), HOME)
    assert c.score <= 0.45


def test_exact_local_match_auto_accepts():
    c = score(cand("Bestia", 34.0337, -118.2292, osm_value="restaurant"),
              ItemHint("place", "Bestia", category="restaurant"), HOME)
    assert c.score >= AUTO_ACCEPT


def test_vague_item_prefers_area():
    hint = ItemHint("place", "Venice", area="Venice", flags=["not a specific venue"])
    area = score(cand("Venice", 33.985, -118.469, kind="area", city="Los Angeles"), hint, HOME)
    poi = score(cand("Venice Skate Park", 33.986, -118.473), hint, HOME)
    assert area.score > poi.score


def test_house_number_match_counts_as_name():
    hint = ItemHint("place", "Zaya", address="515 W 7th St")
    c = cand("Zaya", 34.0477, -118.2565, kind="address", address_text="515 West 7th Street, Los Angeles")
    c.provider = "address"
    c.extra["house_match"] = True
    assert score(c, hint, HOME).score >= AUTO_ACCEPT
