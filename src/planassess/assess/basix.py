"""NSW BASIX pre-assessment: Energy, Water, Thermal Comfort.

INDICATIVE pre-assessment only. A real BASIX certificate issues solely via the
NSW Planning Portal; this estimates the three BASIX caps for data-prep and to
surface likely shortfalls early. Targets come from config (per dwelling type).
Missing inputs are flagged, never guessed.
"""

from __future__ import annotations

from ..config.models import BasixConfig
from ..model.building import BuildingModel
from ..model.enums import DwellingType, Orientation
from .results import CategoryResult
from .scoring import (
    COOKTOP_FACTORS,
    HOT_WATER_FACTORS,
    HVAC_FACTORS,
    score_text,
)

# Indicative end-use shares of household potable water (sum to 1.0).
_WATER_SHARES = {"showers": 0.35, "toilets": 0.20, "taps": 0.15, "laundry": 0.15, "outdoor": 0.15}

# Indicative emissions shares for the BASIX energy proxy (sum to 1.0).
_ENERGY_SHARES = {"hot_water": 0.30, "hvac": 0.40, "cooking": 0.10, "other": 0.20}


def _dwelling_type(model: BuildingModel) -> DwellingType:
    for d in model.dwellings:
        if not d.type.is_missing:
            return d.type.value
    return DwellingType.HOUSE


def _stars_reduction(stars: float | None, max_stars: float, cap: float) -> float:
    """Fractional reduction for a WELS-rated fixture, 0 at 1 star up to ``cap``."""
    if stars is None:
        return 0.0
    return max(0.0, min(cap, (stars - 1) / (max_stars - 1) * cap))


def assess_water(model: BuildingModel, cfg: BasixConfig, target_pct: float) -> CategoryResult:
    cat = CategoryResult(name="Water", target=target_pct, unit="% potable reduction", method="BASIX")
    fx = model.fixtures
    reduction = 0.0

    showers = fx.wels_showers.value if not fx.wels_showers.is_missing else None
    taps = fx.wels_taps.value if not fx.wels_taps.is_missing else None
    toilets = fx.wels_toilets.value if not fx.wels_toilets.is_missing else None
    if showers is None:
        cat.missing_inputs.append("fixtures.wels_showers")
    if taps is None:
        cat.missing_inputs.append("fixtures.wels_taps")
    if toilets is None:
        cat.missing_inputs.append("fixtures.wels_toilets")

    reduction += _WATER_SHARES["showers"] * _stars_reduction(showers, 4, 0.45)
    reduction += _WATER_SHARES["taps"] * _stars_reduction(taps, 6, 0.45)
    reduction += _WATER_SHARES["toilets"] * _stars_reduction(toilets, 5, 0.60)

    # Rainwater tank offsets toilet+laundry+outdoor end uses.
    tank = fx.rainwater_tank_l.value if not fx.rainwater_tank_l.is_missing else None
    if tank is None:
        cat.missing_inputs.append("fixtures.rainwater_tank_l")
    else:
        offsettable = _WATER_SHARES["toilets"] + _WATER_SHARES["laundry"] + _WATER_SHARES["outdoor"]
        tank_fraction = min(1.0, tank / 10000.0)  # ~10 kL ≈ full offset of those uses (indicative)
        reduction += offsettable * tank_fraction * 0.8
        cat.assumptions.append("Rainwater tank assumed plumbed to toilets, laundry and outdoor.")

    # Drought-tolerant / native landscaping reduces the outdoor share.
    land = fx.landscaping_type.value if not fx.landscaping_type.is_missing else None
    if land and any(k in land.lower() for k in ("native", "drought", "low water", "xeric")):
        reduction += _WATER_SHARES["outdoor"] * 0.5
        cat.assumptions.append("Low-water landscaping credited against outdoor use.")
    elif land is None:
        cat.missing_inputs.append("fixtures.landscaping_type")

    value = round(reduction * 100, 1)
    cat.value = value
    cat.margin = round(value - target_pct, 1)
    cat.passed = value >= target_pct
    if cat.missing_inputs:
        cat.notes.append(
            "Missing fixture inputs were treated as no-credit; the estimate is "
            "conservative-low and may improve once confirmed."
        )
    return cat


