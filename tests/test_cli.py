"""CLI smoke tests via typer's CliRunner."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from planassess.cli import app

runner = CliRunner()


def test_version():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "PlanAssess" in result.stdout


def test_demo_runs_end_to_end(tmp_path: Path):
    result = runner.invoke(app, ["demo", "--state", "NSW", "--postcode", "2000", "--out", str(tmp_path)])
    assert result.exit_code == 0, result.stdout
    assert (tmp_path / "building_model.json").exists()
    assert (tmp_path / "assessment_report.md").exists()
    assert (tmp_path / "gap_report.md").exists()
    assert "basix" in result.stdout.lower()


def test_assess_pending_adapter_is_reported_not_guessed(tmp_path: Path):
    dummy = tmp_path / "plan.dxf"
    dummy.write_text("not a real dxf")
    result = runner.invoke(app, ["assess", str(dummy), "--state", "NSW"])
    # DXF adapter is P1 -> must report clearly, not guess.
    assert result.exit_code == 3
    assert "P1" in result.output


def test_assess_accepts_building_model_json(tmp_path: Path):
    # First produce a model json via demo, then feed it back to assess.
    runner.invoke(app, ["demo", "--state", "VIC", "--postcode", "3000", "--out", str(tmp_path)])
    model_json = tmp_path / "building_model.json"
    assert model_json.exists()
    out2 = tmp_path / "out2"
    result = runner.invoke(app, ["assess", str(model_json), "--state", "VIC", "--out", str(out2)])
    assert result.exit_code == 0, result.output
    assert (out2 / "assessment_report.md").exists()
