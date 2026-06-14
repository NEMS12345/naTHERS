"""DXF ingestion adapter (P1).

Parses an architectural DXF into the canonical Building Model:

* reads $INSUNITS to fix the unit scale (mm/m/...);
* collects WALL-layer line/polyline segments;
* detects a NORTH arrow for orientation;
* reads the window/door SCHEDULE text.

The extracted primitives are handed to ``builder.build_model_from_primitives``,
shared with the PDF-vector adapter. Every emitted value is a TrackedValue with a
source and a confidence; nothing is silently defaulted.
"""

from __future__ import annotations

from pathlib import Path

import ezdxf
from shapely.geometry import LineString, Point

from ..model.building import BuildingModel
from ..model.enums import Provenance
from .builder import build_model_from_primitives
from .geometry import units_to_metres
from .schedule import ScheduleItem, parse_schedule

# Default layer-name conventions. A different CAD standard can be mapped by
# passing a LayerMap; nothing is hardcoded into the parsing logic.
DEFAULT_LAYERS = {
    "walls": ("WALLS", "WALL", "A-WALL"),
    "text": ("TEXT", "ROOMS", "A-ROOM", "A-ANNO"),
    "north": ("NORTH",),
    "schedule": ("SCHEDULE", "A-SCHED"),
    "glazing": ("GLAZING", "WINDOWS", "A-GLAZ"),
}


def _layer_match(layer: str, names: tuple[str, ...]) -> bool:
    up = layer.upper()
    return any(up == n or up.startswith(n) for n in names)


class DXFAdapter:
    """Ingestion adapter for DXF files."""

    name = "dxf"

    def __init__(self, layers: dict[str, tuple[str, ...]] | None = None):
        self.layers = layers or DEFAULT_LAYERS

    def supports(self, path: Path) -> bool:
        return path.suffix.lower() == ".dxf"

    def ingest(self, path: Path, project_id: str) -> BuildingModel:
        doc = ezdxf.readfile(str(path))
        msp = doc.modelspace()

        m_per_unit, unit_conf = units_to_metres(doc.header.get("$INSUNITS"))
        north_vec, north_conf = self._detect_north(msp)

        return build_model_from_primitives(
            project_id=project_id,
            wall_segments=self._collect_wall_segments(msp),
            labels=self._collect_labels(msp),
            schedule_items=self._read_schedule(msp),
            north_vec=north_vec,
            north_conf=north_conf,
            m_per_unit=m_per_unit,
            unit_conf=unit_conf,
            geom_provenance=Provenance.DXF_GEOMETRY,
            text_provenance=Provenance.DXF_TEXT,
            source_file=str(path),
            adapter_name=self.name,
        )

    # --- DXF-specific extraction --------------------------------------------

    def _detect_north(self, msp) -> tuple[tuple[float, float], float]:
        for e in msp.query("LINE"):
            if _layer_match(e.dxf.layer, self.layers["north"]):
                s, t = e.dxf.start, e.dxf.end
                vec = (t.x - s.x, t.y - s.y)
                if vec != (0, 0):
                    return vec, 0.85
        return (0.0, 1.0), 0.3  # no arrow: assume up=north, flagged low confidence

    def _collect_wall_segments(self, msp) -> list[LineString]:
        segs: list[LineString] = []
        for e in msp.query("LINE"):
            if _layer_match(e.dxf.layer, self.layers["walls"]):
                s, t = e.dxf.start, e.dxf.end
                segs.append(LineString([(s.x, s.y), (t.x, t.y)]))
        for e in msp.query("LWPOLYLINE"):
            if _layer_match(e.dxf.layer, self.layers["walls"]):
                pts = [(p[0], p[1]) for p in e.get_points()]
                if e.closed:
                    pts.append(pts[0])
                for a, b in zip(pts, pts[1:]):
                    segs.append(LineString([a, b]))
        return segs

    def _collect_labels(self, msp) -> list[tuple[str, Point]]:
        labels: list[tuple[str, Point]] = []
        for e in msp.query("TEXT MTEXT"):
            if _layer_match(e.dxf.layer, self.layers["text"]):
                text = e.plain_text() if e.dxftype() == "MTEXT" else e.dxf.text
                ins = e.dxf.insert
                labels.append((text.strip(), Point(ins.x, ins.y)))
        return labels

    def _read_schedule(self, msp) -> list[ScheduleItem]:
        lines: list[str] = []
        for e in msp.query("TEXT MTEXT"):
            if _layer_match(e.dxf.layer, self.layers["schedule"]):
                text = e.plain_text() if e.dxftype() == "MTEXT" else e.dxf.text
                lines.append(text)
        return parse_schedule(lines)


def ingest_dxf(path: Path, project_id: str) -> BuildingModel:
    """Convenience wrapper."""
    return DXFAdapter().ingest(path, project_id)
