"""Serialise the canonical Building Model to building_model.json."""

from __future__ import annotations

from pathlib import Path

from ..model.building import BuildingModel


def write_building_model_json(model: BuildingModel, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "building_model.json"
    path.write_text(model.model_dump_json(indent=2), encoding="utf-8")
    return path
