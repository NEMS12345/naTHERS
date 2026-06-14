"""Human-in-the-loop review I/O: template export + typed answer merge."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from planassess.model.enums import Orientation, Provenance, ZoneType
from planassess.review.gate import run_review_gate
from planassess.review.review_io import (
    apply_review,
    export_review_template,
    set_at_path,
)
from planassess.samples import synthetic_house


def test_export_template_lists_flagged_paths(tmp_path: Path):
    model = synthetic_house()
    review = run_review_gate(model, threshold=0.6)
    path = export_review_template(review, tmp_path)
    rows = list(csv.DictReader(path.open()))
    paths = {r["path"] for r in rows}
    assert "roofs[0].colour" in paths
    assert "your_value" in rows[0]  # empty column for the human to fill


def test_set_at_path_coerces_types():
    model = synthetic_house()
    set_at_path(model, "walls[0].r_value", "2.8")        # float
    set_at_path(model, "walls[0].orientation", "E")      # enum
    set_at_path(model, "project.climate_zone", "56")     # int
    set_at_path(model, "zones[0].type", "night")         # enum by value

    assert model.walls[0].r_value.value == 2.8
    assert isinstance(model.walls[0].r_value.value, float)
    assert model.walls[0].orientation.value == Orientation.E
    assert model.project.climate_zone.value == 56
    assert isinstance(model.project.climate_zone.value, int)
    assert model.zones[0].type.value == ZoneType.NIGHT


def test_applied_values_are_human_full_confidence():
    model = synthetic_house()
    set_at_path(model, "walls[0].r_value", "3.1")
    tv = model.walls[0].r_value
    assert tv.source == Provenance.HUMAN
    assert tv.confidence == 1.0
    assert tv.unit == "m2.K/W"  # original unit preserved


def test_apply_review_reduces_gaps(tmp_path: Path):
    model = synthetic_house()
    before = len(run_review_gate(model, 0.6).gaps)

    answers = tmp_path / "answers.csv"
    with answers.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["path", "your_value"])
        w.writeheader()
        w.writerow({"path": "roofs[0].colour", "your_value": "Light grey"})
        w.writerow({"path": "roofs[0].solar_absorptance", "your_value": "0.45"})
        w.writerow({"path": "zones[1].ceiling_height", "your_value": "2.7"})

    applied, errors = apply_review(model, answers)
    assert set(applied) == {
        "roofs[0].colour", "roofs[0].solar_absorptance", "zones[1].ceiling_height"
    }
    assert errors == []
    after = len(run_review_gate(model, 0.6).gaps)
    assert after == before - 3


def test_apply_review_reports_bad_paths(tmp_path: Path):
    model = synthetic_house()
    answers = tmp_path / "answers.csv"
    with answers.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["path", "your_value"])
        w.writeheader()
        w.writerow({"path": "walls[99].r_value", "your_value": "2.8"})   # bad index
        w.writerow({"path": "not.a.field", "your_value": "x"})           # bad path
    applied, errors = apply_review(model, answers)
    assert applied == []
    assert {e.path for e in errors} == {"walls[99].r_value", "not.a.field"}


def test_empty_answers_are_ignored(tmp_path: Path):
    model = synthetic_house()
    answers = tmp_path / "answers.csv"
    with answers.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["path", "your_value"])
        w.writeheader()
        w.writerow({"path": "roofs[0].colour", "your_value": ""})  # blank -> skip
    applied, errors = apply_review(model, answers)
    assert applied == [] and errors == []
