"""Generate a *raster* (scanned-style) PDF fixture for the P4 raster adapter.

Renders the vector fixture to an image and wraps it back into a PDF that carries
NO selectable text or vector paths — forcing the OCR + OpenCV Tier-1 path.

Run:
    python scripts/make_synthetic_raster_pdf.py
"""
from __future__ import annotations
import sys
from pathlib import Path


def build(vector_pdf: Path, out_path: Path, dpi: int = 200) -> None:
    import fitz
    src = fitz.open(str(vector_pdf))
    rect = src[0].rect  # keep ORIGINAL physical page size (points) to preserve scale
    pix = src[0].get_pixmap(dpi=dpi)
    out = fitz.open()
    page = out.new_page(width=rect.width, height=rect.height)
    page.insert_image(page.rect, pixmap=pix)  # image only -> no text/vectors
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.save(str(out_path))
    print(f"wrote {out_path}")


if __name__ == "__main__":
    base = Path("tests/fixtures")
    build(base / "synthetic_house.pdf", base / "synthetic_house_scan.pdf")
