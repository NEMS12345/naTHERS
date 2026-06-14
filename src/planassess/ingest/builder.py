"""Shared 'geometry primitives -> Building Model' assembly.

Both the DXF (P1) and PDF-vector (P3) adapters extract the same primitives —
wall segments, text labels, a north vector, schedule items — and hand them here
to build the canonical model. Keeping assembly in one place means orientation,
room-closing, zone typing and schedule linking behave identically regardless of
source, and only the per-format extraction differs.
"""

from __future__ import annotations

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
from ..model.enums import DwellingType, Provenance, ZoneType
from ..model.tracked import missing, observed
from .geometry import bearing_from_north, compass_8, north_angle_degrees, outward_normal
from .schedule import ScheduleItem

# Room-name keyword -> zone type (Australian residential conventions).
ZONE_KEYWORDS = {
    ZoneType.LIVING: ("living", "kitchen", "dining", "lounge", "family", "meals", "study"),
    ZoneType.NIGHT: ("bed", "master", "nursery"),
    ZoneType.WET: ("bath", "ensuite", "laundry", "wc", "toilet", "powder"),
    ZoneType.GARAGE: ("garage", "carport"),
}


def zone_type_from_name(name: str) -> tuple[ZoneType, float]:
    low = name.lower()
    for ztype, keys in ZONE_KEYWORDS.items():
        if any(k in low for k in keys):
            return ztype, 0.8
    return ZoneType.UNCONDITIONED, 0.3  # unknown -> low confidence, gets flagged


def close_rooms(segments: list[LineString]) -> list[Polygon]:
    """Close room polygons from a wall-segment network via shapely.polygonize."""
    if not segments:
        return []
    merged = unary_union(segments)
    polys = [p for p in polygonize(merged) if p.area > 0]
    return sorted(polys, key=lambda p: p.area, reverse=True)


def build_model_from_primitives(
    *,
    project_id: str,
    wall_segments: list[LineString],
    labels: list[tuple[str, Point]],
    schedule_items: list[ScheduleItem],
    north_vec: tuple[float, float],
    north_conf: float,
    m_per_unit: float,
    unit_conf: float,
    geom_provenance: Provenance,
    text_provenance: Provenance,
    source_file: str,
    adapter_name: str,
    min_room_area_m2: float = 0.0,
) -> BuildingModel:
    """Assemble a BuildingModel from extracted geometry primitives.

    ``min_room_area_m2`` discards closed polygons smaller than this real-world
    area — used by the noisy raster path to drop spurious tiny contours.
    """
    model = BuildingModel(
        project=Project(
            id=project_id,
            address=missing(notes="Not extracted from drawing geometry."),
            state=missing(notes="Supply via --state or title block (not parsed)."),
            postcode=missing(notes="Supply via --postcode or title block (not parsed)."),
            climate_zone=missing(notes="Resolved from postcode downstream."),
        ),
        site=Site(
            north_angle_deg=observed(
                round(north_angle_degrees(north_vec), 1),
                geom_provenance,
                north_conf,
                unit="deg",
                notes=("Derived from detected north arrow." if north_conf > 0.3
                       else "No north arrow found; assumed drawing-up = north."),
            ),
        ),
        dwellings=[
            Dwelling(
                id="D1",
                type=observed(DwellingType.HOUSE, Provenance.DERIVED, 0.4,
                              notes="Defaulted to house; dwelling type not parsed from geometry."),
                storeys=missing(notes="Storey count not parsed from a single-level drawing."),
            )
        ],
    )

    rooms = close_rooms(wall_segments)
    if min_room_area_m2 > 0:
        min_units = min_room_area_m2 / (m_per_unit * m_per_unit)
        rooms = [p for p in rooms if p.area >= min_units]
    _build_zones_and_walls(
        model, rooms, labels, north_vec, north_conf, m_per_unit, unit_conf,
        geom_provenance, text_provenance,
    )
    _apply_schedule(model, schedule_items)

    model.extraction_meta.source_file = source_file
    model.extraction_meta.adapter = adapter_name
    return model


def _build_zones_and_walls(
    model, rooms, labels, north_vec, north_conf, m_per_unit, unit_conf,
    geom_provenance, text_provenance,
) -> None:
    for i, poly in enumerate(rooms, start=1):
        zone_id = f"Z{i}"
        name, name_conf = None, 0.0
        for text, pt in labels:
            if poly.contains(pt):
                name, name_conf = text, 0.85
                break
        ztype, ztype_conf = (
            zone_type_from_name(name) if name else (ZoneType.UNCONDITIONED, 0.2)
        )
        area_m2 = round(poly.area * m_per_unit * m_per_unit, 2)
        area_conf = round(min(0.85, unit_conf), 2)

        model.zones.append(
            Zone(
                id=zone_id,
                dwelling_id="D1",
                name=(observed(name, text_provenance, name_conf)
                      if name else missing(notes="No room label found inside polygon.")),
                type=observed(ztype, text_provenance if name else geom_provenance, ztype_conf),
                floor_area=observed(area_m2, geom_provenance, area_conf, unit="m2"),
                ceiling_height=missing(unit="m", notes="Ceiling height not on floor plan; check sections."),
                volume=missing(unit="m3", notes="Derivable once ceiling height is confirmed."),
            )
        )

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
                    construction=missing(notes="Wall construction not parsed from geometry."),
                    r_value=missing(unit="m2.K/W", notes="From schedule/spec — not parsed from geometry."),
                    area=observed(
                        round(length_m, 2), geom_provenance, min(0.6, unit_conf), unit="m2",
                        notes="Wall length (m); area pending confirmed wall height.",
                    ),
                    orientation=observed(
                        compass_8(bearing), geom_provenance, round(0.9 * north_conf + 0.1, 2)
                    ),
                    adjacency=missing(notes="External/party/internal not classified from geometry."),
                )
            )


def _apply_schedule(model, items: list[ScheduleItem]) -> None:
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
                    eave_shading_depth=missing(unit="m", notes="Eave/shading depth from sections — not parsed."),
                )
            )
