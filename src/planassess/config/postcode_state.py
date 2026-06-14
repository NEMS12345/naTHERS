"""Derive the Australian state/territory from a postcode.

Uses the authoritative Australia Post postcode ranges — this is well-defined and
needs no external data, so it works fully offline. The state of a postcode is
unambiguous (unlike its NatHERS *climate* zone, which still requires the official
lookup table). Returned as a TrackedValue so it carries confidence + source and
trips the review gate when a postcode is invalid.
"""

from __future__ import annotations

from ..model.enums import Provenance, State
from ..model.tracked import TrackedValue, missing

# (low, high, state) inclusive ranges — Australia Post allocations.
_RANGES: list[tuple[int, int, State]] = [
    (200, 299, State.ACT),     # ACT PO boxes / GPO
    (800, 999, State.NT),
    (1000, 1999, State.NSW),   # NSW PO boxes / LVRs
    (2000, 2599, State.NSW),
    (2600, 2618, State.ACT),
    (2619, 2899, State.NSW),
    (2900, 2920, State.ACT),
    (2921, 2999, State.NSW),
    (3000, 3999, State.VIC),
    (4000, 4999, State.QLD),
    (5000, 5999, State.SA),
    (6000, 6999, State.WA),
    (7000, 7999, State.TAS),
    (8000, 8999, State.VIC),   # VIC PO boxes / LVRs
    (9000, 9999, State.QLD),   # QLD PO boxes / LVRs
]


def state_from_postcode(postcode: str | int | None) -> TrackedValue:
    """Return the state/territory for an Australian postcode as a TrackedValue."""
    if postcode is None:
        return missing(notes="No postcode supplied to derive state/territory.")
    try:
        pc = int(str(postcode).strip())
    except (TypeError, ValueError):
        return missing(notes=f"Postcode '{postcode}' is not numeric; cannot derive state.")
    for low, high, state in _RANGES:
        if low <= pc <= high:
            return TrackedValue(
                value=state,
                source=Provenance.DERIVED,
                confidence=0.97,
                notes=f"Derived from Australia Post postcode range {low:04d}-{high:04d}.",
            )
    return missing(notes=f"Postcode {pc:04d} is outside known Australian ranges.")
