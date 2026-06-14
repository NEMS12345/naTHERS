"""The human-in-the-loop review gate (sits between extract and assess).

Walks the canonical Building Model, finds every TrackedValue at or below the
configured confidence threshold (or missing, or config-defaulted), and groups
the gaps. This is where the "no silent defaults" guarantee is enforced: nothing
proceeds to assessment without low-confidence fields being surfaced.

The gate is config-driven (threshold injected) and assessment-aware: each gap is
tagged with which assessment(s) need it, so the gap report can group by need.
"""

from __future__ import annotations

from pydantic import BaseModel

from ..model.building import BuildingModel
from ..model.tracked import TrackedValue

# Which assessment consumes which model path. A path prefix maps to the set of
# assessments that depend on it. Used to group gaps by "the assessment that
# needs it" in the gap report.
ASSESSMENT_NEEDS: dict[str, tuple[str, ...]] = {
    "project.climate_zone": ("thermal", "compliance"),
    "project.state": ("compliance",),
    "site.north_angle_deg": ("thermal",),
    "zones": ("thermal",),
    "walls": ("thermal",),
    "roofs": ("thermal",),
    "floors": ("thermal",),
    "glazing": ("thermal",),
    "doors": ("thermal",),
    "services": ("compliance",),
    "fixtures": ("compliance",),  # WELS/water -> BASIX water; loads -> WoH
}


class Gap(BaseModel):
    """A single field requiring human review."""

    path: str  # dotted path within the BuildingModel, e.g. "walls[0].r_value"
    reason: str  # "missing" | "low_confidence" | "config_default"
    confidence: float
    source: str
    unit: str | None = None
    notes: str | None = None
    needed_by: tuple[str, ...] = ()  # assessments that depend on this field


class ReviewResult(BaseModel):
    threshold: float
    total_tracked: int
    populated: int
    gaps: list[Gap]

    @property
    def passed(self) -> bool:
        """True when no field needs review."""
        return len(self.gaps) == 0


def _reason(tv: TrackedValue, threshold: float) -> str:
    if tv.is_missing:
        return "missing"
    if tv.source.value == "config_default":
        return "config_default"
    if tv.confidence < threshold:
        return "low_confidence"
    return "ok"


def _needed_by(path: str) -> tuple[str, ...]:
    for prefix, needs in ASSESSMENT_NEEDS.items():
        if path == prefix or path.startswith(prefix + ".") or path.startswith(prefix + "["):
            return needs
    return ()


def _walk(obj: object, path: str, threshold: float, out: list[Gap], counts: list[int]) -> None:
    """Recursively walk pydantic models / lists, collecting tracked-value gaps."""
    if isinstance(obj, TrackedValue):
        counts[0] += 1  # total tracked
        if not obj.is_missing:
            counts[1] += 1  # populated
        if obj.below(threshold):
            out.append(
                Gap(
                    path=path,
                    reason=_reason(obj, threshold),
                    confidence=obj.confidence,
                    source=obj.source.value,
                    unit=obj.unit,
                    notes=obj.notes,
                    needed_by=_needed_by(path),
                )
            )
        return
    if isinstance(obj, BaseModel):
        for name, _ in type(obj).model_fields.items():
            _walk(getattr(obj, name), f"{path}.{name}" if path else name, threshold, out, counts)
        return
    if isinstance(obj, (list, tuple)):
        for i, item in enumerate(obj):
            _walk(item, f"{path}[{i}]", threshold, out, counts)
        return
    # plain scalars (ids, links, schema_version) are model wiring, not tracked.


def run_review_gate(model: BuildingModel, threshold: float) -> ReviewResult:
    """Evaluate the model against the threshold and return grouped gaps."""
    gaps: list[Gap] = []
    counts = [0, 0]  # [total_tracked, populated]
    _walk(model, "", threshold, gaps, counts)
    # Keep the model's completeness summary in sync with what the gate found.
    model.extraction_meta.field_count = counts[0]
    model.extraction_meta.populated_count = counts[1]
    model.extraction_meta.flagged_count = len(gaps)
    return ReviewResult(
        threshold=threshold,
        total_tracked=counts[0],
        populated=counts[1],
        gaps=gaps,
    )
