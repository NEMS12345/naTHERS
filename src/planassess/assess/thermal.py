"""Indicative NatHERS thermal estimate (national).

A simplified, transparent seasonal heat-balance / degree-day calculation. It is
INDICATIVE ONLY and is NOT the CSIRO Chenath engine — see the caveat carried on
every result and report. Outputs are structured to map onto accredited-software
input categories (envelope conductance, glazing, orientation, climate zone).

Approach (all terms logged as assumptions):
    UA   = Σ(area/R)_opaque + Σ(U·area)_glazing + ventilation conductance
    Q_h  = max(0, UA·HDD·0.0864 − useful gains)      [MJ/yr]
    Q_c  = UA·CDD·0.0864 + solar gain (cooling)        [MJ/yr]
    load = (Q_h + Q_c) / conditioned floor area        [MJ/m².yr]
    star = interpolated against the zone's star-band load thresholds (config)

Missing inputs are never guessed: elements lacking R/U/area are recorded in
``missing_inputs`` (which maps to the gap report) and excluded from UA.
"""

from __future__ import annotations

from pydantic import BaseModel

from ..config.models import Settings, ZoneClimate
from ..constants import INDICATIVE_THERMAL_CAVEAT
from ..model.building import BuildingModel
from ..model.enums import Orientation, ZoneType
from ..model.tracked import TrackedValue

# Seconds-per-day / 1e6 — converts W·(degree-day) to MJ.
_DD_TO_MJ = 0.0864

# Conditioned zone types contribute to the per-m² load denominator.
_CONDITIONED = {ZoneType.LIVING, ZoneType.NIGHT}

# Indicative solar gain weighting by the orientation a window faces.
_SOLAR_WEIGHT = {
    Orientation.N: 1.0,
    Orientation.NE: 0.8,
    Orientation.NW: 0.8,
    Orientation.E: 0.6,
    Orientation.W: 0.6,
    Orientation.SE: 0.4,
    Orientation.SW: 0.4,
    Orientation.S: 0.3,
}


class ThermalResult(BaseModel):
    indicative: bool = True
    computed: bool = False
    climate_zone: int | None = None
    conditioned_floor_area_m2: float | None = None
    ua_w_per_k: float | None = None
    heating_load_mj_per_m2: float | None = None
    cooling_load_mj_per_m2: float | None = None
    total_load_mj_per_m2: float | None = None
    indicative_star: float | None = None
    star_target: float | None = None
    meets_target: bool | None = None
    assumptions: list[str] = []
    missing_inputs: list[str] = []
    notes: list[str] = []
    caveat: str = INDICATIVE_THERMAL_CAVEAT


def _num(tv: TrackedValue, label: str, missing: list[str]) -> float | None:
    """Return a numeric tracked value, or record it as a missing input."""
    if tv is None or tv.is_missing or not isinstance(tv.value, (int, float)):
        missing.append(label)
        return None
    return float(tv.value)


def _star_from_load(load: float, bands: list) -> float:
    """Interpolate an indicative star value from the zone's star-band thresholds.

    Bands give max load to achieve each star (higher star -> lower max load).
    """
    ordered = sorted(bands, key=lambda b: b.star)  # ascending star
    # Below the easiest band's load -> worse than its star.
    if not ordered:
        return 0.0
    if load >= ordered[0].max_load:
        # Extrapolate gently below the lowest tabulated star, floor at 1.
        return round(max(1.0, ordered[0].star - (load - ordered[0].max_load) / ordered[0].max_load), 1)
    for lower, upper in zip(ordered, ordered[1:]):
        # upper has a higher star and a lower max_load.
        if upper.max_load <= load < lower.max_load:
            span = lower.max_load - upper.max_load
            frac = (lower.max_load - load) / span if span else 0.0
            return round(lower.star + frac * (upper.star - lower.star), 1)
    # Better than the best tabulated band.
    return round(min(10.0, ordered[-1].star), 1)


