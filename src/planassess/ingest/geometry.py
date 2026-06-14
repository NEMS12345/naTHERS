"""Geometry helpers for ingestion: units, bearings, compass orientation.

Kept adapter-agnostic so PDF-vector ingestion (P3) can reuse the same bearing /
orientation logic as the DXF adapter.
"""

from __future__ import annotations

import math

from ..model.enums import Orientation

# DXF $INSUNITS code -> metres-per-unit. Covers the values seen on residential
# architectural drawings; anything else is treated as unknown (low confidence).
INSUNITS_TO_M: dict[int, float] = {
    0: 1.0,      # unitless (assume metres, flag low confidence)
    1: 0.0254,   # inches
    2: 0.3048,   # feet
    4: 0.001,    # millimetres (architectural default)
    5: 0.01,     # centimetres
    6: 1.0,      # metres
}


def units_to_metres(insunits: int | None) -> tuple[float, float]:
    """Return (metres_per_unit, confidence) for a DXF $INSUNITS code."""
    if insunits is None or insunits == 0:
        return 1.0, 0.3  # unknown units; assume metres but flag for review
    return INSUNITS_TO_M.get(insunits, 1.0), (0.9 if insunits in INSUNITS_TO_M else 0.3)


def bearing_from_north(vec: tuple[float, float], north: tuple[float, float]) -> float:
    """Clockwise bearing of ``vec`` measured from the ``north`` vector, in [0, 360).

    Uses a compass convention (clockwise positive), independent of the drawing's
    rotation, so orientations stay correct on rotated plans.
    """
    nx, ny = north
    vx, vy = vec
    # Angle of each vector measured clockwise from +Y (north-up): atan2(x, y).
    north_ang = math.atan2(nx, ny)
    vec_ang = math.atan2(vx, vy)
    deg = math.degrees(vec_ang - north_ang)
    return deg % 360.0


def compass_8(bearing_deg: float) -> Orientation:
    """Map a 0..360 bearing to the nearest 8-point compass orientation."""
    sectors = [
        Orientation.N,
        Orientation.NE,
        Orientation.E,
        Orientation.SE,
        Orientation.S,
        Orientation.SW,
        Orientation.W,
        Orientation.NW,
    ]
    idx = int((bearing_deg + 22.5) % 360 // 45)
    return sectors[idx]


def north_angle_degrees(north: tuple[float, float]) -> float:
    """How far true north is rotated from the drawing's +Y (up) axis, clockwise [0,360)."""
    return bearing_from_north((0.0, 1.0), north)


def outward_normal(
    a: tuple[float, float], b: tuple[float, float], centroid: tuple[float, float]
) -> tuple[float, float]:
    """Unit normal of edge a->b pointing away from ``centroid``."""
    ex, ey = b[0] - a[0], b[1] - a[1]
    # Two candidate normals perpendicular to the edge.
    n1 = (-ey, ex)
    mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    to_out = (mid[0] - centroid[0], mid[1] - centroid[1])
    # Choose the normal pointing away from the centroid.
    if n1[0] * to_out[0] + n1[1] * to_out[1] < 0:
        n1 = (ey, -ex)
    length = math.hypot(*n1) or 1.0
    return (n1[0] / length, n1[1] / length)
