"""Referential-integrity checks for the Building Model."""

from __future__ import annotations

from planassess.model.validation import check_integrity
from planassess.samples import synthetic_house


def test_synthetic_house_is_sound():
    assert check_integrity(synthetic_house()) == []


def test_dangling_zone_reference_detected():
    model = synthetic_house()
    model.walls[0].zone_id = "ZX"  # no such zone
    issues = check_integrity(model)
    assert any("references missing id 'ZX'" in i for i in issues)


def test_dangling_wall_reference_on_glazing():
    model = synthetic_house()
    model.glazing[0].wall_id = "WX"
    issues = check_integrity(model)
    assert any("glazing" in i and "WX" in i for i in issues)


def test_duplicate_ids_detected():
    model = synthetic_house()
    model.zones[1].id = model.zones[0].id  # duplicate zone id
    issues = check_integrity(model)
    assert any("duplicate zone id" in i for i in issues)


def test_none_references_are_allowed():
    model = synthetic_house()
    model.walls[0].zone_id = None  # unlinked is permitted, not an error
    assert all("references missing" not in i for i in check_integrity(model))
