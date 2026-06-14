"""Unit test for the NatHERS postcode-table builder's parse logic.

Exercises the row->yaml mapping without needing the official (gov-hosted) file:
single-zone postcodes become high-confidence entries; multi-zone postcodes become
low-confidence `ambiguous` entries so they are gap-flagged.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_climate_zone_table.py"
_spec = importlib.util.spec_from_file_location("build_cz", _SCRIPT)
build_cz = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_cz)


def test_single_and_multi_zone_rows():
    rows = [
        ["Postcode", "Primary", "Secondary", "Tertiary"],
        ["0800", "1", "", ""],          # single -> postcodes
        ["2620", "24", "62", ""],       # multi  -> ambiguous
        ["abc", "5", "", ""],           # invalid postcode -> skipped
        ["3000", "60", "60", ""],       # duplicate zone collapses -> single
    ]
    postcodes, ambiguous = build_cz.build(rows)
    assert postcodes["0800"] == {"zone": 1, "confidence": 0.9}
    assert postcodes["3000"]["zone"] == 60
    assert ambiguous["2620"]["zones"] == [24, 62]
    assert ambiguous["2620"]["confidence"] < 0.6
    assert "abc" not in postcodes and "abc" not in ambiguous


def test_yaml_round_trips_into_loader(tmp_path: Path):
    import yaml

    from planassess.config.models import ClimateZoneTable

    postcodes, ambiguous = build_cz.build([
        ["Postcode", "Primary", "Secondary"],
        ["0800", "1", ""],
        ["2620", "24", "62"],
    ])
    text = build_cz.to_yaml(postcodes, ambiguous, "test.xlsx")
    table = ClimateZoneTable.model_validate(yaml.safe_load(text))
    assert table.postcodes["0800"].zone == 1
    assert table.ambiguous["2620"].zones == [24, 62]
