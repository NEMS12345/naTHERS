"""Canonical constants and disclaimer text.

These disclaimer strings are the single source of truth for the labelling that
the project's HARD CONSTRAINTS require on every output. Reports import from here
so the wording can never silently drift or be omitted.
"""

from __future__ import annotations

SCHEMA_VERSION = "0.1.0"

# --- Mandatory disclaimers (must appear on every output) ---------------------

INDICATIVE_THERMAL_CAVEAT = (
    "INDICATIVE ONLY — not a NatHERS rating. Official NatHERS star ratings "
    "require the CSIRO Chenath engine inside accredited software. This figure "
    "is a simplified heat-balance estimate for pre-assessment and is not "
    "produced by, and must not be represented as, a Chenath rating."
)

NOT_A_CERTIFICATE_CAVEAT = (
    "This document is a PRE-ASSESSMENT and data-preparation pack only. It is "
    "NOT an official or lodgeable certificate. BASIX certificates issue only "
    "via the NSW Planning Portal; NatHERS Whole-of-Home outputs only via "
    "accredited software."
)

CONFIDENCE_CAVEAT = (
    "Every extracted value carries a confidence score and a source. Values "
    "below the configured review threshold are gap-flagged for human review. "
    "No values are silently defaulted or guessed."
)

DISCLAIMER_BLOCK = "\n\n".join(
    ["> " + line for line in (INDICATIVE_THERMAL_CAVEAT, NOT_A_CERTIFICATE_CAVEAT, CONFIDENCE_CAVEAT)]
)
