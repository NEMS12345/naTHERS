"""Generate a synthetic residential DXF fixture for P1 DXF-adapter development.

Scaffold only — requires the optional `dxf` extra (ezdxf). The P0 pipeline does
not depend on this; it exists so P1 has a deterministic DXF to parse. Run:

    pip install -e ".[dxf]"
    python scripts/make_synthetic_dxf.py tests/fixtures/synthetic_house.dxf

The drawing intentionally includes the features the DXF adapter must read:
layers, a closed room polyline, a north arrow, room-label text, and a simple
window schedule as text.
"""

from __future__ import annotations

import sys
from pathlib import Path


def build(out_path: Path) -> None:
    try:
        import ezdxf
    except ImportError:  # pragma: no cover - optional dependency
        raise SystemExit("ezdxf not installed. Run: pip install -e '.[dxf]'")

    doc = ezdxf.new(setup=True)
    msp = doc.modelspace()

    for layer in ("WALLS", "ROOMS", "GLAZING", "TEXT", "NORTH", "SCHEDULE"):
        if layer not in doc.layers:
            doc.layers.add(layer)

    # A simple 8m x 6m rectangular room as a closed polyline (mm units).
    msp.add_lwpolyline(
        [(0, 0), (8000, 0), (8000, 6000), (0, 6000)],
        close=True,
        dxfattribs={"layer": "WALLS"},
    )
    msp.add_text("Living/Kitchen", dxfattribs={"layer": "TEXT"}).set_placement((1500, 3000))

    # North arrow marker (the adapter detects orientation from this).
    msp.add_line((9000, 0), (9000, 1500), dxfattribs={"layer": "NORTH"})
    msp.add_text("N", dxfattribs={"layer": "NORTH"}).set_placement((9000, 1700))

    # A north window + a tiny schedule the adapter can read.
    msp.add_lwpolyline([(2000, 0), (4000, 0)], dxfattribs={"layer": "GLAZING"})
    msp.add_text(
        "W1: 2000x1500 Alu DG U=3.9 SHGC=0.5",
        dxfattribs={"layer": "SCHEDULE"},
    ).set_placement((0, -1000))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(out_path)
    print(f"wrote {out_path}")


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("tests/fixtures/synthetic_house.dxf")
    build(target)
