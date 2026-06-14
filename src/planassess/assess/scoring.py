"""Transparent keyword scoring helpers for service/fixture text.

Indicative only. Maps free-text service descriptions to efficiency factors used
by the BASIX energy and WoH pre-assessments. Returns None when no keyword
matches so the caller can flag the input rather than assume a value.
"""

from __future__ import annotations

# Hot-water system -> indicative emissions-reduction contribution (0..1 of the
# hot-water share) relative to an electric-resistance baseline.
HOT_WATER_FACTORS = {
    ("solar", "thermal"): 0.85,
    ("heat pump", "heat-pump", "heatpump"): 0.75,
    ("gas", "instant", "instantaneous"): 0.35,
    ("electric", "resistance", "storage"): 0.0,
}

# Space conditioning -> efficiency factor relative to a resistive/ducted baseline.
HVAC_FACTORS = {
    ("reverse", "reverse-cycle", "split", "heat pump"): 0.6,
    ("ducted reverse", "vrf"): 0.5,
    ("gas",): 0.3,
    ("resistance", "electric", "panel"): 0.0,
}

# Cooktop -> factor.
COOKTOP_FACTORS = {
    ("induction",): 0.6,
    ("electric", "ceramic"): 0.3,
    ("gas",): 0.0,
}


def score_text(text: str | None, table: dict[tuple[str, ...], float]) -> float | None:
    """Return the best-matching factor for ``text`` from a keyword table, or None."""
    if not text:
        return None
    low = text.lower()
    best: float | None = None
    for keys, factor in table.items():
        if any(k in low for k in keys):
            best = factor if best is None else max(best, factor)
    return best
