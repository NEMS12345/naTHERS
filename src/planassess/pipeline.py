"""End-to-end orchestration: extract -> review gate -> assess -> report.

This is the spine the phases plug into. P0 runs it over a pre-built canonical
model (synthetic sample or a loaded building_model.json); ingestion adapters
feed the same spine from P1 onward.
"""

from __future__ import annotations

from pathlib import Path

from .assess.strategy import ComplianceResult, run_compliance
from .config.loader import load_jurisdictions, load_settings, lookup_climate_zone
from .model.building import BuildingModel
from .model.enums import State
from .report.assessment_report import write_assessment_report
from .report.building_model_json import write_building_model_json
from .report.gap_report import write_gap_report
from .review.gate import ReviewResult, run_review_gate


def resolve_climate_zone(model: BuildingModel, config_dir: Path | None = None) -> None:
    """Fill project.climate_zone via national postcode lookup if it is missing.

    This is a *derived* lookup with its own confidence, not a silent default —
    ambiguous/unknown postcodes still trip the review gate.
    """
    if model.project.climate_zone.is_missing and not model.project.postcode.is_missing:
        model.project.climate_zone = lookup_climate_zone(
            str(model.project.postcode.value), config_dir
        )


def run_pipeline(
    model: BuildingModel,
    state: State,
    out_dir: Path,
    config_dir: Path | None = None,
) -> tuple[ReviewResult, ComplianceResult, list[Path]]:
    """Run the full extract->review->assess->report pipeline over a model."""
    settings = load_settings(config_dir)
    jurisdictions = load_jurisdictions(config_dir)

    # Normalise: resolve climate zone from postcode where possible.
    resolve_climate_zone(model, config_dir)

    # Review gate (also refreshes extraction_meta counts).
    review = run_review_gate(model, settings.review_confidence_threshold)

    # Assess: select jurisdiction strategy at runtime.
    compliance = run_compliance(model, state, jurisdictions)

    # Report.
    written = [
        write_building_model_json(model, out_dir),
        write_assessment_report(model, review, compliance, out_dir),
        write_gap_report(review, out_dir),
    ]
    return review, compliance, written
