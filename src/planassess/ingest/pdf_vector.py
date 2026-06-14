"""PDF vector ingestion adapter (P3).

Reads a *vector* PDF floor plan (lines + selectable text, not a scanned image)
with PyMuPDF: extracts line geometry and positioned text, detects the drawing
scale and a north arrow, and hands the primitives to the shared builder used by
the DXF adapter.

PDFs carry no CAD layers or real-world units, so this adapter is inherently
lower-confidence than DXF:

* Scale is recovered from a "1:NNN" note when present; without it, floor areas
  are emitted at very low confidence so they are gap-flagged (never guessed).
* North is recovered from an 'N' label beside a near-vertical arrow; otherwise
  drawing-up is assumed, flagged low-confidence.

PDF coordinates (origin top-left, y down) are flipped to a y-up frame so
orientation and polygon handling match the DXF path.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import fitz  # PyMuPDF
from shapely.geometry import LineString, Point

from ..model.building import BuildingModel
from ..model.enums import Provenance
from .builder import build_model_from_primitives
from .schedule import ScheduleItem, parse_schedule

_SCALE_RE = re.compile(r"\b1\s*[:：]\s*(\d{1,4})\b")
# Points -> metres on paper: (1/72 inch) * 25.4 mm / 1000.
_M_PER_POINT_PAPER = 25.4 / 72.0 / 1000.0

# Geometry filters (points).
_MIN_SEG_LEN = 5.0
_MIN_ROOM_AREA_PT2 = 400.0  # ignore titleblock / annotation noise


class PDFVectorAdapter:
    name = "pdf_vector"

    def supports(self, path: Path) -> bool:
        return path.suffix.lower() == ".pdf"

    def ingest(self, path: Path, project_id: str, page_index: int = 0) -> BuildingModel:
        doc = fitz.open(str(path))
        page = doc[page_index]
        height = page.rect.height

        def flip(x: float, y: float) -> tuple[float, float]:
            return (x, height - y)  # to y-up frame

        text_lines = self._text_lines(page, flip)
        m_per_unit, unit_conf = self._detect_scale([t for t, _ in text_lines])
        north_vec, north_conf = self._detect_north(page, text_lines, flip)

        return build_model_from_primitives(
            project_id=project_id,
            wall_segments=self._wall_segments(page, flip),
            labels=text_lines,
            schedule_items=self._schedule(text_lines),
            north_vec=north_vec,
            north_conf=north_conf,
            m_per_unit=m_per_unit,
            unit_conf=unit_conf,
            geom_provenance=Provenance.PDF_VECTOR,
            text_provenance=Provenance.PDF_VECTOR,
            source_file=str(path),
            adapter_name=self.name,
        )

    # --- extraction ---------------------------------------------------------

    def _text_lines(self, page, flip) -> list[tuple[str, Point]]:
        out: list[tuple[str, Point]] = []
        for block in page.get_text("dict").get("blocks", []):
            for line in block.get("lines", []):
                text = "".join(span["text"] for span in line.get("spans", [])).strip()
                if not text:
                    continue
                x0, y0, x1, y1 = line["bbox"]
                cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
                out.append((text, Point(*flip(cx, cy))))
        return out

    def _wall_segments(self, page, flip) -> list[LineString]:
        segs: list[LineString] = []
        for d in page.get_drawings():
            for item in d.get("items", []):
                if item[0] == "l":  # line
                    p1, p2 = item[1], item[2]
                    seg = (flip(p1.x, p1.y), flip(p2.x, p2.y))
                elif item[0] == "re":  # rectangle -> four edges
                    r = item[1]
                    corners = [flip(r.x0, r.y0), flip(r.x1, r.y0), flip(r.x1, r.y1), flip(r.x0, r.y1)]
                    for a, b in zip(corners, corners[1:] + corners[:1]):
                        if math.dist(a, b) >= _MIN_SEG_LEN:
                            segs.append(LineString([a, b]))
                    continue
                else:
                    continue
                if math.dist(*seg) >= _MIN_SEG_LEN:
                    segs.append(LineString([seg[0], seg[1]]))
        return segs

    def _schedule(self, text_lines: list[tuple[str, Point]]) -> list[ScheduleItem]:
        return parse_schedule([t for t, _ in text_lines])

    def _detect_scale(self, texts: list[str]) -> tuple[float, float]:
        for t in texts:
            if m := _SCALE_RE.search(t):
                ratio = int(m.group(1))
                if ratio > 0:
                    return _M_PER_POINT_PAPER * ratio, 0.6
        # No scale found: emit geometry at paper scale but very low confidence so
        # floor areas are gap-flagged rather than trusted.
        return _M_PER_POINT_PAPER, 0.2

    def _detect_north(self, page, text_lines, flip) -> tuple[tuple[float, float], float]:
        # Find a standalone 'N' label.
        n_pts = [pt for t, pt in text_lines if t.strip().upper() == "N"]
        if not n_pts:
            return (0.0, 1.0), 0.35  # assume drawing-up = north
        n = n_pts[0]
        # Nearest near-vertical short segment; north points from its midpoint to 'N'.
        best = None
        best_d = 1e9
        for d in page.get_drawings():
            for item in d.get("items", []):
                if item[0] != "l":
                    continue
                a, b = flip(item[1].x, item[1].y), flip(item[2].x, item[2].y)
                if abs(b[0] - a[0]) > abs(b[1] - a[1]):
                    continue  # not near-vertical
                mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
                dist = math.dist(mid, (n.x, n.y))
                if dist < best_d:
                    best_d, best = dist, mid
        if best is not None and best_d < 120:
            vec = (n.x - best[0], n.y - best[1])
            if vec != (0.0, 0.0):
                return vec, 0.6
        return (0.0, 1.0), 0.35


def ingest_pdf_vector(path: Path, project_id: str) -> BuildingModel:
    return PDFVectorAdapter().ingest(path, project_id)
