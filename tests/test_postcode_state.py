"""Postcode -> state/territory derivation (Australia Post ranges)."""

from __future__ import annotations

import pytest

from planassess.config.postcode_state import state_from_postcode
from planassess.model.enums import State


@pytest.mark.parametrize(
    "postcode,expected",
    [
        ("2000", State.NSW),   # Sydney
        ("2600", State.ACT),   # Canberra (ACT pocket inside NSW range)
        ("2619", State.NSW),   # Queanbeyan (back to NSW)
        ("0800", State.NT),    # Darwin
        ("3000", State.VIC),   # Melbourne
        ("4000", State.QLD),   # Brisbane
        ("5000", State.SA),    # Adelaide
        ("6000", State.WA),    # Perth
        ("7000", State.TAS),   # Hobart
        ("8000", State.VIC),   # VIC PO-box range
        ("9000", State.QLD),   # QLD PO-box range
    ],
)
def test_known_postcodes_resolve(postcode, expected):
    tv = state_from_postcode(postcode)
    assert tv.value == expected
    assert tv.confidence >= 0.9
    assert not tv.is_missing


def test_invalid_postcode_is_missing_not_guessed():
    assert state_from_postcode("abcd").is_missing
    assert state_from_postcode(None).is_missing


def test_out_of_range_is_missing():
    tv = state_from_postcode("0000")
    assert tv.is_missing
    assert tv.below(0.6)
