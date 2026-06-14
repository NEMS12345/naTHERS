"""P3 PDF-vector ingestion: scale/north detection, rooms, schedule, pipeline.

Skips cleanly if the optional `pdf` extra (PyMuPDF) is not installed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fitz")

from planassess.ingest import ingest as ingest_plan  # noqa: E402
from planassess.ingest.pdf_vector import PDFVectorAdapter, ingest_pdf_vector  # noqa: E402
from planassess.model.enums import Orientation, Provenance, State, ZoneType  # noqa: E402
from planassess.pipeline import run_pipeline  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "synthetic_house.pdf"


@pytest.fixture(scope="module")
def model():
    assert FIXTURE.exists(), "Run scripts/make_synthetic_pdf.py to build the fixture."
    return ingest_pdf_vector(FIXTURE, "PDF-TEST")


def test_scale_detected_from_note():
    m_per_unit, conf = PDFVectorAdapter()._detect_scale(["SCALE 1:100"])
    assert conf >= 0.5
    assert m_per_unit == pytest.approx(25.4 / 72.0 / 1000.0 * 100.0)


def test_no_scale_is_low_confidence():
    _, conf = PDFVectorAdapter()._detect_scale(["no scale here"])
    assert conf < 0.3  # so floor areas get gap-flagged rather than trusted


def test_two_rooms_with_correct_areas(model):
    areas = sorted(z.floor_area.value for z in model.zones)
    assert areas == [pytest.approx(36.0, abs=0.5), pytest.approx(48.0, abs=0.5)]


def test_pdf_confidence_lower_than_dxf(model):
    # PDF lacks layers/units, so floor-area confidence is capped below DXF's.
    assert all(z.floor_area.confidence <= 0.6 for z in model.zones)
    assert all(z.floor_area.source == Provenance.PDF_VECTOR for z in model.zones)


def test_zone_types_inferred(model):
    by_name = {z.name.value: z.type.value for z in model.zones}
    assert by_name["Living/Kitchen"] == ZoneType.LIVING
    assert by_name["Bedrooms"] == ZoneType.NIGHT


def test_north_detected_near_up(model):
    assert model.site.north_angle_deg.value == pytest.approx(0.0, abs=5.0)
    assert model.site.north_angle_deg.confidence >= 0.5


def test_glazing_and_doors_from_schedule(model):
    w1 = next(g for g in model.glazing if g.id == "W1")
    assert w1.zone_id == "Z1"
    assert w1.orientation.value == Orientation.N
    assert w1.u_value.value == 3.9
    d1 = next(d for d in model.doors if d.id == "D1")
    assert d1.zone_id == "Z1"


def test_unextracted_fields_missing(model):
    assert model.project.state.is_missing
    assert all(w.r_value.is_missing for w in model.walls)


def test_registry_dispatches_pdf(model):
    via = ingest_plan(FIXTURE, "PDF-TEST")
    assert len(via.zones) == len(model.zones)


def test_pipeline_consumes_pdf(tmp_path: Path):
    config_dir = Path(__file__).resolve().parents[1] / "config"
    model = ingest_pdf_vector(FIXTURE, "PDF-TEST")
    from planassess.model.tracked import observed

    model.project.postcode = observed("3000", Provenance.HUMAN, 1.0)
    out = run_pipeline(model, State.VIC, tmp_path, config_dir)
    assert (tmp_path / "building_model.json").exists()
    # No wall R-values from a PDF plan -> thermal honestly not computable.
    assert out.thermal.computed is False
