"""Generate a synthetic vector-PDF floor plan for the P3 PDF adapter.

Draws the same two-room plan as the DXF fixture, sized for a 1:100 scale, with a
scale note, a north arrow + 'N' label, room labels and a window/door schedule —
all as real vector lines and text (not a raster image).

Run:
    pip install -e ".[pdf]"
    python scripts/make_synthetic_pdf.py tests/fixtures/synthetic_house.pdf
"""

from __future__ import annotations

import sys
from pathlib import Path

# Point -> metre factor at 1:100 ( (1/72 inch)*25.4 mm *100 / 1000 ).
M_PER_POINT_1_100 = 25.4 / 72.0 / 1000.0 * 100.0  # ≈ 0.035278

SCHEDULE_LINES = [
    "WINDOW SCHEDULE",
    "W1 | Living/Kitchen | N | 2000x1500 | Aluminium | Double clear | U=3.9 | SHGC=0.50",
    "W2 | Bedrooms | E | 1800x1200 | Aluminium | Double clear | U=3.9 | SHGC=0.50",
    "DOOR SCHEDULE",
    "D1 | Living/Kitchen | N | 2400x2100 | Sliding aluminium",
]


def build(out_path: Path) -> None:
    try:
        import fitz  # PyMuPDF
    except ImportError:  # pragma: no cover - optional dependency
        raise SystemExit("PyMuPDF not installed. Run: pip install -e '.[pdf]'")

    def m(x: float) -> float:
        return x / M_PER_POINT_1_100  # metres -> points at 1:100

    doc = fitz.open()
    page = doc.new_page(width=600, height=800)

    x0, y0 = 100.0, 200.0
    w14, w8, h6 = m(14), m(8), m(6)  # outer width, internal wall x-offset, height

    # Wall network (PDF top-left origin, y down).
    walls = [
        ((x0, y0), (x0 + w14, y0)),                  # top
        ((x0 + w14, y0), (x0 + w14, y0 + h6)),       # right
        ((x0 + w14, y0 + h6), (x0, y0 + h6)),        # bottom
        ((x0, y0 + h6), (x0, y0)),                   # left
        ((x0 + w8, y0), (x0 + w8, y0 + h6)),         # internal wall
    ]
    for p1, p2 in walls:
        page.draw_line(p1, p2, color=(0, 0, 0), width=1.5)

    # Room labels (inside each room). Offset vertically so OCR reads them as two
    # separate text lines (same y would merge into one line on the raster path).
    page.insert_text((x0 + w8 / 2 - 30, y0 + h6 / 2 - 20), "Living/Kitchen", fontsize=9)
    page.insert_text((x0 + w8 + (w14 - w8) / 2 - 20, y0 + h6 / 2 + 20), "Bedrooms", fontsize=9)

    # North arrow (points up the page) + 'N' label at its head.
    page.draw_line((520, y0 + 60), (520, y0), color=(0, 0, 0), width=1.5)
    page.insert_text((515, y0 - 6), "N", fontsize=12)

    # Scale note.
    page.insert_text((x0, y0 + h6 + 40), "SCALE 1:100", fontsize=9)

    # Schedule block.
    y = y0 + h6 + 70
    for line in SCHEDULE_LINES:
        page.insert_text((x0, y), line, fontsize=8)
        y += 16

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_path))
    print(f"wrote {out_path}")


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("tests/fixtures/synthetic_house.pdf")
    build(target)
