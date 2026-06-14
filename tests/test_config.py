"""Config: load, strategy selection, climate-zone lookup with ambiguity handling."""

from __future__ import annotations

from pathlib import Path

import pytest

from planassess.config.loader import (
    load_jurisdictions,
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


def test_targets_are_config_driven_not_hardcoded(config_dir: Path):
    cfg = load_jurisdictions(config_dir)
    # standards_version pins the config revision; assessment modules read from here.
    assert cfg.standards_version
    assert cfg.ncc_alignment == "NCC 2022"


def test_climate_zone_lookup_known(config_dir: Path):
    tv = lookup_climate_zone("2000", config_dir)
    assert tv.value == 56
    assert tv.confidence >= 0.6
    assert not tv.is_missing


def test_climate_zone_lookup_ambiguous_is_low_confidence(config_dir: Path):
    tv = lookup_climate_zone("2620", config_dir)
    assert tv.value is not None  # picks first but...
    assert tv.below(0.6)  # ...is flagged for human review
    assert "ambiguous" in (tv.notes or "").lower()


def test_climate_zone_lookup_unknown_is_missing_not_guessed(config_dir: Path):
    tv = lookup_climate_zone("9999", config_dir)
    assert tv.is_missing
    assert tv.below(0.6)


def test_unknown_state_raises(config_dir: Path):
    cfg = load_jurisdictions(config_dir)
    with pytest.raises(KeyError):
        cfg.for_state("XYZ")


def test_every_state_enum_has_config(config_dir: Path):
    cfg = load_jurisdictions(config_dir)
    for st in State:
        assert st.value in cfg.jurisdictions
