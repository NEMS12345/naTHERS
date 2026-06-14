"""Ingestion adapters. DXF (P1), DWG (P2), PDF vector (P3), PDF raster (P4).

Adapters with heavy optional dependencies (ezdxf, shapely, PyMuPDF, ...) are
imported lazily by :func:`get_adapter` so the core package stays installable
without them.
"""

from __future__ import annotations

from pathlib import Path

from ..model.building import BuildingModel
from .base import IngestionAdapter

# Suffix -> phase the adapter is scheduled for (used for clear "not yet" errors).
ADAPTER_PHASES: dict[str, str] = {}  # all planned ingestion formats now implemented


class AdapterNotAvailable(RuntimeError):
    """Raised when no ingestion adapter is available for a file type yet."""


def ingest(path: Path, project_id: str) -> BuildingModel:
    """Dispatch a plan file to the appropriate ingestion adapter."""
    suffix = path.suffix.lower()
    if suffix == ".dxf":
        from .dxf import DXFAdapter

        return DXFAdapter().ingest(path, project_id)
    if suffix == ".dwg":
        from .dwg import DWGAdapter

        return DWGAdapter().ingest(path, project_id)
    if suffix == ".pdf":
        from .pdf_router import ingest_pdf

        return ingest_pdf(path, project_id)
    phase = ADAPTER_PHASES.get(suffix)
    if phase:
        raise AdapterNotAvailable(
            f"Ingestion adapter for '{suffix}' is scheduled for phase {phase} and is not yet "
            f"available."
        )
    raise AdapterNotAvailable(f"Unsupported input format: '{suffix}'.")


__all__ = ["IngestionAdapter", "ingest", "AdapterNotAvailable", "ADAPTER_PHASES"]
