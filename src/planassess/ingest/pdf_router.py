"""Routes a PDF to the vector adapter (P3) or the raster adapter (P4).

A vector PDF exposes line geometry and selectable text; a scanned/raster PDF
does not. We sniff the first page's vector content and route accordingly. The
raster path is added in P4; until then a scanned PDF raises a clear error rather
than silently producing an empty model.
"""

from __future__ import annotations

from pathlib import Path

from ..model.building import BuildingModel

# A page with at least this many vector line items is treated as a vector plan.
_VECTOR_LINE_THRESHOLD = 4


def _vector_line_count(path: Path) -> int:
    import fitz

    doc = fitz.open(str(path))
    if doc.page_count == 0:
        return 0
    page = doc[0]
    return sum(1 for d in page.get_drawings() for it in d.get("items", []) if it[0] in ("l", "re"))


def ingest_pdf(path: Path, project_id: str) -> BuildingModel:
    from .pdf_vector import PDFVectorAdapter

    if _vector_line_count(path) >= _VECTOR_LINE_THRESHOLD:
        return PDFVectorAdapter().ingest(path, project_id)

    # Scanned/raster PDF -> raster adapter (P4) if available.
    try:
        from .pdf_raster import PDFRasterAdapter
    except ImportError as exc:  # raster extras not installed
        raise RuntimeError(
            f"'{path.name}' looks like a scanned/raster PDF. Install the raster extras "
            f"(pip install -e '.[raster]') to ingest it. ({exc})"
        ) from exc
    return PDFRasterAdapter().ingest(path, project_id)
