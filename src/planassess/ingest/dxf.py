"""DXF ingestion adapter (P1).

Parses an architectural DXF into the canonical Building Model:

* reads $INSUNITS to fix the unit scale (mm/m/...);
* collects WALL-layer line/polyline segments into a network and closes rooms
  with ``shapely.polygonize``; computes floor areas;
* associates room-label TEXT to rooms by point-in-polygon;
* detects a NORTH arrow and derives orientation; computes per-wall outward
  bearings;
* reads the window/door SCHEDULE text into glazing/door records.

Every emitted value is a TrackedValue with a source and a confidence reflecting
how cleanly it was detected. Nothing is silently defaulted — undetected fields
stay missing for the review gate.
"""

from __future__ import annotations

from pathlib import Path

import ezdxf
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import polygonize, unary_union

from ..model.building import (
    BuildingModel,
    Dwelling,
    ExternalDoor,
    Glazing,
    Project,
    Site,
    Wall,
    Zone,
)
from ..model.enums import (
    DwellingType,
    Provenance,
    WallAdjacency,
    ZoneType,
)
from ..model.tracked import missing, observed
from .geometry import (
    bearing_from_north,
    compass_8,
    north_angle_degrees,
    outward_normal,
    units_to_metres,
)
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

# Room-name keyword -> zone type (Australian residential conventions).
_ZONE_KEYWORDS = {
    ZoneType.LIVING: ("living", "kitchen", "dining", "lounge", "family", "meals", "study"),
    ZoneType.NIGHT: ("bed", "master", "nursery"),
    ZoneType.WET: ("bath", "ensuite", "laundry", "wc", "toilet", "powder"),
    ZoneType.GARAGE: ("garage", "carport"),
}


def _layer_match(layer: str, names: tuple[str, ...]) -> bool:
    up = layer.upper()
    return any(up == n or up.startswith(n) for n in names)


