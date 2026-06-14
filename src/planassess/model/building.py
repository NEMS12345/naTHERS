"""The canonical Building Model.

Every domain field is a :class:`TrackedValue` so it carries value + source +
confidence. Structural identifiers and relational links (``id``, ``dwelling_id``,
``zone_id``, ``wall_id``) are plain typed fields — they are model wiring, not
extracted measurements, so they are not themselves tracked.

Units convention (SI):
    length m | area m2 | volume m3 | R-value m2.K/W | U-value W/m2.K
    energy MJ/m2.yr | angle degrees clockwise from true north
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..constants import SCHEMA_VERSION
from .enums import (
    DwellingType,
    FloorType,
    Orientation,
    RoofType,
    State,
    SubFloorCondition,
    WallAdjacency,
    ZoneType,
)
from .tracked import TrackedValue

# Shorthand: a tracked value of a given type.
TV = TrackedValue


class Project(BaseModel):
    id: str
    address: TV[str] = Field(default_factory=TrackedValue)
    state: TV[State] = Field(default_factory=TrackedValue)
    postcode: TV[str] = Field(default_factory=TrackedValue)
    # NatHERS climate zone (1..69), looked up nationally from postcode. Ambiguous
    # postcodes resolve to a low-confidence value so they trip the review gate.
    climate_zone: TV[int] = Field(default_factory=TrackedValue)


class Site(BaseModel):
    site_area: TV[float] = Field(default_factory=lambda: TrackedValue(unit="m2"))
    north_angle_deg: TV[float] = Field(default_factory=lambda: TrackedValue(unit="deg"))
    roof_plan_area: TV[float] = Field(default_factory=lambda: TrackedValue(unit="m2"))


class Dwelling(BaseModel):
    id: str
    type: TV[DwellingType] = Field(default_factory=TrackedValue)
    storeys: TV[int] = Field(default_factory=TrackedValue)


class Zone(BaseModel):
    id: str
    dwelling_id: str | None = None  # link to parent Dwelling
    name: TV[str] = Field(default_factory=TrackedValue)
    type: TV[ZoneType] = Field(default_factory=TrackedValue)
    floor_area: TV[float] = Field(default_factory=lambda: TrackedValue(unit="m2"))
    ceiling_height: TV[float] = Field(default_factory=lambda: TrackedValue(unit="m"))
    volume: TV[float] = Field(default_factory=lambda: TrackedValue(unit="m3"))


class Wall(BaseModel):
    id: str
    zone_id: str | None = None  # link to the Zone this wall bounds
    construction: TV[str] = Field(default_factory=TrackedValue)
    r_value: TV[float] = Field(default_factory=lambda: TrackedValue(unit="m2.K/W"))
    area: TV[float] = Field(default_factory=lambda: TrackedValue(unit="m2"))
    orientation: TV[Orientation] = Field(default_factory=TrackedValue)
    adjacency: TV[WallAdjacency] = Field(default_factory=TrackedValue)


class RoofCeiling(BaseModel):
    id: str
    zone_id: str | None = None
    roof_type: TV[RoofType] = Field(default_factory=TrackedValue)
    construction: TV[str] = Field(default_factory=TrackedValue)
    r_value: TV[float] = Field(default_factory=lambda: TrackedValue(unit="m2.K/W"))
    area: TV[float] = Field(default_factory=lambda: TrackedValue(unit="m2"))
    colour: TV[str] = Field(default_factory=TrackedValue)
    # Solar absorptance 0..1; may be derived from colour (provenance DERIVED).
    solar_absorptance: TV[float] = Field(default_factory=TrackedValue)


class Floor(BaseModel):
    id: str
    zone_id: str | None = None
    type: TV[FloorType] = Field(default_factory=TrackedValue)
    sub_floor_condition: TV[SubFloorCondition] = Field(default_factory=TrackedValue)
    r_value: TV[float] = Field(default_factory=lambda: TrackedValue(unit="m2.K/W"))
    area: TV[float] = Field(default_factory=lambda: TrackedValue(unit="m2"))


class Glazing(BaseModel):
    id: str
    zone_id: str | None = None
    wall_id: str | None = None  # host wall (for orientation/shading context)
    orientation: TV[Orientation] = Field(default_factory=TrackedValue)
    area: TV[float] = Field(default_factory=lambda: TrackedValue(unit="m2"))
    frame: TV[str] = Field(default_factory=TrackedValue)
    glazing_type: TV[str] = Field(default_factory=TrackedValue)
    u_value: TV[float] = Field(default_factory=lambda: TrackedValue(unit="W/m2.K"))
    shgc: TV[float] = Field(default_factory=TrackedValue)  # solar heat gain coefficient 0..1
    eave_shading_depth: TV[float] = Field(default_factory=lambda: TrackedValue(unit="m"))


class ExternalDoor(BaseModel):
    id: str
    zone_id: str | None = None
    wall_id: str | None = None
    orientation: TV[Orientation] = Field(default_factory=TrackedValue)
    area: TV[float] = Field(default_factory=lambda: TrackedValue(unit="m2"))
    type: TV[str] = Field(default_factory=TrackedValue)


class Services(BaseModel):
    hot_water: TV[str] = Field(default_factory=TrackedValue)
    heating: TV[str] = Field(default_factory=TrackedValue)
    cooling: TV[str] = Field(default_factory=TrackedValue)
    ventilation: TV[str] = Field(default_factory=TrackedValue)
    lighting: TV[str] = Field(default_factory=TrackedValue)
    cooktop: TV[str] = Field(default_factory=TrackedValue)
    pool_spa: TV[str] = Field(default_factory=TrackedValue)
    solar_pv_kw: TV[float] = Field(default_factory=lambda: TrackedValue(unit="kW"))
    battery_kwh: TV[float] = Field(default_factory=lambda: TrackedValue(unit="kWh"))


class Fixtures(BaseModel):
    wels_taps: TV[float] = Field(default_factory=lambda: TrackedValue(unit="stars"))
    wels_showers: TV[float] = Field(default_factory=lambda: TrackedValue(unit="stars"))
    wels_toilets: TV[float] = Field(default_factory=lambda: TrackedValue(unit="stars"))
    rainwater_tank_l: TV[float] = Field(default_factory=lambda: TrackedValue(unit="L"))
    landscaping_area: TV[float] = Field(default_factory=lambda: TrackedValue(unit="m2"))
    landscaping_type: TV[str] = Field(default_factory=TrackedValue)


class ExtractionMeta(BaseModel):
    """Provenance and completeness summary for the whole extraction."""

    source_file: str | None = None
    adapter: str | None = None  # which ingestion adapter produced this model
    field_count: int = 0
    populated_count: int = 0
    flagged_count: int = 0  # below review threshold (filled by the review gate)

    @property
    def completeness(self) -> float:
        """Fraction of tracked fields that carry a value (0..1)."""
        return (self.populated_count / self.field_count) if self.field_count else 0.0


class BuildingModel(BaseModel):
    """Canonical, jurisdiction-neutral representation of a residential plan."""

    schema_version: str = SCHEMA_VERSION
    project: Project
    site: Site = Field(default_factory=Site)
    dwellings: list[Dwelling] = Field(default_factory=list)
    zones: list[Zone] = Field(default_factory=list)
    walls: list[Wall] = Field(default_factory=list)
    roofs: list[RoofCeiling] = Field(default_factory=list)
    floors: list[Floor] = Field(default_factory=list)
    glazing: list[Glazing] = Field(default_factory=list)
    doors: list[ExternalDoor] = Field(default_factory=list)
    services: Services = Field(default_factory=Services)
    fixtures: Fixtures = Field(default_factory=Fixtures)
    extraction_meta: ExtractionMeta = Field(default_factory=ExtractionMeta)
