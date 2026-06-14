"""Typed config models. Targets/benchmarks are loaded, never hardcoded."""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..model.enums import JurisdictionStrategy


# --- settings.yaml -----------------------------------------------------------


class VisionLLMSettings(BaseModel):
    enabled: bool = False
    model: str = "claude-sonnet-4-6"
    send_full_plan: bool = False


class ODASettings(BaseModel):
    enabled: bool = True
    executable: str = "ODAFileConverter"


class Settings(BaseModel):
    review_confidence_threshold: float = Field(default=0.6, ge=0.0, le=1.0)
    vision_llm: VisionLLMSettings = Field(default_factory=VisionLLMSettings)
    oda_file_converter: ODASettings = Field(default_factory=ODASettings)


# --- jurisdictions.yaml ------------------------------------------------------


class BasixThermalComfort(BaseModel):
    method: str = "deemed_to_satisfy"
    requires_simulation_above_area_m2: float = 0.0


class BasixEnergy(BaseModel):
    target_pct_by_dwelling: dict[str, float] = Field(default_factory=dict)


class BasixWater(BaseModel):
    target_pct_by_dwelling: dict[str, float] = Field(default_factory=dict)


class BasixConfig(BaseModel):
    thermal_comfort: BasixThermalComfort = Field(default_factory=BasixThermalComfort)
    energy: BasixEnergy = Field(default_factory=BasixEnergy)
    water: BasixWater = Field(default_factory=BasixWater)


class WohConfig(BaseModel):
    mandatory: bool = True
    benchmark_score: float | None = None


class JurisdictionConfig(BaseModel):
    strategy: JurisdictionStrategy
    nathers_star_target: float
    basix: BasixConfig | None = None
    woh: WohConfig | None = None


class JurisdictionsConfig(BaseModel):
    standards_version: str
    ncc_alignment: str
    default_star_target: float = 7.0
    notes: str | None = None
    jurisdictions: dict[str, JurisdictionConfig]

    def for_state(self, state: str) -> JurisdictionConfig:
        if state not in self.jurisdictions:
            raise KeyError(f"No jurisdiction config for state/territory '{state}'")
        return self.jurisdictions[state]


# --- climate_zones.yaml ------------------------------------------------------


class ZoneEntry(BaseModel):
    zone: int
    confidence: float = Field(ge=0.0, le=1.0)


class AmbiguousZoneEntry(BaseModel):
    zones: list[int]
    confidence: float = Field(ge=0.0, le=1.0)
    note: str | None = None


class ClimateZoneTable(BaseModel):
    version: str
    postcodes: dict[str, ZoneEntry] = Field(default_factory=dict)
    ambiguous: dict[str, AmbiguousZoneEntry] = Field(default_factory=dict)
