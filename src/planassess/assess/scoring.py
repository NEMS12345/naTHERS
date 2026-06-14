"""Transparent keyword scoring helpers for service/fixture text.

Indicative only. Maps free-text service descriptions to efficiency factors used
by the BASIX energy and WoH pre-assessments. Returns None when no keyword
matches so the caller can flag the input rather than assume a value.
"""

from __future__ import annotations

# Hot-water system -> indicative emissions-reduction contribution (0..1 of the
# hot-water share) relative to an electric-resistance baseline. score_text takes
# the MAX over matches, so more specific (higher) entries win.
HOT_WATER_FACTORS = {
    ("solar thermal", "solar hot water"): 0.85,
    ("heat pump", "heat-pump", "heatpump", "co2", "co₂"): 0.75,
    ("gas boosted solar", "solar gas", "gas-boosted"): 0.70,
    ("electric boosted solar", "solar electric"): 0.60,
    ("solar",): 0.55,                                  # unspecified solar
    ("gas", "instant", "instantaneous", "continuous flow", "lpg"): 0.35,
    ("electric", "resistance", "storage"): 0.0,
}

# Space conditioning -> efficiency factor relative to a resistive baseline.
HVAC_FACTORS = {
    ("ducted reverse", "vrf", "vrv"): 0.6,
    ("reverse", "reverse-cycle", "reverse cycle", "split", "heat pump"): 0.55,
    ("evaporative",): 0.4,                             # efficient but climate-limited cooling
    ("hydronic",): 0.35,
    ("gas", "ducted gas"): 0.3,
    ("resistance", "electric", "panel", "bar heater"): 0.0,
}

# Cooktop -> factor.
COOKTOP_FACTORS = {
    ("induction",): 0.6,
    ("electric", "ceramic", "radiant"): 0.3,
    ("gas", "lpg"): 0.0,
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
