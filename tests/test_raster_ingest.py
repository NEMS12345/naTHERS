"""P4 PDF-raster ingestion (offline Tier 1) + Tier-2 vision fallback gating.

Skips cleanly if the optional `raster` extras or the tesseract binary are absent.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("cv2")
pytest.importorskip("fitz")
pytest.importorskip("pytesseract")

import pytesseract  # noqa: E402

try:
    pytesseract.get_tesseract_version()
except Exception:  # pragma: no cover - environment without the binary
    pytest.skip("tesseract binary not available", allow_module_level=True)

from planassess.config.loader import load_settings  # noqa: E402
from planassess.config.models import Settings, VisionLLMSettings  # noqa: E402
from planassess.ingest import ingest as ingest_plan  # noqa: E402
from planassess.ingest.pdf_raster import PDFRasterAdapter, ingest_pdf_raster  # noqa: E402
from planassess.ingest.vision_fallback import VisionFallback  # noqa: E402
from planassess.model.enums import Provenance, State  # noqa: E402
from planassess.pipeline import run_pipeline  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "synthetic_house_scan.pdf"
CONFIG = Path(__file__).resolve().parents[1] / "config"


@pytest.fixture(scope="module")
def model():
    assert FIXTURE.exists(), "Run scripts/make_synthetic_raster_pdf.py to build the fixture."
    return ingest_pdf_raster(FIXTURE, "RASTER-TEST")


def test_runs_fully_offline_by_default():
    # Default settings keep the vision LLM OFF — adapter must complete with no API.
    assert load_settings(CONFIG).vision_llm.enabled is False
    m = ingest_pdf_raster(FIXTURE, "RASTER-TEST")
    assert m.extraction_meta.adapter == "pdf_raster"


def test_schedule_recovered_by_ocr(model):
    ids = {g.id for g in model.glazing} | {d.id for d in model.doors}
    assert {"W1", "W2", "D1"} <= ids
    w1 = next(g for g in model.glazing if g.id == "W1")
    assert w1.u_value.value == 3.9
    assert w1.u_value.source == Provenance.SCHEDULE


def test_at_least_one_labelled_conditioned_zone(model):
    named = [z for z in model.zones if not z.name.is_missing]
    assert named, "expected at least one OCR-labelled room"
    assert any("living" in z.name.value.lower() for z in named)


def test_raster_provenance_and_low_confidence(model):
    z = next(z for z in model.zones if not z.name.is_missing)
    assert z.name.source == Provenance.OCR
    assert z.floor_area.source == Provenance.RASTER_CV
    # Raster is the lowest-confidence path -> floor areas readily gap-flagged.
    assert z.floor_area.confidence <= 0.45


def test_router_dispatches_scan_to_raster():
    m = ingest_plan(FIXTURE, "RASTER-TEST")
    assert m.extraction_meta.adapter == "pdf_raster"


def test_pipeline_runs_on_raster_model(tmp_path: Path):
    m = ingest_pdf_raster(FIXTURE, "RASTER-TEST")
    from planassess.model.tracked import observed

    m.project.postcode = observed("4000", Provenance.HUMAN, 1.0)
    out = run_pipeline(m, State.QLD, tmp_path, CONFIG)
    assert (tmp_path / "building_model.json").exists()
    assert (tmp_path / "gap_report.md").exists()


# --- Tier 2 vision fallback gating ------------------------------------------


def _img() -> np.ndarray:
    return np.full((40, 80, 3), 255, dtype=np.uint8)


def test_vision_fallback_disabled_is_noop():
    vf = VisionFallback(Settings(vision_llm=VisionLLMSettings(enabled=False)))
    assert vf.enabled is False
    assert vf.read_schedule(_img()) == []  # offline guarantee: no network, nothing filled


def test_vision_fallback_enabled_parses_and_crops(monkeypatch):
    vf = VisionFallback(Settings(vision_llm=VisionLLMSettings(enabled=True, model="claude-sonnet-4-6")))
    captured = {}

    def fake_call(prompt, image):
        captured["shape"] = image.shape
        return "W9 | Living | N | 1200x1000 | Aluminium | Double | U=4.0 | SHGC=0.6\nNONE"

    monkeypatch.setattr(vf, "_call", fake_call)
    lines = vf.read_schedule(_img(), region=(10, 10, 50, 30))
    assert any(line.startswith("W9") for line in lines)
    # Only the cropped region is sent, never the whole image.
    assert captured["shape"] == (20, 40, 3)


def test_snap_endpoints_clusters_nearby_points():
    segs = [(0, 0, 100, 0), (101, 1, 200, 0)]  # endpoints ~1px apart -> snap together
    out = PDFRasterAdapter._snap_endpoints(segs, tol=5.0)
    # The shared corner near (100,0)/(101,1) collapses to one representative.
    assert out[0][2:] == (100.0, 0.0)
    assert out[1][:2] == (100.0, 0.0)
