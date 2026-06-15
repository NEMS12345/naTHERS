"""Load and validate the versioned, jurisdiction-keyed config files."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from ..model.enums import Provenance
from ..model.tracked import TrackedValue, missing
from .models import (
    ClimateDataTable,
    ClimateZoneTable,
    JurisdictionsConfig,
    NccClimateZoneTable,
    Settings,
)

# Repo-root/config by default (…/src/planassess/config/loader.py -> repo root).
DEFAULT_CONFIG_DIR = Path(__file__).resolve().parents[3] / "config"


def _read_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_settings(config_dir: Path | None = None) -> Settings:
    config_dir = config_dir or DEFAULT_CONFIG_DIR
    return Settings.model_validate(_read_yaml(config_dir / "settings.yaml"))


def load_jurisdictions(config_dir: Path | None = None) -> JurisdictionsConfig:
    config_dir = config_dir or DEFAULT_CONFIG_DIR
    return JurisdictionsConfig.model_validate(_read_yaml(config_dir / "jurisdictions.yaml"))


def load_climate_zones(config_dir: Path | None = None) -> ClimateZoneTable:
    config_dir = config_dir or DEFAULT_CONFIG_DIR
    return ClimateZoneTable.model_validate(_read_yaml(config_dir / "climate_zones.yaml"))


def load_climate_data(config_dir: Path | None = None) -> ClimateDataTable:
    config_dir = config_dir or DEFAULT_CONFIG_DIR
    return ClimateDataTable.model_validate(_read_yaml(config_dir / "climate_data.yaml"))


def load_ncc_climate_zones(config_dir: Path | None = None) -> NccClimateZoneTable:
    """Load the coarse NCC zones (1–8) cross-reference table (ABCB, CC BY 4.0)."""
    config_dir = config_dir or DEFAULT_CONFIG_DIR
    return NccClimateZoneTable.model_validate(_read_yaml(config_dir / "ncc_climate_zones.yaml"))


def lookup_climate_zone(
    postcode: str, config_dir: Path | None = None
) -> TrackedValue:
    """Return the NatHERS climate zone for a postcode as a TrackedValue.

    Ambiguous postcodes (spanning multiple zones) resolve to a low-confidence
    value so they are gap-flagged rather than silently disambiguated. Unknown
    postcodes return an explicit missing value — never a guess.
    """
    table = _cached_climate_zones(str(config_dir) if config_dir else None)
    seed = "UNVERIFIED" in (table.version or "").upper()
    if postcode in table.postcodes:
        entry = table.postcodes[postcode]
        note = f"Postcode {postcode} -> NatHERS climate zone {entry.zone} (national lookup)."
        if seed or entry.confidence < 0.7:
            note += " Illustrative seed value — verify against the official NatHERS table."
        return TrackedValue(
            value=entry.zone,
            source=Provenance.DERIVED,
            confidence=entry.confidence,
            notes=note,
        )
    if postcode in table.ambiguous:
        amb = table.ambiguous[postcode]
        return TrackedValue(
            value=amb.zones[0],
            source=Provenance.DERIVED,
            confidence=amb.confidence,
            notes=(
                f"Postcode {postcode} is ambiguous across NatHERS zones {amb.zones}. "
                f"{amb.note or ''} Human confirmation required."
            ).strip(),
        )
    return missing(
        notes=f"Postcode {postcode} not found in NatHERS climate-zone table. Human input required."
    )


@lru_cache(maxsize=8)
def _cached_climate_zones(config_dir_str: str | None) -> ClimateZoneTable:
    config_dir = Path(config_dir_str) if config_dir_str else None
    return load_climate_zones(config_dir)
