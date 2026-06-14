"""Generate a synthetic residential DXF fixture for the P1 DXF adapter.

Produces a deterministic two-room single-storey plan containing exactly the
features the adapter must read:

* a closed WALL centreline network (outer rectangle + one internal wall) that
  shapely.polygonize turns into two rooms;
* room-label TEXT placed inside each room;
* a NORTH arrow (a line) defining orientation;
* a window/door SCHEDULE as structured TEXT lines.

Geometry is in millimetres ($INSUNITS = 4), the common architectural default.

Run:
    pip install -e ".[dxf]"
    python scripts/make_synthetic_dxf.py tests/fixtures/synthetic_house.dxf
"""

from __future__ import annotations

import sys
from pathlib import Path

# Schedule lines the adapter parses (pipe-delimited, tolerant parser).
SCHEDULE_LINES = [
    "WINDOW SCHEDULE",
    "W1 | Living/Kitchen | N | 2000x1500 | Aluminium | Double clear | U=3.9 | SHGC=0.50",
    "W2 | Bedrooms | E | 1800x1200 | Aluminium | Double clear | U=3.9 | SHGC=0.50",
    "DOOR SCHEDULE",
    "D1 | Living/Kitchen | N | 2400x2100 | Sliding aluminium",
]


def build(out_path: Path) -> None:
    try:
        import ezdxf
    except ImportError:  # pragma: no cover - optional dependency
        raise SystemExit("ezdxf not installed. Run: pip install -e '.[dxf]'")

    doc = ezdxf.new(setup=True)
    doc.header["$INSUNITS"] = 4  # millimetres
    msp = doc.modelspace()

    for layer in ("WALLS", "GLAZING", "TEXT", "NORTH", "SCHEDULE"):
        if layer not in doc.layers:
            doc.layers.add(layer)

    # --- Wall centreline network (mm). Outer 14m x 6m + internal wall at x=8m.
    # shapely.polygonize closes this into two rooms: 8x6 (48 m2) and 6x6 (36 m2).
    walls = [
        ((0, 0), (14000, 0)),       # south
        ((14000, 0), (14000, 6000)),  # east
        ((14000, 6000), (0, 6000)),   # north
        ((0, 6000), (0, 0)),        # west
        ((8000, 0), (8000, 6000)),    # internal party wall between the two rooms
    ]
    for (x1, y1), (x2, y2) in walls:
        msp.add_line((x1, y1), (x2, y2), dxfattribs={"layer": "WALLS"})

    # --- Room labels (placed inside each room polygon).
    msp.add_text("Living/Kitchen", dxfattribs={"layer": "TEXT", "height": 250}).set_placement(
        (4000, 3000)
    )
    msp.add_text("Bedrooms", dxfattribs={"layer": "TEXT", "height": 250}).set_placement(
        (11000, 3000)
    )

    # --- North arrow: a line pointing +Y (drawing up == true north here).
    msp.add_line((15500, 0), (15500, 1500), dxfattribs={"layer": "NORTH"})
    msp.add_text("N", dxfattribs={"layer": "NORTH", "height": 300}).set_placement((15500, 1800))

    # --- Glazing markers on external walls (segments on the GLAZING layer).
    msp.add_line((3000, 6000), (5000, 6000), dxfattribs={"layer": "GLAZING"})  # north window W1
    msp.add_line((14000, 2000), (14000, 3200), dxfattribs={"layer": "GLAZING"})  # east window W2

    # --- Window/door schedule as structured text.
    y = -1500
    for line in SCHEDULE_LINES:
        msp.add_text(line, dxfattribs={"layer": "SCHEDULE", "height": 200}).set_placement((0, y))
        y -= 600

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(out_path)
    print(f"wrote {out_path}")


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("tests/fixtures/synthetic_house.dxf")
    build(target)