def assess_thermal(
    model: BuildingModel,
    climate: ZoneClimate,
    settings: Settings,
    star_target: float,
) -> ThermalResult:
    tm = settings.thermal
    result = ThermalResult(star_target=star_target)
    missing = result.missing_inputs
    assumptions = result.assumptions

    zone = model.project.climate_zone
    if not zone.is_missing:
        result.climate_zone = int(zone.value)

    # Conditioned floor area (denominator).
    cond_zone_ids = {
        z.id for z in model.zones if not z.type.is_missing and z.type.value in _CONDITIONED
    }
    cond_area = 0.0
    for z in model.zones:
        if z.id in cond_zone_ids:
            a = _num(z.floor_area, f"zones[{z.id}].floor_area", missing)
            if a:
                cond_area += a
    if cond_area <= 0:
        result.computed = False
        result.notes.append(
            "Insufficient data: no conditioned floor area available. "
            "Resolve the flagged inputs (see gap report) and re-run."
        )
        return result
    result.conditioned_floor_area_m2 = round(cond_area, 2)

    # --- Envelope conductance UA -------------------------------------------
    ua = 0.0
    opaque_ua = 0.0  # walls/roof/floor only — used to gate soundness
    for w in model.walls:
        if not w.adjacency.is_missing and w.adjacency.value.value in ("internal", "party"):
            continue  # only external fabric loses heat to ambient
        area = _num(w.area, f"walls[{w.id}].area", missing)
        r = _num(w.r_value, f"walls[{w.id}].r_value", missing)
        if area and r:
            opaque_ua += area / r
    for rf in model.roofs:
        area = _num(rf.area, f"roofs[{rf.id}].area", missing)
        r = _num(rf.r_value, f"roofs[{rf.id}].r_value", missing)
        if area and r:
            opaque_ua += area / r
    for fl in model.floors:
        area = _num(fl.area, f"floors[{fl.id}].area", missing)
        r = _num(fl.r_value, f"floors[{fl.id}].r_value", missing)
        if area and r:
            opaque_ua += area / r
    ua += opaque_ua

    glazing_solar = 0.0
    for g in model.glazing:
        area = _num(g.area, f"glazing[{g.id}].area", missing)
        u = _num(g.u_value, f"glazing[{g.id}].u_value", missing)
        if area and u:
            ua += area * u
        # Solar gain term (best-effort; only when area+SHGC+orientation present).
        shgc = g.shgc.value if not g.shgc.is_missing else None
        orient = g.orientation.value if not g.orientation.is_missing else None
        if area and shgc is not None and orient is not None:
            glazing_solar += area * shgc * _SOLAR_WEIGHT.get(orient, 0.5)

    # Ventilation/infiltration conductance (a method assumption, not plan data).
    total_volume = 0.0
    have_volume = False
    for z in model.zones:
        if z.id in cond_zone_ids and not z.volume.is_missing:
            total_volume += float(z.volume.value)
            have_volume = True
    if have_volume:
        vent_ua = 0.33 * tm.air_changes_per_hour * total_volume
        ua += vent_ua
        assumptions.append(
            f"Ventilation conductance from assumed {tm.air_changes_per_hour} ACH "
            f"over {round(total_volume,1)} m³ conditioned volume."
        )
    else:
        result.notes.append(
            "Conditioned-zone volumes unavailable; ventilation heat loss omitted "
            "(estimate is conservative-low). Confirm ceiling heights."
        )

    # Soundness gate: a star from glazing conductance alone (no wall/roof/floor
    # R-values) would be misleadingly optimistic, so refuse it rather than guess.
    if opaque_ua <= 0:
        result.computed = False
        result.notes.append(
            "Insufficient opaque-envelope data: no usable wall, roof or floor "
            "R-values. An indicative star cannot be produced from glazing alone — "
            "provide the flagged R-values (see gap report) and re-run."
        )
        return result
    if ua <= 0:
        result.computed = False
        result.notes.append(
            "Insufficient envelope data to estimate conductance. See gap report."
        )
        return result
    result.ua_w_per_k = round(ua, 2)

    # --- Seasonal loads -----------------------------------------------------
    internal_gain_annual_mj = (
        tm.internal_gain_w_per_m2 * cond_area * 8.76 * 3.6  # W * h/yr(8760) -> MJ: W*8760h*3600s/1e6
    )
    assumptions.append(
        f"Internal gains assumed {tm.internal_gain_w_per_m2} W/m² over conditioned area."
    )
    assumptions.append(
        f"Heating degree days {climate.heating_degree_days}, cooling degree days "
        f"{climate.cooling_degree_days} (indicative, climate zone "
        f"{result.climate_zone if result.climate_zone is not None else 'unknown'})."
    )

    q_fabric_heat = ua * climate.heating_degree_days * _DD_TO_MJ
    useful_gains = tm.heating_utilisation_factor * (internal_gain_annual_mj + glazing_solar * tm.solar_gain_factor)
    q_heat = max(0.0, q_fabric_heat - useful_gains)

    q_fabric_cool = ua * climate.cooling_degree_days * _DD_TO_MJ
    q_solar_cool = glazing_solar * tm.solar_gain_factor * climate.solar_irradiance_factor
    q_cool = q_fabric_cool + q_solar_cool

    result.heating_load_mj_per_m2 = round(q_heat / cond_area, 1)
    result.cooling_load_mj_per_m2 = round(q_cool / cond_area, 1)
    total = result.heating_load_mj_per_m2 + result.cooling_load_mj_per_m2
    result.total_load_mj_per_m2 = round(total, 1)

    result.indicative_star = _star_from_load(total, climate.star_bands)
    result.meets_target = result.indicative_star >= star_target
    result.computed = True

    if missing:
        result.notes.append(
            f"{len(set(missing))} envelope input(s) were missing and excluded from the "
            "estimate; the indicative star is therefore optimistic. See gap report."
        )
    return result
