"""P2 assessment logic: indicative thermal, BASIX categories, WoH score."""

from __future__ import annotations

from pathlib import Path

import pytest

from planassess.assess.basix import assess_basix, assess_water
from planassess.assess.thermal import assess_thermal
from planassess.assess.woh import assess_woh
from planassess.config.loader import load_climate_data, load_jurisdictions, load_settings
from planassess.model.enums import Provenance
from planassess.model.tracked import missing, observed
from planassess.samples import synthetic_house

CONFIG = Path(__file__).resolve().parents[1] / "config"


@pytest.fixture()
def settings():
    return load_settings(CONFIG)


@pytest.fixture()
def climate_default():
    return load_climate_data(CONFIG).default


# --- thermal -----------------------------------------------------------------


def test_thermal_computes_for_complete_envelope(settings, climate_default):
    model = synthetic_house()
    model.project.climate_zone = observed(56, Provenance.DERIVED, 0.9)
    result = assess_thermal(model, climate_default, settings, star_target=7.0)
    assert result.computed
    assert result.indicative is True
    assert result.ua_w_per_k > 0
    assert result.total_load_mj_per_m2 == pytest.approx(
        result.heating_load_mj_per_m2 + result.cooling_load_mj_per_m2, abs=0.2
    )
    assert 0 < result.indicative_star <= 10


def test_thermal_flags_missing_envelope_inputs(settings, climate_default):
    model = synthetic_house()
    # Strip all roof R-values -> recorded as missing inputs, not guessed.
    for rf in model.roofs:
        rf.r_value = missing(unit="m2.K/W")
    result = assess_thermal(model, climate_default, settings, star_target=7.0)
    assert any("r_value" in m for m in result.missing_inputs)


def test_thermal_not_computable_without_floor_area(settings, climate_default):
    model = synthetic_house()
    for z in model.zones:
        z.floor_area = missing(unit="m2")
    result = assess_thermal(model, climate_default, settings, star_target=7.0)
    assert result.computed is False
    assert result.indicative_star is None


def test_better_insulation_improves_star(settings, climate_default):
    base = synthetic_house()
    base.project.climate_zone = observed(56, Provenance.DERIVED, 0.9)
    better = synthetic_house()
    better.project.climate_zone = observed(56, Provenance.DERIVED, 0.9)
    for rf in better.roofs:
        rf.r_value = observed(6.0, Provenance.SCHEDULE, 0.8, unit="m2.K/W")
    for w in better.walls:
        w.r_value = observed(4.0, Provenance.SCHEDULE, 0.8, unit="m2.K/W")
    r_base = assess_thermal(base, climate_default, settings, 7.0)
    r_better = assess_thermal(better, climate_default, settings, 7.0)
    assert r_better.indicative_star >= r_base.indicative_star


# --- BASIX -------------------------------------------------------------------


def test_basix_returns_three_categories():
    cfg = load_jurisdictions(CONFIG).for_state("NSW").basix
    cats = assess_basix(synthetic_house(), cfg)
    assert {c.name for c in cats} == {"Energy", "Water", "Thermal Comfort"}


def test_basix_water_missing_fixtures_is_conservative_and_flagged():
    cfg = load_jurisdictions(CONFIG).for_state("NSW").basix
    cat = assess_water(synthetic_house(), cfg, target_pct=40)
    # No WELS fixtures in the sample -> 0% credited, flagged, fails target.
    assert cat.value == 0.0
    assert cat.passed is False
    assert "fixtures.wels_showers" in cat.missing_inputs


def test_basix_water_credits_good_fixtures():
    cfg = load_jurisdictions(CONFIG).for_state("NSW").basix
    model = synthetic_house()
    model.fixtures.wels_showers = observed(4, Provenance.SCHEDULE, 0.9, unit="stars")
    model.fixtures.wels_taps = observed(6, Provenance.SCHEDULE, 0.9, unit="stars")
    model.fixtures.wels_toilets = observed(5, Provenance.SCHEDULE, 0.9, unit="stars")
    model.fixtures.rainwater_tank_l = observed(5000, Provenance.SCHEDULE, 0.9, unit="L")
    cat = assess_water(model, cfg, target_pct=40)
    assert cat.value > 0
    assert cat.value > assess_water(synthetic_house(), cfg, 40).value


def test_basix_thermal_comfort_flags_simulation_for_large_glazing():
    cfg = load_jurisdictions(CONFIG).for_state("NSW").basix
    model = synthetic_house()
    # Inflate glazing area beyond the DTS ratio to trigger the simulation note.
    model.glazing[0].area = observed(40.0, Provenance.SCHEDULE, 0.8, unit="m2")
    cats = assess_basix(model, cfg)
    tc = next(c for c in cats if c.name == "Thermal Comfort")
    assert any("Simulation" in n for n in tc.notes)


# --- WoH ---------------------------------------------------------------------


def test_woh_score_in_range_and_pv_helps():
    base = synthetic_house()
    no_pv = synthetic_house()
    no_pv.services.solar_pv_kw = missing(unit="kW")
    r_base = assess_woh(base, benchmark_score=60)
    r_no_pv = assess_woh(no_pv, benchmark_score=60)
    assert 0 <= r_base.value <= 100
    assert r_base.value >= r_no_pv.value  # PV should not reduce the score


def test_woh_flags_missing_services():
    model = synthetic_house()
    model.services.lighting = missing()
    cat = assess_woh(model, benchmark_score=60)
    assert "services.lighting" in cat.missing_inputs
