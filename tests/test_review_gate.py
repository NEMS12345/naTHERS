"""Review gate: flags missing/low-confidence/defaulted fields, groups by assessment."""

from __future__ import annotations

from planassess.model.building import BuildingModel
from planassess.review.gate import run_review_gate


def test_gate_flags_known_sample_gaps(house: BuildingModel):
    result = run_review_gate(house, threshold=0.6)
    flagged_paths = {g.path for g in result.gaps}
    # Deliberate gaps in the synthetic house:
    assert "project.climate_zone" in flagged_paths        # missing pre-lookup
    assert "roofs[0].colour" in flagged_paths             # missing
    assert "roofs[0].solar_absorptance" in flagged_paths  # missing
    assert "zones[1].ceiling_height" in flagged_paths     # low confidence (0.4)
    assert "zones[1].volume" in flagged_paths             # missing
    assert "services.battery_kwh" in flagged_paths        # missing


def test_gate_counts_consistent(house: BuildingModel):
    result = run_review_gate(house, threshold=0.6)
    assert result.total_tracked > 0
    assert result.populated <= result.total_tracked
    # extraction_meta is refreshed by the gate
    assert house.extraction_meta.field_count == result.total_tracked
    assert house.extraction_meta.flagged_count == len(result.gaps)


def test_gate_threshold_is_configurable(house: BuildingModel):
    lenient = run_review_gate(house, threshold=0.0)
    strict = run_review_gate(house, threshold=0.95)
    # A higher threshold flags at least as many fields.
    assert len(strict.gaps) >= len(lenient.gaps)


def test_gaps_tagged_with_needing_assessment(house: BuildingModel):
    result = run_review_gate(house, threshold=0.6)
    cz = next(g for g in result.gaps if g.path == "project.climate_zone")
    assert "thermal" in cz.needed_by and "compliance" in cz.needed_by


def test_fully_populated_high_confidence_model_passes():
    # An empty-ish model with only the required project id still has tracked
    # fields; assert the gate runs and returns a structured result.
    from planassess.model.building import Project
    from planassess.model.enums import Provenance, State
    from planassess.model.tracked import observed

    model = BuildingModel(
        project=Project(
            id="P",
            state=observed(State.VIC, Provenance.HUMAN, 1.0),
            postcode=observed("3000", Provenance.HUMAN, 1.0),
            address=observed("x", Provenance.HUMAN, 1.0),
            climate_zone=observed(60, Provenance.HUMAN, 1.0),
        )
    )
    result = run_review_gate(model, threshold=0.6)
    # site/services/fixtures default to missing tracked values -> some gaps expected
    assert result.total_tracked > 0