def assess_energy(model: BuildingModel, cfg: BasixConfig, target_pct: float) -> CategoryResult:
    cat = CategoryResult(name="Energy", target=target_pct, unit="% emissions reduction", method="BASIX")
    s = model.services
    reduction = 0.0

    hw = score_text(s.hot_water.value, HOT_WATER_FACTORS) if not s.hot_water.is_missing else None
    hvac = score_text(s.heating.value, HVAC_FACTORS) if not s.heating.is_missing else None
    cook = score_text(s.cooktop.value, COOKTOP_FACTORS) if not s.cooktop.is_missing else None

    if hw is None:
        cat.missing_inputs.append("services.hot_water")
    else:
        reduction += _ENERGY_SHARES["hot_water"] * hw
    if hvac is None:
        cat.missing_inputs.append("services.heating")
    else:
        reduction += _ENERGY_SHARES["hvac"] * hvac
    if cook is None:
        cat.missing_inputs.append("services.cooktop")
    else:
        reduction += _ENERGY_SHARES["cooking"] * cook

    # On-site PV offsets emissions across the board.
    pv = s.solar_pv_kw.value if not s.solar_pv_kw.is_missing else None
    if pv is None:
        cat.missing_inputs.append("services.solar_pv_kw")
    else:
        reduction += min(0.40, pv * 0.05)  # ~ 8 kW saturates the indicative PV credit
        cat.assumptions.append(f"{pv} kW PV credited (indicative cap at ~8 kW).")

    value = round(reduction * 100, 1)
    cat.value = value
    cat.margin = round(value - target_pct, 1)
    cat.passed = value >= target_pct
    return cat


def assess_thermal_comfort(model: BuildingModel, cfg: BasixConfig) -> CategoryResult:
    dts = cfg.thermal_comfort.dts
    cat = CategoryResult(
        name="Thermal Comfort", method=cfg.thermal_comfort.method, unit="DTS elemental"
    )
    checks: list[tuple[str, bool | None]] = []

    # Ceiling/roof R.
    for rf in model.roofs:
        if rf.r_value.is_missing:
            cat.missing_inputs.append(f"roofs[{rf.id}].r_value")
            checks.append((f"roof {rf.id} R≥{dts.min_ceiling_r}", None))
        else:
            checks.append((f"roof {rf.id} R≥{dts.min_ceiling_r}", rf.r_value.value >= dts.min_ceiling_r))
    # External wall R.
    for w in model.walls:
        if not w.adjacency.is_missing and w.adjacency.value.value in ("internal", "party"):
            continue
        if w.r_value.is_missing:
            cat.missing_inputs.append(f"walls[{w.id}].r_value")
        else:
            checks.append((f"wall {w.id} R≥{dts.min_wall_r}", w.r_value.value >= dts.min_wall_r))
    # Glazing U / SHGC.
    for g in model.glazing:
        if not g.u_value.is_missing:
            checks.append((f"glazing {g.id} U≤{dts.max_glazing_u}", g.u_value.value <= dts.max_glazing_u))
        else:
            cat.missing_inputs.append(f"glazing[{g.id}].u_value")
        if not g.shgc.is_missing and not g.orientation.is_missing:
            if g.orientation.value in (Orientation.W, Orientation.NW, Orientation.SW):
                checks.append(
                    (f"glazing {g.id} west SHGC≤{dts.max_glazing_shgc}", g.shgc.value <= dts.max_glazing_shgc)
                )

    assessed = [(label, ok) for label, ok in checks if ok is not None]
    failed = [label for label, ok in assessed if ok is False]
    cat.notes.extend(f"FAIL: {label}" for label in failed)

    # Glazing-area ratio -> recommend Simulation/NatHERS method instead of DTS.
    glaz_area = sum(g.area.value for g in model.glazing if not g.area.is_missing)
    floor_area = sum(z.floor_area.value for z in model.zones if not z.floor_area.is_missing)
    if floor_area > 0 and glaz_area / floor_area > dts.max_glazing_area_ratio:
        cat.notes.append(
            f"Glazing/floor ratio {glaz_area/floor_area:.0%} exceeds DTS limit "
            f"{dts.max_glazing_area_ratio:.0%} — the Simulation (NatHERS) method is "
            "likely required instead of DIY deemed-to-satisfy."
        )

    if not assessed:
        cat.passed = None
        cat.notes.append("Not enough envelope data to run DTS checks — see gap report.")
    else:
        cat.passed = len(failed) == 0
        cat.value = round(100 * (len(assessed) - len(failed)) / len(assessed), 0)
        cat.unit = "% DTS elements passed"
    return cat


def assess_basix(model: BuildingModel, cfg: BasixConfig, dwelling_type: DwellingType | None = None) -> list[CategoryResult]:
    dt = (dwelling_type or _dwelling_type(model)).value
    water_target = cfg.water.target_pct_by_dwelling.get(dt, 40)
    energy_target = cfg.energy.target_pct_by_dwelling.get(dt, 50)
    return [
        assess_energy(model, cfg, energy_target),
        assess_water(model, cfg, water_target),
        assess_thermal_comfort(model, cfg),
    ]
