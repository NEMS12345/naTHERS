"""Synthetic sample Building Models for P0 tests and CLI demos.

The DXF *adapter* arrives in P1; for P0 we construct the canonical model directly
so the extract -> review -> assess -> report pipeline can be exercised end to end.
The sample deliberately includes a mix of high-confidence, low-confidence and
missing fields so the review gate has something to flag.
"""

from __future__ import annotations

from .model.building import (
    BuildingModel,
    Dwelling,
    Glazing,
    Project,
    RoofCeiling,
    Services,
    Site,
    Wall,
    Zone,
)
from .model.enums import (
    DwellingType,
    Orientation,
    Provenance,
    RoofType,
    State,
    WallAdjacency,
    ZoneType,
)
from .model.tracked import missing, observed


def synthetic_house(project_id: str = "SAMPLE-HOUSE-001", postcode: str = "2000") -> BuildingModel:
    """A small single-storey NSW house with a couple of deliberate gaps."""
    dwelling = Dwelling(
        id="D1",
        type=observed(DwellingType.HOUSE, Provenance.DXF_TEXT, 0.9),
        storeys=observed(1, Provenance.DXF_TEXT, 0.85),
    )

    living = Zone(
        id="Z1",
        dwelling_id="D1",
        name=observed("Living/Kitchen", Provenance.DXF_TEXT, 0.9),
        type=observed(ZoneType.LIVING, Provenance.DXF_TEXT, 0.85),
        floor_area=observed(48.0, Provenance.DXF_GEOMETRY, 0.8, unit="m2"),
        ceiling_height=observed(2.7, Provenance.DXF_TEXT, 0.7, unit="m"),
        volume=observed(129.6, Provenance.DERIVED, 0.7, unit="m3"),
    )
    bed = Zone(
        id="Z2",
        dwelling_id="D1",
        name=observed("Bedrooms", Provenance.DXF_TEXT, 0.9),
        type=observed(ZoneType.NIGHT, Provenance.DXF_TEXT, 0.85),
        floor_area=observed(36.0, Provenance.DXF_GEOMETRY, 0.8, unit="m2"),
        # deliberately low confidence -> should be gap-flagged
        ceiling_height=observed(2.7, Provenance.DXF_GEOMETRY, 0.4, unit="m"),
        volume=missing(unit="m3", notes="Not derivable until ceiling height confirmed."),
    )

    north_wall = Wall(
        id="W1",
        zone_id="Z1",
        construction=observed("Brick veneer", Provenance.DXF_TEXT, 0.8),
        r_value=observed(2.8, Provenance.SCHEDULE, 0.7, unit="m2.K/W"),
        area=observed(21.6, Provenance.DXF_GEOMETRY, 0.8, unit="m2"),
        orientation=observed(Orientation.N, Provenance.DXF_GEOMETRY, 0.85),
        adjacency=observed(WallAdjacency.EXTERNAL, Provenance.DXF_GEOMETRY, 0.9),
    )

    roof = RoofCeiling(
        id="R1",
        zone_id="Z1",
        roof_type=observed(RoofType.PITCHED, Provenance.DXF_TEXT, 0.8),
        construction=observed("Concrete tile, ceiling insulation", Provenance.DXF_TEXT, 0.7),
        r_value=observed(4.1, Provenance.SCHEDULE, 0.7, unit="m2.K/W"),
        area=observed(84.0, Provenance.DXF_GEOMETRY, 0.75, unit="m2"),
        # missing colour -> absorptance can't be derived -> gap
        colour=missing(notes="Roof colour/finish not annotated on plan."),
        solar_absorptance=missing(notes="Depends on roof colour."),
    )

    n_window = Glazing(
        id="G1",
        zone_id="Z1",
        wall_id="W1",
        orientation=observed(Orientation.N, Provenance.DXF_GEOMETRY, 0.85),
        area=observed(6.0, Provenance.SCHEDULE, 0.8, unit="m2"),
        frame=observed("Aluminium", Provenance.SCHEDULE, 0.8),
        glazing_type=observed("Double, clear", Provenance.SCHEDULE, 0.7),
        u_value=observed(3.9, Provenance.SCHEDULE, 0.6, unit="W/m2.K"),
        shgc=observed(0.5, Provenance.SCHEDULE, 0.6),
        eave_shading_depth=observed(0.6, Provenance.DXF_GEOMETRY, 0.5, unit="m"),
    )

    services = Services(
        hot_water=observed("Heat pump", Provenance.DXF_TEXT, 0.7),
        heating=observed("Reverse-cycle split", Provenance.DXF_TEXT, 0.7),
        cooling=observed("Reverse-cycle split", Provenance.DXF_TEXT, 0.7),
        solar_pv_kw=observed(6.6, Provenance.DXF_TEXT, 0.8, unit="kW"),
        battery_kwh=missing(unit="kWh", notes="No battery shown on plan."),
    )

    return BuildingModel(
        project=Project(
            id=project_id,
            address=observed("1 Example St, Sydney NSW", Provenance.DXF_TEXT, 0.7),
            state=observed(State.NSW, Provenance.DXF_TEXT, 0.9),
            postcode=observed(postcode, Provenance.DXF_TEXT, 0.9),
            # climate_zone left missing here; CLI fills it via national lookup.
            climate_zone=missing(notes="To be resolved by postcode lookup."),
        ),
        site=Site(
            site_area=observed(450.0, Provenance.DXF_GEOMETRY, 0.7, unit="m2"),
            north_angle_deg=observed(0.0, Provenance.DXF_GEOMETRY, 0.6, unit="deg"),
            roof_plan_area=observed(84.0, Provenance.DXF_GEOMETRY, 0.7, unit="m2"),
        ),
        dwellings=[dwelling],
        zones=[living, bed],
        walls=[north_wall],
        roofs=[roof],
        glazing=[n_window],
        services=services,
    )
