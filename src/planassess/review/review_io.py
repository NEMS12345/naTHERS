"""Human-in-the-loop review I/O: export an editable template, apply answers back.

This is the inbound half of the review gate. ``export_review_template`` writes the
flagged fields (by dotted path) to a CSV an assessor edits; ``apply_review`` reads
the filled CSV and writes each answer back into the Building Model as a
HUMAN-sourced, full-confidence TrackedValue, so the subsequent assessment uses
confirmed data. Values are coerced to each field's declared type (enums, ints,
floats) via the pydantic annotation — never blindly stored as strings.
"""

from __future__ import annotations

import csv
import re
from enum import Enum
from pathlib import Path
from typing import Any, get_args

from pydantic import BaseModel

from ..model.building import BuildingModel
from ..model.enums import Provenance
from ..model.tracked import TrackedValue, observed
from .gate import ReviewResult

_SEG = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)(?:\[(\d+)\])?")

_TEMPLATE_COLUMNS = [
    "path", "reason", "needed_by", "current_value", "unit", "confidence", "source", "your_value"
]


class ReviewError(BaseModel):
    path: str
    error: str


def export_review_template(review: ReviewResult, out_dir: Path) -> Path:
    """Write a CSV of flagged fields for a human to fill (`your_value` column)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "review_template.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(_TEMPLATE_COLUMNS)
        for g in review.gaps:
            w.writerow([
                g.path, g.reason, "|".join(g.needed_by), "", g.unit or "",
                f"{g.confidence:.2f}", g.source, "",
            ])
    return path


def _navigate(model: BuildingModel, path: str) -> tuple[BaseModel, str]:
    """Return (parent_model, leaf_field_name) for a dotted/indexed path."""
    segments = [m for m in _SEG.finditer(path)]
    obj: Any = model
    for seg in segments[:-1]:
        name, idx = seg.group(1), seg.group(2)
        obj = getattr(obj, name)
        if idx is not None:
            obj = obj[int(idx)]
    leaf = segments[-1].group(1)
    if not isinstance(obj, BaseModel) or leaf not in type(obj).model_fields:
        raise KeyError(f"'{path}' does not resolve to a model field")
    return obj, leaf


def _inner_type(annotation: Any) -> Any:
    """Extract X from a TrackedValue[X] field annotation.

    pydantic v2 materialises ``TrackedValue[X]`` as a concrete class whose generic
    args live in ``__pydantic_generic_metadata__`` (get_args returns () for it),
    so check both.
    """
    args = get_args(annotation)
    if args:
        return args[0]
    meta = getattr(annotation, "__pydantic_generic_metadata__", None)
    if meta and meta.get("args"):
        return meta["args"][0]
    return str


def _coerce(raw: str, parent: BaseModel, leaf: str) -> Any:
    """Coerce a string cell to the leaf TrackedValue's declared inner type."""
    target = _inner_type(type(parent).model_fields[leaf].annotation)
    raw = raw.strip()
    if isinstance(target, type) and issubclass(target, Enum):
        try:
            return target(raw)
        except ValueError:
            return target[raw.upper()]  # try by member name
    if target is bool:
        return raw.lower() in {"1", "true", "yes", "y"}
    if target is int:
        return int(float(raw))
    if target is float:
        return float(raw)
    return raw


def set_at_path(model: BuildingModel, path: str, raw_value: str) -> None:
    """Set the TrackedValue at ``path`` from a human answer (source=HUMAN, conf=1.0)."""
    parent, leaf = _navigate(model, path)
    existing = getattr(parent, leaf)
    unit = existing.unit if isinstance(existing, TrackedValue) else None
    value = _coerce(raw_value, parent, leaf)
    setattr(parent, leaf, observed(value, Provenance.HUMAN, 1.0, unit=unit,
                                   notes="Supplied at human review."))


def apply_review(model: BuildingModel, answers_csv: Path) -> tuple[list[str], list[ReviewError]]:
    """Apply a filled review CSV to the model. Returns (applied_paths, errors)."""
    applied: list[str] = []
    errors: list[ReviewError] = []
    with answers_csv.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            answer = (row.get("your_value") or "").strip()
            path = (row.get("path") or "").strip()
            if not answer or not path:
                continue
            try:
                set_at_path(model, path, answer)
                applied.append(path)
            except Exception as exc:  # bad path or uncoercible value -> report, skip
                errors.append(ReviewError(path=path, error=str(exc)))
    return applied, errors
