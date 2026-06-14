"""Enumerations for the canonical Building Model.

All string values use Australian spelling. Enums keep the model self-validating
and make jurisdiction-strategy selection explicit.
"""

from __future__ import annotations

from enum import Enum


class State(str, Enum):
    """Australian states and territories."""

    NSW = "NSW"
    VIC = "VIC"
    QLD = "QLD"
    SA = "SA"
    WA = "WA"
    TAS = "TAS"
    NT = "NT"
    ACT = "ACT"


class Provenance(str, Enum):
    """Where a tracked value came from. Drives confidence interpretation."""

    DXF_GEOMETRY = "dxf_geometry"      # derived from polylines/blocks via shapely
    DXF_TEXT = "dxf_text"             # MTEXT / TEXT labels
    SCHEDULE = "schedule"            # window/door schedule table
    PDF_VECTOR = "pdf_vector"          # vector line geometry / text from PDF
    RASTER_CV = "raster_cv"           # geometry from OpenCV on a rasterised page
    OCR = "ocr"                  # pytesseract
    VISION_LLM = "vision_llm"           # Tier-2 cropped-region fallback (only if enabled)
    DERIVED = "derived"              # computed from other tracked values
    CONFIG_DEFAULT = "config_default"       # a default; NEVER applied silently — still gap-flagged
    HUMAN = "human"                # entered/confirmed at the review gate
    UNKNOWN = "unknown"              # placeholder for a missing field


class DwellingType(str, Enum):
    HOUSE = "house"
    DUAL_OCCUPANCY = "dual_occupancy"
    SECONDARY = "secondary"           # secondary dwelling / granny flat
    APARTMENT = "apartment"


class ZoneType(str, Enum):
    LIVING = "living"               # conditioned daytime living
    NIGHT = "night"                # conditioned bedrooms
    WET = "wet"                  # bathroom/laundry/kitchen wet areas
    GARAGE = "garage"
    UNCONDITIONED = "unconditioned"


class Orientation(str, Enum):
    """8-point compass orientation (the face a surface points toward)."""

    N = "N"
    NE = "NE"
    E = "E"
    SE = "SE"
    S = "S"
    SW = "SW"
    W = "W"
    NW = "NW"


class WallAdjacency(str, Enum):
    EXTERNAL = "external"           # exposed to ambient
    PARTY = "party"               # shared with neighbouring dwelling
    INTERNAL = "internal"           # between zones of the same dwelling


class FloorType(str, Enum):
    SLAB_ON_GROUND = "slab_on_ground"
    SUSPENDED = "suspended"
    SLAB_ON_GROUND_WAFFLE = "slab_on_ground_waffle"
    OTHER = "other"


class SubFloorCondition(str, Enum):
    ENCLOSED = "enclosed"
    VENTILATED = "ventilated"
    NA = "not_applicable"          # e.g. slab on ground


class RoofType(str, Enum):
    PITCHED = "pitched"
    SKILLION = "skillion"
    FLAT = "flat"


class JurisdictionStrategy(str, Enum):
    """Which sustainability assessment path applies."""

    BASIX = "basix"               # NSW
    WOH = "woh"                  # NatHERS Whole-of-Home (all other states/territories)
