"""Ingestion adapter protocol. Every adapter returns a BuildingModel with confidence."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from ..model.building import BuildingModel


@runtime_checkable
class IngestionAdapter(Protocol):
    """An adapter that turns a plan file into the canonical Building Model.

    Adapters must populate every field as a TrackedValue (value + source +
    confidence) and must never silently default — unknown fields stay missing so
    the review gate can flag them.
    """

    name: str

    def supports(self, path: Path) -> bool:
        """True if this adapter can handle the given file."""
        ...

    def ingest(self, path: Path, project_id: str) -> BuildingModel:
        """Parse the file and return a populated BuildingModel."""
        ...