def _zone_type_from_name(name: str) -> tuple[ZoneType, float]:
    low = name.lower()
    for ztype, keys in _ZONE_KEYWORDS.items():
        if any(k in low for k in keys):
            return ztype, 0.8
    return ZoneType.UNCONDITIONED, 0.3  # unknown -> low confidence, gets flagged


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
        wall_segments = self._collect_wall_segments(msp)
        rooms = self._close_rooms(wall_segments)
        labels = self._collect_labels(msp)
        schedule_items = self._read_schedule(msp)

        model = BuildingModel(
            project=Project(
                id=project_id,
                # Address/state/postcode are rarely reliably extractable from
                # geometry; left missing for the review gate / CLI to supply.
                address=missing(notes="Not extracted from DXF geometry."),
                state=missing(notes="Supply via --state or title block (not parsed in P1)."),
                postcode=missing(notes="Supply via --postcode or title block (not parsed in P1)."),
                climate_zone=missing(notes="Resolved from postcode downstream."),
            ),
            site=Site(
                north_angle_deg=(
                    observed(
                        round(north_angle_degrees(north_vec), 1),
                        Provenance.DXF_GEOMETRY,
                        north_conf,
                        unit="deg",
                        notes="Derived from detected north arrow." if north_conf > 0.3 else
                        "No north arrow found; assumed drawing-up = north.",
                    )
                ),
            ),
            dwellings=[
                Dwelling(
                    id="D1",
                    type=observed(DwellingType.HOUSE, Provenance.DERIVED, 0.4,
                                  notes="Defaulted to house; dwelling type not parsed in P1."),
                    storeys=missing(notes="Storey count not parsed from a single-level DXF."),
                )
            ],
        )

        self._build_zones_and_walls(
            model, rooms, labels, north_vec, north_conf, m_per_unit, unit_conf
        )
        self._apply_schedule(model, schedule_items)

        model.extraction_meta.source_file = str(path)
        model.extraction_meta.adapter = self.name
        return model

    # --- detection helpers ---------------------------------------------------

    def _detect_north(self, msp) -> tuple[tuple[float, float], float]:
        """Find the north arrow line; return its direction vector and confidence."""
        for e in msp.query("LINE"):
            if _layer_match(e.dxf.layer, self.layers["north"]):
                s, t = e.dxf.start, e.dxf.end
                vec = (t.x - s.x, t.y - s.y)
                if vec != (0, 0):
                    return vec, 0.85
        # No arrow: assume drawing-up is north, but flag it (low confidence).
        return (0.0, 1.0), 0.3

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

    def _close_rooms(self, segments: list[LineString]) -> list[Polygon]:
        """Close room polygons from the wall network via shapely.polygonize."""
        if not segments:
            return []
        merged = unary_union(segments)
        polys = [p for p in polygonize(merged) if p.area > 0]
        # Largest first for stable, deterministic ordering.
        return sorted(polys, key=lambda p: p.area, reverse=True)

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

    # --- model assembly ------------------------------------------------------

    def _build_zones_and_walls(
        self, model, rooms, labels, north_vec, north_conf, m_per_unit, unit_conf
    ) -> None:
        for i, poly in enumerate(rooms, start=1):
            zone_id = f"Z{i}"
            # Label whose point falls inside this room.
            name, name_conf = None, 0.0
            for text, pt in labels:
                if poly.contains(pt):
                    name, name_conf = text, 0.85
                    break
            ztype, ztype_conf = (
                _zone_type_from_name(name) if name else (ZoneType.UNCONDITIONED, 0.2)
            )
            area_m2 = round(poly.area * m_per_unit * m_per_unit, 2)
            # Floor-area confidence is capped by the unit/scale confidence.
            area_conf = round(min(0.85, unit_conf), 2)

            model.zones.append(
                Zone(
                    id=zone_id,
                    dwelling_id="D1",
                    name=(observed(name, Provenance.DXF_TEXT, name_conf)
                          if name else missing(notes="No room label found inside polygon.")),
                    type=observed(ztype, Provenance.DXF_TEXT if name else Provenance.DERIVED, ztype_conf),
                    floor_area=observed(area_m2, Provenance.DXF_GEOMETRY, area_conf, unit="m2"),
                    ceiling_height=missing(unit="m", notes="Ceiling height not on floor plan; check sections."),
                    volume=missing(unit="m3", notes="Derivable once ceiling height is confirmed."),
                )
            )

            # Walls from the room polygon edges, oriented via the north arrow.
            centroid = (poly.centroid.x, poly.centroid.y)
            coords = list(poly.exterior.coords)
            for j, (a, b) in enumerate(zip(coords, coords[1:]), start=1):
                normal = outward_normal(a, b, centroid)
                bearing = bearing_from_north(normal, north_vec)
                length_m = LineString([a, b]).length * m_per_unit
                model.walls.append(
                    Wall(
                        id=f"{zone_id}-W{j}",
                        zone_id=zone_id,
                        construction=missing(notes="Wall construction not parsed from geometry (P1)."),
                        r_value=missing(unit="m2.K/W", notes="From schedule/spec — not parsed in P1."),
                        area=observed(
                            round(length_m, 2), Provenance.DXF_GEOMETRY, min(0.6, unit_conf),
                            unit="m2",
                            notes="Wall length (m); area pending confirmed wall height.",
                        ),
                        orientation=observed(
                            compass_8(bearing), Provenance.DXF_GEOMETRY, round(0.9 * north_conf + 0.1, 2)
                        ),
                        adjacency=missing(notes="External/party/internal not classified in P1."),
                    )
                )

    def _apply_schedule(self, model, items: list[ScheduleItem]) -> None:
        """Turn parsed schedule items into Glazing / ExternalDoor records."""
        # Map room name -> zone id for linking schedule items to zones.
        name_to_zone = {
            z.name.value.lower(): z.id for z in model.zones if not z.name.is_missing
        }
        g_idx = d_idx = 0
        for item in items:
            zone_id = name_to_zone.get((item.room or "").lower())
            if item.is_door:
                d_idx += 1
                model.doors.append(
                    ExternalDoor(
                        id=item.item_id or f"D{d_idx}",
                        zone_id=zone_id,
                        orientation=(observed(item.orientation, Provenance.SCHEDULE, item.confidence)
                                     if item.orientation else missing()),
                        area=(observed(item.area_m2, Provenance.SCHEDULE, item.confidence, unit="m2")
                              if item.area_m2 else missing(unit="m2")),
                        type=(observed(item.raw.split("|")[-1].strip(), Provenance.SCHEDULE, item.confidence)
                              if "|" in item.raw else missing()),
                    )
                )
            else:
                g_idx += 1
                model.glazing.append(
                    Glazing(
                        id=item.item_id or f"G{g_idx}",
                        zone_id=zone_id,
                        orientation=(observed(item.orientation, Provenance.SCHEDULE, item.confidence)
                                     if item.orientation else missing()),
                        area=(observed(item.area_m2, Provenance.SCHEDULE, item.confidence, unit="m2")
                              if item.area_m2 else missing(unit="m2")),
                        frame=(observed(item.frame, Provenance.SCHEDULE, item.confidence)
                               if item.frame else missing()),
                        glazing_type=(observed(item.glazing_type, Provenance.SCHEDULE, item.confidence)
                                      if item.glazing_type else missing()),
                        u_value=(observed(item.u_value, Provenance.SCHEDULE, item.confidence, unit="W/m2.K")
                                 if item.u_value is not None else missing(unit="W/m2.K")),
                        shgc=(observed(item.shgc, Provenance.SCHEDULE, item.confidence)
                              if item.shgc is not None else missing()),
                        eave_shading_depth=missing(unit="m", notes="Eave/shading depth from sections — not parsed in P1."),
                    )
                )


def ingest_dxf(path: Path, project_id: str) -> BuildingModel:
    """Convenience wrapper."""
    return DXFAdapter().ingest(path, project_id)
