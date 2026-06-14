"""End-to-end pipeline: extract -> review -> assess -> report, plus disclaimers."""

from __future__ import annotations

from pathlib import Path

from planassess.constants import INDICATIVE_THERMAL_CAVEAT, NOT_A_CERTIFICATE_CAVEAT
from planassess.model.enums import JurisdictionStrategy, State
from planassess.pipeline import run_pipeline
from planassess.samples import synthetic_house


def test_pipeline_nsw_selects_basix_and_writes_outputs(tmp_path: Path, config_dir: Path):
    model = synthetic_house(postcode="2000")
    out = run_pipeline(model, State.NSW, tmp_path, config_dir)

    assert out.compliance.strategy == JurisdictionStrategy.BASIX
    names = {p.name for p in out.written}
    # The PDF is optional (depends on reportlab); the rest are always produced.
    assert {
        "building_model.json",
        "assessment_report.md",
        "gap_report.md",
        "input_pack.md",
        "input_pack.csv",
    } <= names
    assert names <= {
        "building_model.json",
        "assessment_report.md",
        "assessment_report.pdf",
        "gap_report.md",
        "input_pack.md",
        "input_pack.csv",
    }
    for p in out.written:
        assert p.exists()


def test_pipeline_resolves_climate_zone_from_postcode(tmp_path: Path, config_dir: Path):
    model = synthetic_house(postcode="2000")
    assert model.project.climate_zone.is_missing
    run_pipeline(model, State.NSW, tmp_path, config_dir)
    assert model.project.climate_zone.value == 56


def test_pipeline_vic_selects_woh(tmp_path: Path, config_dir: Path):
    model = synthetic_house(postcode="3000")
    out = run_pipeline(model, State.VIC, tmp_path, config_dir)
    assert out.compliance.strategy == JurisdictionStrategy.WOH
    assert out.compliance.mandatory is True
    assert len(out.compliance.categories) == 1  # the WoH score category


def test_pipeline_nt_marks_woh_not_required(tmp_path: Path, config_dir: Path):
    model = synthetic_house(postcode="0800")
    out = run_pipeline(model, State.NT, tmp_path, config_dir)
    assert out.compliance.strategy == JurisdictionStrategy.WOH
    assert out.compliance.mandatory is False
    assert "not required" in out.compliance.summary.lower()
    assert out.compliance.categories == []  # nothing to score when not mandatory


def test_pipeline_thermal_is_indicative_and_computed(tmp_path: Path, config_dir: Path):
    model = synthetic_house(postcode="2000")
    out = run_pipeline(model, State.NSW, tmp_path, config_dir)
    assert out.thermal.indicative is True
    assert out.thermal.computed is True
    assert out.thermal.total_load_mj_per_m2 is not None
    assert out.thermal.indicative_star is not None
    assert "INDICATIVE" in out.thermal.caveat.upper()


def test_reports_carry_mandatory_disclaimers(tmp_path: Path, config_dir: Path):
    model = synthetic_house(postcode="2000")
    run_pipeline(model, State.NSW, tmp_path, config_dir)
    report = (tmp_path / "assessment_report.md").read_text(encoding="utf-8")
    assert NOT_A_CERTIFICATE_CAVEAT in report
    assert INDICATIVE_THERMAL_CAVEAT in report
    assert "NOT A CERTIFICATE" in report
    pack = (tmp_path / "input_pack.md").read_text(encoding="utf-8")
    assert NOT_A_CERTIFICATE_CAVEAT in pack


def test_input_pack_csv_has_nathers_and_basix_targets(tmp_path: Path, config_dir: Path):
    model = synthetic_house(postcode="2000")
    run_pipeline(model, State.NSW, tmp_path, config_dir)
    csv_text = (tmp_path / "input_pack.csv").read_text(encoding="utf-8")
    assert "NatHERS" in csv_text  # always present
    assert "BASIX" in csv_text  # NSW path
    # Missing fields are flagged for action, not silently blank.
    assert "PROVIDE" in csv_text


def test_input_pack_woh_for_non_nsw(tmp_path: Path, config_dir: Path):
    model = synthetic_house(postcode="3000")
    run_pipeline(model, State.VIC, tmp_path, config_dir)
    csv_text = (tmp_path / "input_pack.csv").read_text(encoding="utf-8")
    assert "WoH" in csv_text
    assert "BASIX" not in csv_text


def test_assessment_pdf_written_when_reportlab_available(tmp_path: Path, config_dir: Path):
    pytest_importorskip = __import__("pytest").importorskip
    pytest_importorskip("reportlab")
    model = synthetic_house(postcode="2000")
    out = run_pipeline(model, State.NSW, tmp_path, config_dir)
    pdf = tmp_path / "assessment_report.pdf"
    assert pdf.exists()
    assert pdf in out.written
    assert pdf.read_bytes().startswith(b"%PDF")  # valid PDF magic


def test_building_model_json_preserves_confidence_and_source(tmp_path: Path, config_dir: Path):
    model = synthetic_house(postcode="2000")
    run_pipeline(model, State.NSW, tmp_path, config_dir)
    import json

    data = json.loads((tmp_path / "building_model.json").read_text(encoding="utf-8"))
    pv = data["services"]["solar_pv_kw"]
    assert pv["value"] == 6.6
    assert pv["confidence"] == 0.8
    assert pv["source"] == "dxf_text"
