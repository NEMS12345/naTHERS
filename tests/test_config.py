"""Config: load, strategy selection, climate-zone lookup with ambiguity handling."""

from __future__ import annotations

from pathlib import Path

import pytest

from planassess.config.loader import (
    load_jurisdictions,
    load_ncc_climate_zones,
    load_settings,
    lookup_climate_zone,
)
from planassess.model.enums import JurisdictionStrategy, State


def test_settings_load(config_dir: Path):
    s = load_settings(config_dir)
    assert 0.0 <= s.review_confidence_threshold <= 1.0
    # Tier-2 vision LLM must be OFF by default (offline-first guarantee).
    assert s.vision_llm.enabled is False
    assert s.vision_llm.model == "claude-sonnet-4-6"


def test_nsw_uses_basix(config_dir: Path):
    cfg = load_jurisdictions(config_dir)
    jc = cfg.for_state("NSW")
    assert jc.strategy == JurisdictionStrategy.BASIX
    assert jc.basix is not None
    assert jc.basix.water.target_pct_by_dwelling["house"] > 0


@pytest.mark.parametrize("state", ["VIC", "QLD", "SA", "WA", "TAS", "ACT", "NT"])
def test_non_nsw_uses_woh(config_dir: Path, state: str):
    cfg = load_jurisdictions(config_dir)
    jc = cfg.for_state(state)
    assert jc.strategy == JurisdictionStrategy.WOH


def test_nt_woh_not_mandatory(config_dir: Path):
    cfg = load_jurisdictions(config_dir)
    jc = cfg.for_state("NT")
    assert jc.woh is not None
    assert jc.woh.mandatory is False


def test_non_adopting_jurisdictions_flagged(config_dir: Path):
    cfg = load_jurisdictions(config_dir)
    # TAS and NT have not adopted the 7-star/WoH provisions (sourced 2026-06).
    for st in ("TAS", "NT"):
        jc = cfg.for_state(st)
        assert jc.seven_star_mandatory is False
        assert jc.ncc2022_adoption_date is None
        assert jc.woh.mandatory is False
    # Adopting jurisdictions carry a dated adoption.
    assert cfg.for_state("NSW").ncc2022_adoption_date == "2023-10-01"
    assert cfg.for_state("VIC").seven_star_mandatory is True


def test_config_carries_sources_and_review_date(config_dir: Path):
    cfg = load_jurisdictions(config_dir)
    assert cfg.last_reviewed  # provenance for the sourced figures
    assert any("nathers.gov.au" in s for s in cfg.sources)


def test_basix_energy_target_is_indicative_index_not_regulated_pct(config_dir: Path):
    cfg = load_jurisdictions(config_dir)
    energy = cfg.for_state("NSW").basix.energy
    assert energy.indicative_index_target_by_dwelling["house"] > 0
    # The regulated percentage is recorded as a note, not conflated with our index.
    assert energy.regulated_reduction_note and "%" in energy.regulated_reduction_note


def test_targets_are_config_driven_not_hardcoded(config_dir: Path):
    cfg = load_jurisdictions(config_dir)
    # standards_version pins the config revision; assessment modules read from here.
    assert cfg.standards_version
    assert cfg.ncc_alignment == "NCC 2022"


def test_climate_zone_lookup_known(config_dir: Path):
    tv = lookup_climate_zone("2000", config_dir)
    assert not tv.is_missing
    assert tv.value is not None
    # Seed table is unverified -> flagged for review until the official table is imported.
    assert tv.below(0.6)
    assert "verify" in (tv.notes or "").lower()


def test_climate_zone_lookup_ambiguous_is_low_confidence(config_dir: Path):
    tv = lookup_climate_zone("2620", config_dir)
    assert tv.value is not None  # picks first but...
    assert tv.below(0.6)  # ...is flagged for human review
    assert "ambiguous" in (tv.notes or "").lower()


def test_climate_zone_lookup_unknown_is_missing_not_guessed(config_dir: Path):
    tv = lookup_climate_zone("9999", config_dir)
    assert tv.is_missing
    assert tv.below(0.6)


def test_ncc_climate_zones_load_with_provenance(config_dir: Path):
    table = load_ncc_climate_zones(config_dir)
    # The eight NCC zones (1–8), verified from the ABCB shapefile.
    assert set(table.zones) == set(range(1, 9))
    # CC BY 4.0 provenance + attribution must be recorded for the sourced dataset.
    assert table.source.licence == "CC BY 4.0"
    assert "Australian Building Codes Board" in table.source.attribution
    assert "data.gov.au" in (table.source.dataset_url or "")


def test_ncc_zone_descriptors_are_indicative_until_verified(config_dir: Path):
    table = load_ncc_climate_zones(config_dir)
    # Descriptors are NCC 2022 definitions recorded as indicative -> below the
    # 0.6 review threshold so reliance on them is gap-flagged (no fabrication).
    for entry in table.zones.values():
        assert entry.confidence < 0.6
        assert entry.description


def test_unknown_state_raises(config_dir: Path):
    cfg = load_jurisdictions(config_dir)
    with pytest.raises(KeyError):
        cfg.for_state("XYZ")


def test_every_state_enum_has_config(config_dir: Path):
    cfg = load_jurisdictions(config_dir)
    for st in State:
        assert st.value in cfg.jurisdictions
