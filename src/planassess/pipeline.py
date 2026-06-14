"""End-to-end orchestration: extract -> review gate -> assess -> report.

This is the spine the phases plug into. P0 runs it over a pre-built canonical
model (synthetic sample or a loaded building_model.json); ingestion adapters
feed the same spine from P1 onward. P2 adds the indicative thermal estimate and
the jurisdiction compliance pre-assessment, plus the input pack.
"""

from __future__ import annotations

from pathlib import Path

from .assess.results import ComplianceResult
from .assess.strategy import run_compliance
from .assess.thermal import ThermalResult, assess_thermal
from .config.loader import (
    load_climate_data,
    load_jurisdictions,
    load_settings,
    lookup_climate_zone,
)
from .config.postcode_state import state_from_postcode
from .model.building import BuildingModel
from .model.enums import State
from .report.assessment_pdf import write_assessment_pdf
from .report.assessment_report import write_assessment_report
from .report.building_model_json import write_building_model_json
from .report.gap_report import write_gap_report
from .report.input_pack import write_input_pack
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


def resolve_state(model: BuildingModel) -> None:
    """Fill project.state from the postcode (Australia Post ranges) if missing."""
    if model.project.state.is_missing and not model.project.postcode.is_missing:
        model.project.state = state_from_postcode(model.project.postcode.value)


class PipelineOutput:
    """Bundle of everything the pipeline produced (kept simple, not pydantic)."""

    def __init__(
        self,
        review: ReviewResult,
        thermal: ThermalResult,
        compliance: ComplianceResult,
        written: list[Path],
    ):
        self.review = review
        self.thermal = thermal
        self.compliance = compliance
        self.written = written


def run_pipeline(
    model: BuildingModel,
    state: State,
    out_dir: Path,
    config_dir: Path | None = None,
) -> PipelineOutput:
    """Run the full extract->review->assess->report pipeline over a model."""
    settings = load_settings(config_dir)
    jurisdictions = load_jurisdictions(config_dir)
    climate_data = load_climate_data(config_dir)

    # Normalise: resolve state and climate zone from postcode where possible.
    resolve_state(model)
    resolve_climate_zone(model, config_dir)

    # Review gate (also refreshes extraction_meta counts).
    review = run_review_gate(model, settings.review_confidence_threshold)

    # Assess: indicative thermal first (feeds WoH), then jurisdiction compliance.
    jc = jurisdictions.for_state(state.value)
    zone = model.project.climate_zone
    climate = climate_data.for_zone(int(zone.value)) if not zone.is_missing else climate_data.default
    thermal = assess_thermal(model, climate, settings, jc.nathers_star_target)
    compliance = run_compliance(model, state, jurisdictions, thermal=thermal)

    # Report.
    written = [
        write_building_model_json(model, out_dir),
        write_assessment_report(model, review, thermal, compliance, out_dir),
        write_gap_report(review, out_dir),
        *write_input_pack(model, state, thermal, compliance, out_dir),
    ]
    # PDF report is optional (reportlab); appended only if it was produced.
    pdf = write_assessment_pdf(model, review, thermal, compliance, out_dir)
    if pdf is not None:
        written.append(pdf)
    return PipelineOutput(review, thermal, compliance, written)
