from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from geoalchemy2.shape import from_shape
from shapely.geometry import Point

from app.api.items import EventPatch, PlacePatch, apply_changes, patch_changes


def sent(model, body: dict) -> dict:
    data = model.model_validate(body)
    return {k: getattr(data, k) for k in data.model_fields_set}


def test_place_title_maps_to_name_and_point_to_geom():
    cols = patch_changes("place", sent(PlacePatch, {"title": " Perch ", "lat": 34.05, "lon": -118.25}))
    assert cols == {"name": "Perch", "geom": (34.05, -118.25)}


def test_event_title_stays_title():
    assert patch_changes("event", sent(EventPatch, {"title": "Jazz night"})) == {"title": "Jazz night"}


def test_only_sent_keys_and_explicit_nulls():
    cols = patch_changes("place", sent(PlacePatch, {"website": None, "price_level": 2, "phone": "  "}))
    assert cols == {"website": None, "price_level": 2, "phone": None}


def test_tags_cleaned():
    cols = patch_changes("place", sent(PlacePatch, {"tags": ["rooftop", " views ", "", "rooftop"]}))
    assert cols == {"tags": ["rooftop", "views"]}


@pytest.mark.parametrize("body", [{"lat": 34.0}, {"lon": -118.0}, {"title": None}, {"title": "  "},
                                  {"tags": None}, {"closed": None}, {"lat": None, "lon": None}])
def test_rejected(body):
    with pytest.raises(HTTPException) as e:
        patch_changes("place", sent(PlacePatch, body))
    assert e.value.status_code == 400


def test_models_reject_unknown_and_bad_values():
    for model, body in ((PlacePatch, {"name": "x"}), (PlacePatch, {"price_level": 5}),
                        (PlacePatch, {"review_status": "needs_review"}), (EventPatch, {"status": "done"}),
                        (EventPatch, {"price_min": -1})):
        with pytest.raises(Exception):
            model.model_validate(body)


def test_apply_changes_reports_only_real_changes():
    item = SimpleNamespace(name="Perch", website=None, price_level=2, user_overrides={},
                           geom=from_shape(Point(-118.25, 34.05), srid=4326))
    changed = apply_changes(item, {"name": "Perch", "website": "https://perchla.com", "price_level": 2,
                                   "geom": (34.0500001, -118.2500001)})
    assert changed == {"website"} and item.website == "https://perchla.com"
    changed = apply_changes(item, {"geom": (34.06, -118.25)})
    assert changed == {"geom"}


def test_event_datetimes_parse():
    cols = patch_changes("event", sent(EventPatch, {"starts_at": "2026-10-17T20:00:00-07:00", "all_day": False}))
    assert cols["starts_at"] == datetime(2026, 10, 18, 3, tzinfo=timezone.utc) and cols["all_day"] is False
