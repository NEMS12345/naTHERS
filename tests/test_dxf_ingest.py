"""P1 DXF ingestion: geometry, orientation, schedule parsing, end-to-end pipeline.

Skips cleanly if the optional `dxf` extra (ezdxf/shapely) is not installed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("ezdxf")
pytest.importorskip("shapely")

from planassess.ingest import ingest as ingest_plan  # noqa: E402
from planassess.ingest.dxf import ingest_dxf  # noqa: E402
from planassess.ingest.geometry import (  # noqa: E402
    bearing_from_north,
    compass_8,
    units_to_metres,
)
from planassess.ingest.schedule import parse_schedule_line  # noqa: E402
from planassess.model.enums import Orientation, Provenance, State, ZoneType  # noqa: E402
from planassess.pipeline import run_pipeline  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "synthetic_house.dxf"


@pytest.fixture(scope="module")
def model():
    assert FIXTURE.exists(), "Run scripts/make_synthetic_dxf.py to build the fixture."
    return ingest_dxf(FIXTURE, "DXF-TEST")


# --- geometry/units unit tests ----------------------------------------------


def test_units_mm():
    m_per_unit, conf = units_to_metres(4)
    assert m_per_unit == 0.001
    assert conf >= 0.8


def test_units_unknown_low_confidence():
    _, conf = units_to_metres(0)
    assert conf < 0.6  # unknown units must be flagged


def test_bearing_and_compass_north_up():
    # With north pointing +Y, a vector pointing +Y is due North.
    assert compass_8(bearing_from_north((0, 1), (0, 1))) == Orientation.N
    assert compass_8(bearing_from_north((1, 0), (0, 1))) == Orientation.E
    assert compass_8(bearing_from_north((0, -1), (0, 1))) == Orientation.S
    assert compass_8(bearing_from_north((-1, 0), (0, 1))) == Orientation.W


def test_compass_handles_rotated_north():
    # If north points +X (drawing rotated 90deg), a +X vector is North.
    assert compass_8(bearing_from_north((1, 0), (1, 0))) == Orientation.N


# --- schedule parser ---------------------------------------------------------


def test_parse_window_schedule_line():
    item = parse_schedule_line("W1 | Living | N | 2000x1500 | Aluminium | Double clear | U=3.9 | SHGC=0.50")
    assert item is not None
    assert item.item_id == "W1"
    assert not item.is_door
    assert item.orientation == Orientation.N
    assert item.area_m2 == 3.0
    assert item.u_value == 3.9
    assert item.shgc == 0.5
    assert item.frame == "Aluminium"
    assert item.confidence > 0.6


def test_parse_door_line():
    item = parse_schedule_line("D1 | Living | N | 2400x2100 | Sliding aluminium")
    assert item is not None
    assert item.is_door
    assert item.area_m2 == pytest.approx(5.04)


def test_non_schedule_line_ignored():
    assert parse_schedule_line("WINDOW SCHEDULE") is None


# --- end-to-end adapter ------------------------------------------------------


def test_two_rooms_closed_with_correct_areas(model):
    areas = sorted(z.floor_area.value for z in model.zones)
    assert areas == [36.0, 48.0]  # 6x6 and 8x6 rooms (mm -> m)


def test_zone_types_inferred_from_labels(model):
    by_name = {z.name.value: z.type.value for z in model.zones}
    assert by_name["Living/Kitchen"] == ZoneType.LIVING
    assert by_name["Bedrooms"] == ZoneType.NIGHT


def test_north_angle_detected(model):
    assert model.site.north_angle_deg.value == pytest.approx(0.0)
    assert model.site.north_angle_deg.confidence >= 0.8
    assert model.site.north_angle_deg.source == Provenance.DXF_GEOMETRY


def test_wall_orientations_present_for_each_room(model):
    living_walls = [w.orientation.value for w in model.walls if w.zone_id == "Z1"]
    assert {Orientation.N, Orientation.E, Orientation.S, Orientation.W} <= set(living_walls)


def test_glazing_from_schedule_linked_to_zone(model):
    w1 = next(g for g in model.glazing if g.id == "W1")
    assert w1.zone_id == "Z1"
    assert w1.orientation.value == Orientation.N
    assert w1.u_value.value == 3.9
    assert w1.shgc.value == 0.5
    assert w1.area.value == 3.0


def test_door_from_schedule(model):
    d1 = next(d for d in model.doors if d.id == "D1")
    assert d1.zone_id == "Z1"
    assert d1.area.value == pytest.approx(5.04)


def test_unextracted_fields_are_missing_not_guessed(model):
    # State/postcode/climate zone aren't derivable from geometry -> stay missing.
    assert model.project.state.is_missing
    assert model.project.postcode.is_missing
    # Ceiling heights aren't on a floor plan.
    assert all(z.ceiling_height.is_missing for z in model.zones)
    # Wall R-values/construction not parsed in P1.
    assert all(w.r_value.is_missing for w in model.walls)


def test_provenance_recorded_on_extracted_values(model):
    z = model.zones[0]
    assert z.floor_area.source == Provenance.DXF_GEOMETRY
    assert z.name.source == Provenance.DXF_TEXT


def test_dispatch_via_registry(model):
    via_registry = ingest_plan(FIXTURE, "DXF-TEST")
    assert len(via_registry.zones) == len(model.zones)


def test_pipeline_consumes_dxf_model(tmp_path: Path):
    config_dir = Path(__file__).resolve().parents[1] / "config"
    model = ingest_dxf(FIXTURE, "DXF-TEST")
    # Supply jurisdiction context a floor plan can't provide.
    from planassess.model.tracked import observed

    model.project.postcode = observed("2000", Provenance.HUMAN, 1.0)
    out = run_pipeline(model, State.NSW, tmp_path, config_dir)
    assert (tmp_path / "building_model.json").exists()
    # Geometry-derived climate zone resolved from the supplied postcode.
    assert model.project.climate_zone.value == 56
    # Real plan extraction leaves genuine gaps for human review.
    assert len(out.review.gaps) > 0
    # The DXF model lacks wall R-values, so thermal can't be computed -> honest.
    assert out.thermal.computed is False
