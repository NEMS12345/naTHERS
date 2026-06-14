"""The TrackedValue wrapper: every extracted field carries value + source + confidence.

This is the backbone of the "no silent defaults" guarantee. A field that could
not be extracted is represented explicitly as a TrackedValue with ``value=None``
and ``source=Provenance.UNKNOWN`` — never omitted, never quietly defaulted.

Review status (is this below the threshold?) deliberately lives in the review
gate, not here, because the threshold is configurable and config-owned. Keeping
TrackedValue free of config coupling means the model stays pure, serialisable
data.
"""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

from .enums import Provenance

T = TypeVar("T")


class TrackedValue(BaseModel, Generic[T]):
    """A single extracted datum with provenance and confidence.

    Attributes:
        value: The extracted value, or ``None`` if it could not be determined.
        source: Where the value came from (see :class:`Provenance`).
        confidence: 0.0–1.0. For a missing value this should be 0.0.
        unit: Optional SI unit string, e.g. ``"m2"``, ``"m"``, ``"MJ/m2.yr"``.
        notes: Optional human-readable note (e.g. why confidence is low,
            ambiguity detected, the raw label text it was parsed from).
    """

    value: T | None = None
    source: Provenance = Provenance.UNKNOWN
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    unit: str | None = None
    notes: str | None = None

    @property
    def is_missing(self) -> bool:
        """True when no value was determined."""
        return self.value is None

    def below(self, threshold: float) -> bool:
        """True when this datum should be flagged for human review.

        A value is flagged if it is missing, if its confidence is below the
        given threshold, or if it was supplied as a config default (defaults
        are never silently accepted).
        """
        return (
            self.is_missing
            or self.confidence < threshold
            or self.source == Provenance.CONFIG_DEFAULT
        )


def missing(unit: str | None = None, notes: str | None = None) -> "TrackedValue":
    """Construct an explicit 'not found' tracked value (no silent omission)."""
    return TrackedValue(value=None, source=Provenance.UNKNOWN, confidence=0.0, unit=unit, notes=notes)


def observed(
    value: T,
    source: Provenance,
    confidence: float,
    unit: str | None = None,
    notes: str | None = None,
) -> "TrackedValue[T]":
    """Construct a tracked value for an extracted/observed datum."""
    return TrackedValue(value=value, source=source, confidence=confidence, unit=unit, notes=notes)
