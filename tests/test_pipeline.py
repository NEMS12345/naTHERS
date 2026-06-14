"""End-to-end pipeline: extract -> review -> assess -> report, plus disclaimers."""

from __future__ import annotations

from pathlib import Path

import pytest

from planassess.constants import INDICATIVE_THERMAL_CAVEAT, NOT_A_CERTIFICATE_CAVEAT
from planassess.model.enums import JurisdictionStrategy, State
from planassess.pipeline import run_pipeline
from planassess.samples import synthetic_house


def test_pipeline_nsw_selects_basix_and_writes_outputs(tmp_path: Path, config_dir: Path):
    model = synthetic_house(postcode="2000")
    review, compliance, written = run_pipeline(model, State.NSW, tmp_path, config_dir)

    assert compliance.strategy == JurisdictionStrategy.BASIX
    names = {p.name for p in written}
    assert names == {"building_model.json", "assessment_report.md", "gap_report.md"}
    for p in written:
        assert p.exists()


def test_pipeline_resolves_climate_zone_from_postcode(tmp_path: Path, config_dir: Path):
    model = synthetic_house(postcode="2000")
    assert model.project.climate_zone.is_missing  # missing before pipeline
    run_pipeline(model, State.NSW, tmp_path, config_dir)
    assert model.project.climate_zone.value == 56  # filled via lookup, with confidence


def test_pipeline_vic_selects_woh(tmp_path: Path, config_dir: Path):
    model = synthetic_house(postcode="3000")
    _, compliance, _ = run_pipeline(model, State.VIC, tmp_path, config_dir)
    assert compliance.strategy == JurisdictionStrategy.WOH
    assert compliance.mandatory is True


def test_pipeline_nt_marks_woh_not_required(tmp_path: Path, config_dir: Path):
    model = synthetic_house(postcode="0800")
    _, compliance, _ = run_pipeline(model, State.NT, tmp_path, config_dir)
    assert compliance.strategy == JurisdictionStrategy.WOH
    assert compliance.mandatory is False
    assert "not required" in compliance.summary.lower()


def test_reports_carry_mandatory_disclaimers(tmp_path: Path, config_dir: Path):
    model = synthetic_house(postcode="2000")
    run_pipeline(model, State.NSW, tmp_path, config_dir)
    report = (tmp_path / "assessment_report.md").read_text(encoding="utf-8")
    assert NOT_A_CERTIFICATE_CAVEAT in report
    assert INDICATIVE_THERMAL_CAVEAT in report
    assert "NOT A CERTIFICATE" in report


def test_building_model_json_preserves_confidence_and_source(tmp_path: Path, config_dir: Path):
    model = synthetic_house(postcode="2000")
    run_pipeline(model, State.NSW, tmp_path, config_dir)
    import json

    data = json.loads((tmp_path / "building_model.json").read_text(encoding="utf-8"))
    pv = data["services"]["solar_pv_kw"]
    assert pv["value"] == 6.6
    assert pv["confidence"] == 0.8
    assert pv["source"] == "dxf_text"
