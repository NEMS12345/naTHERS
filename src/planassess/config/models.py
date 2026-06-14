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


class ThermalMethod(BaseModel):
    air_changes_per_hour: float = 0.7
    internal_gain_w_per_m2: float = 4.0
    heating_utilisation_factor: float = 0.6
    solar_gain_factor: float = 0.6
    default_wall_height_m: float = 2.7


class Settings(BaseModel):
    review_confidence_threshold: float = Field(default=0.6, ge=0.0, le=1.0)
    vision_llm: VisionLLMSettings = Field(default_factory=VisionLLMSettings)
    oda_file_converter: ODASettings = Field(default_factory=ODASettings)
    thermal: ThermalMethod = Field(default_factory=ThermalMethod)


# --- jurisdictions.yaml ------------------------------------------------------


class BasixDtsThresholds(BaseModel):
    min_ceiling_r: float = 4.1
    min_wall_r: float = 2.8
    min_floor_r: float = 1.0
    max_glazing_u: float = 5.4
    max_glazing_shgc: float = 0.60
    max_glazing_area_ratio: float = 0.30


class BasixThermalComfort(BaseModel):
    method: str = "deemed_to_satisfy"
    requires_simulation_above_area_m2: float = 0.0
    dts: BasixDtsThresholds = Field(default_factory=BasixDtsThresholds)


class BasixEnergy(BaseModel):
    # Indicative efficiency-index pass marks (0-100) for the PlanAssess proxy —
    # NOT the regulated BASIX percentage (see regulated_reduction_note).
    indicative_index_target_by_dwelling: dict[str, float] = Field(default_factory=dict)
    regulated_reduction_note: str | None = None


class BasixWater(BaseModel):
    target_pct_by_dwelling: dict[str, float] = Field(default_factory=dict)
    regulated_note: str | None = None


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
    seven_star_mandatory: bool = True
    ncc2022_adoption_date: str | None = None
    basix: BasixConfig | None = None
    woh: WohConfig | None = None


class JurisdictionsConfig(BaseModel):
    standards_version: str
    ncc_alignment: str
    default_star_target: float = 7.0
    last_reviewed: str | None = None
    sources: list[str] = Field(default_factory=list)
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


# --- climate_data.yaml -------------------------------------------------------


class StarBand(BaseModel):
    star: float
    max_load: float  # max total heating+cooling load (MJ/m2.yr) to achieve this star


class ZoneClimate(BaseModel):
    heating_degree_days: float
    cooling_degree_days: float
    solar_irradiance_factor: float = 1.0
    star_bands: list[StarBand] = Field(default_factory=list)


class ClimateDataTable(BaseModel):
    version: str
    default: ZoneClimate
    zones: dict[int, ZoneClimate] = Field(default_factory=dict)

    def for_zone(self, zone: int) -> ZoneClimate:
        """Return zone climate, falling back to default (with default star bands)."""
        zc = self.zones.get(zone)
        if zc is None:
            return self.default
        # Inherit default star bands if a zone omits them.
        if not zc.star_bands:
            zc = zc.model_copy(update={"star_bands": self.default.star_bands})
        return zc
