"""NatHERS Whole-of-Home (WoH) pre-assessment (all states/territories except NSW).

INDICATIVE pre-assessment only. The official WoH score comes from accredited
software running the full method; this estimates an indicative 0–100 WoH score
from the modelled services, on-site generation and thermal loads, for data-prep
and early shortfall detection. NT: WoH is not mandatory (handled upstream).

Higher score = better. The indicative score starts from a neutral baseline and
is adjusted by the efficiency of each WoH end use; missing inputs are flagged and
left neutral, never guessed.
"""

from __future__ import annotations

from ..model.building import BuildingModel
from .results import CategoryResult
from .scoring import COOKTOP_FACTORS, HOT_WATER_FACTORS, HVAC_FACTORS, score_text
from .thermal import ThermalResult

# Indicative weighting of WoH end uses toward the score (sum to 1.0).
_WOH_WEIGHTS = {
    "heating_cooling": 0.35,
    "hot_water": 0.20,
    "lighting": 0.05,
    "pool_spa": 0.05,
    "cooking_plug": 0.10,
    "pv_battery": 0.25,
}

_BASELINE = 50.0  # neutral starting score before efficiency adjustments


def assess_woh(
    model: BuildingModel,
    benchmark_score: float,
    thermal: ThermalResult | None = None,
) -> CategoryResult:
    cat = CategoryResult(
        name="Whole-of-Home", target=benchmark_score, unit="WoH score (0-100, indicative)",
        method="NatHERS WoH",
    )
    s = model.services
    score = _BASELINE

    # Heating/cooling: better thermal performance lifts the score.
    if thermal and thermal.computed and thermal.indicative_star is not None:
        # Centre on a 7-star reference; ±1 star ≈ ±7 points on this component.
        delta = (thermal.indicative_star - 7.0) * 7.0
        score += _WOH_WEIGHTS["heating_cooling"] * delta / 0.35  # scale into the component
        cat.assumptions.append(
            f"Heating/cooling component from indicative {thermal.indicative_star}-star thermal estimate."
        )
    else:
        cat.missing_inputs.append("thermal (indicative star) — heating/cooling component unscored")

    def _apply(value, table, weight_key, label, field):
        nonlocal score
        factor = score_text(value, table) if value else None
        if factor is None:
            cat.missing_inputs.append(field)
            return
        score += _WOH_WEIGHTS[weight_key] * (factor - 0.3) * 100  # 0.3 ≈ baseline efficiency

    _apply(s.hot_water.value if not s.hot_water.is_missing else None,
            HOT_WATER_FACTORS, "hot_water", "hot water", "services.hot_water")
    _apply(s.heating.value if not s.heating.is_missing else None,
            HVAC_FACTORS, "heating_cooling", "hvac", "services.heating")
    _apply(s.cooktop.value if not s.cooktop.is_missing else None,
            COOKTOP_FACTORS, "cooking_plug", "cooktop", "services.cooktop")

    # Lighting: LED assumed beneficial if stated.
    if not s.lighting.is_missing and "led" in str(s.lighting.value).lower():
        score += _WOH_WEIGHTS["lighting"] * 100 * 0.5
    elif s.lighting.is_missing:
        cat.missing_inputs.append("services.lighting")

    # Pool/spa is a penalty when present (pumps add load).
    if not s.pool_spa.is_missing and s.pool_spa.value and "none" not in str(s.pool_spa.value).lower():
        score -= _WOH_WEIGHTS["pool_spa"] * 100 * 0.6
        cat.assumptions.append("Pool/spa pump load applied as a penalty.")

    # On-site PV + battery: strong positive.
    pv = s.solar_pv_kw.value if not s.solar_pv_kw.is_missing else None
    if pv is None:
        cat.missing_inputs.append("services.solar_pv_kw")
    else:
        score += _WOH_WEIGHTS["pv_battery"] * 100 * min(1.0, pv / 8.0)
        cat.assumptions.append(f"{pv} kW PV credited toward WoH (indicative cap ~8 kW).")
    if not s.battery_kwh.is_missing and s.battery_kwh.value:
        score += 3.0
        cat.assumptions.append(f"{s.battery_kwh.value} kWh battery credited.")

    value = round(max(0.0, min(100.0, score)), 0)
    cat.value = value
    cat.margin = round(value - benchmark_score, 1)
    cat.passed = value >= benchmark_score
    if cat.missing_inputs:
        cat.notes.append(
            "Unscored end uses were left neutral; confirm the flagged services to "
            "firm up the indicative WoH score."
        )
    return cat
