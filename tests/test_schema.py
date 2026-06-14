"""Schema: TrackedValue semantics, round-trip, relational links, JSON schema export."""

from __future__ import annotations

from planassess.model.building import BuildingModel
from planassess.model.enums import Provenance, State
from planassess.model.tracked import TrackedValue, missing, observed


def test_tracked_value_missing_is_explicit():
    tv = missing(unit="m2", notes="not annotated")
    assert tv.is_missing
    assert tv.value is None
    assert tv.confidence == 0.0
    assert tv.source == Provenance.UNKNOWN
    assert tv.below(0.6)


def test_tracked_value_below_threshold_logic():
    high = observed(5.0, Provenance.SCHEDULE, 0.9, unit="m2")
    low = observed(5.0, Provenance.OCR, 0.4, unit="m2")
    default = TrackedValue(value=7.0, source=Provenance.CONFIG_DEFAULT, confidence=1.0)
    assert not high.below(0.6)
    assert low.below(0.6)
    # config defaults are NEVER silently accepted, even at confidence 1.0
    assert default.below(0.6)


def test_confidence_bounds_enforced():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        TrackedValue(value=1.0, source=Provenance.OCR, confidence=1.5)


def test_round_trip_json(house: BuildingModel):
    dumped = house.model_dump_json()
    restored = BuildingModel.model_validate_json(dumped)
    assert restored == house


def test_relational_links_present(house: BuildingModel):
    # zones link to a dwelling; walls/glazing link to zones/walls.
    dwelling_ids = {d.id for d in house.dwellings}
    assert all(z.dwelling_id in dwelling_ids for z in house.zones)
    zone_ids = {z.id for z in house.zones}
    assert all(w.zone_id in zone_ids for w in house.walls)
    wall_ids = {w.id for w in house.walls}
    for g in house.glazing:
        assert g.zone_id in zone_ids
        assert g.wall_id in wall_ids


def test_json_schema_exports():
    schema = BuildingModel.model_json_schema()
    assert schema["title"] == "BuildingModel"
    assert "project" in schema["properties"]


def test_state_enum_covers_all_territories():
    assert {s.value for s in State} == {"NSW", "VIC", "QLD", "SA", "WA", "TAS", "NT", "ACT"}
