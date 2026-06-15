"""Unit test for the NCC postcode-crosswalk builder's aggregation logic.

Exercises the {postcode: [zones]} -> yaml mapping without needing the (large,
gov-hosted) GIS inputs or shapely/pyshp: a postcode intersecting a single NCC
zone becomes a derived `postcodes` entry; one intersecting several becomes a
low-confidence `ambiguous` entry so it is gap-flagged.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_ncc_zone_table.py"
_spec = importlib.util.spec_from_file_location("build_ncc", _SCRIPT)
build_ncc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_ncc)


def test_single_and_multi_zone_records():
    records = {
        "0800": [1],            # single -> postcodes
        "2620": [7, 8],         # multi  -> ambiguous
        "3000": [6, 6],         # duplicate collapses -> single
        "9999": [0, 99],        # out-of-range zones dropped -> skipped
    }
    postcodes, ambiguous = build_ncc.to_table(records)
    assert postcodes["0800"] == {"zone": 1, "confidence": build_ncc.SINGLE_ZONE_CONFIDENCE}
    assert postcodes["3000"]["zone"] == 6
    assert ambiguous["2620"]["zones"] == [7, 8]
    assert ambiguous["2620"]["confidence"] < 0.6
    assert "9999" not in postcodes and "9999" not in ambiguous


def test_single_zone_confidence_below_official_table():
    # Derived spatial join must not claim the 0.9 of the official NatHERS table.
    assert build_ncc.SINGLE_ZONE_CONFIDENCE < 0.9


def test_yaml_is_well_formed_and_attributed():
    import yaml

    postcodes, ambiguous = build_ncc.to_table({"0800": [1], "2620": [7, 8]})
    text = build_ncc.to_yaml(postcodes, ambiguous, "zones.shp x poa.shp")
    doc = yaml.safe_load(text)
    assert doc["version"].startswith("abcb-ncc-derived-")
    assert "CC BY 4.0" in doc["attribution"]
    assert doc["postcodes"]["0800"]["zone"] == 1
    assert doc["ambiguous"]["2620"]["zones"] == [7, 8]
