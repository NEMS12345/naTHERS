"""PDF raster ingestion adapter (P4) — offline-first.

For scanned / image-only PDFs. Tier 1 is fully offline:

* rasterise the page with PyMuPDF;
* detect wall lines with OpenCV (Canny + probabilistic Hough), snap endpoints
  and close rooms with the shared builder;
* OCR room labels, the schedule, the scale note and the north marker with
  pytesseract.

Tier 2 (optional, OFF by default) sends only still-unresolved cropped regions to
a vision LLM via the Anthropic API. The adapter runs end to end with Tier 2
disabled; unresolved fields then flow to the gap report rather than being
auto-filled.

Raster extraction is the lowest-confidence path, so values are tagged
accordingly and readily gap-flagged.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import cv2
import numpy as np
from shapely.geometry import LineString, Point

from ..config.loader import load_settings
from ..config.models import Settings
from ..model.building import BuildingModel
from ..model.enums import Provenance
from .builder import build_model_from_primitives
from .schedule import parse_schedule

_SCALE_RE = re.compile(r"\b1\s*[:：]\s*(\d{1,4})\b")
_RENDER_DPI = 200


class PDFRasterAdapter:
    name = "pdf_raster"

    def __init__(self, settings: Settings | None = None):
        self._settings = settings  # loaded lazily if None

    def supports(self, path: Path) -> bool:
        return path.suffix.lower() == ".pdf"

    def ingest(self, path: Path, project_id: str, page_index: int = 0) -> BuildingModel:
        import fitz

        settings = self._settings or load_settings()
        doc = fitz.open(str(path))
        page = doc[page_index]
        pix = page.get_pixmap(dpi=_RENDER_DPI)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY) if pix.n >= 3 else img.copy()
        height = pix.height

        def flip(x: float, y: float) -> tuple[float, float]:
            return (float(x), float(height - y))

        ocr_lines = self._ocr_lines(gray, flip)
        texts = [t for t, _ in ocr_lines]
        schedule_items = parse_schedule(texts)
        m_per_unit, unit_conf = self._detect_scale(texts)
        north_vec, north_conf = self._detect_north(ocr_lines)
        wall_segments = self._detect_walls(gray, flip)

        # --- Tier 2 (optional, OFF by default) ---------------------------------
        if settings.vision_llm.enabled and not schedule_items:
            from .vision_fallback import VisionFallback

            extra = VisionFallback(settings).read_schedule(img)
            schedule_items = parse_schedule(extra)

        model = build_model_from_primitives(
            project_id=project_id,
            wall_segments=wall_segments,
            labels=ocr_lines,
            schedule_items=schedule_items,
            north_vec=north_vec,
            north_conf=north_conf,
            m_per_unit=m_per_unit,
            unit_conf=unit_conf,
            geom_provenance=Provenance.RASTER_CV,
            text_provenance=Provenance.OCR,
            source_file=str(path),
            adapter_name=self.name,
            min_room_area_m2=3.0,  # drop spurious tiny contours from raster noise
        )
        return model

    # --- OCR ----------------------------------------------------------------

    def _ocr_lines(self, gray: np.ndarray, flip) -> list[tuple[str, Point]]:
        import pytesseract

        try:
            data = pytesseract.image_to_data(gray, output_type=pytesseract.Output.DICT)
        except pytesseract.TesseractNotFoundError:  # pragma: no cover
            return []
        # Group words into lines by (block, paragraph, line).
        groups: dict[tuple[int, int, int], list[int]] = {}
        for i, txt in enumerate(data["text"]):
            if txt.strip():
                key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
                groups.setdefault(key, []).append(i)
        lines: list[tuple[str, Point]] = []
        for idxs in groups.values():
            idxs.sort(key=lambda i: data["left"][i])
            text = " ".join(data["text"][i] for i in idxs).strip()
            xs = [data["left"][i] for i in idxs] + [data["left"][i] + data["width"][i] for i in idxs]
            ys = [data["top"][i] for i in idxs] + [data["top"][i] + data["height"][i] for i in idxs]
            cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
            lines.append((text, Point(*flip(cx, cy))))
        return lines

    # --- geometry -----------------------------------------------------------

    def _detect_walls(self, gray: np.ndarray, flip) -> list[LineString]:
        # Walls are long, axis-aligned strokes. Restricting to long near-horizontal
        # / near-vertical lines rejects most text-glyph and annotation noise that
        # otherwise floods polygonisation with spurious tiny rooms.
        edges = cv2.Canny(gray, 50, 150, apertureSize=3)
        min_len = max(60, int(0.06 * max(gray.shape)))
        lines = cv2.HoughLinesP(
            edges, 1, np.pi / 180, threshold=100, minLineLength=min_len, maxLineGap=8
        )
        if lines is None:
            return []
        axis_aligned = []
        for x1, y1, x2, y2 in (tuple(map(float, ln[0])) for ln in lines):
            ang = math.degrees(math.atan2(abs(y2 - y1), abs(x2 - x1)))
            if ang <= 5 or ang >= 85:  # horizontal or vertical only
                axis_aligned.append((x1, y1, x2, y2))
        snapped = self._snap_endpoints(axis_aligned, tol=12.0)
        segs: list[LineString] = []
        for x1, y1, x2, y2 in snapped:
            if math.dist((x1, y1), (x2, y2)) >= min_len:
                segs.append(LineString([flip(x1, y1), flip(x2, y2)]))
        return segs

    @staticmethod
    def _snap_endpoints(segs, tol: float):
        """Cluster nearby endpoints to a shared coordinate so rooms can close."""
        pts: list[tuple[float, float]] = []
        for x1, y1, x2, y2 in segs:
            pts.extend([(x1, y1), (x2, y2)])
        reps: list[tuple[float, float]] = []

        def rep(p):
            for r in reps:
                if math.dist(p, r) <= tol:
                    return r
            reps.append(p)
            return p

        out = []
        for x1, y1, x2, y2 in segs:
            a, b = rep((x1, y1)), rep((x2, y2))
            out.append((a[0], a[1], b[0], b[1]))
        return out

    # --- heuristics ---------------------------------------------------------

    def _detect_scale(self, texts: list[str]) -> tuple[float, float]:
        for t in texts:
            if m := _SCALE_RE.search(t):
                ratio = int(m.group(1))
                if ratio > 0:
                    # pixel -> metre at this DPI and scale ratio.
                    m_per_pixel = (25.4 / _RENDER_DPI / 1000.0) * ratio
                    return m_per_pixel, 0.45
        return (25.4 / _RENDER_DPI / 1000.0), 0.15  # unknown scale -> very low confidence

    def _detect_north(self, ocr_lines) -> tuple[tuple[float, float], float]:
        # OCR rarely localises an arrow reliably; assume drawing-up = north, flagged.
        for t, _ in ocr_lines:
            if t.strip().upper() == "N":
                return (0.0, 1.0), 0.4
        return (0.0, 1.0), 0.3


def ingest_pdf_raster(path: Path, project_id: str) -> BuildingModel:
    return PDFRasterAdapter().ingest(path, project_id)
