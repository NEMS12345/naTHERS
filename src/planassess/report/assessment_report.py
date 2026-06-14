"""assessment_report.md — indicative NatHERS band + jurisdiction compliance result.

P0 renders the skeleton with mandatory disclaimers, the jurisdiction strategy
selection, and the assumptions log. The thermal band and full compliance margins
are populated in P2.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from ..assess.strategy import ComplianceResult
from ..constants import (
    INDICATIVE_THERMAL_CAVEAT,
    NOT_A_CERTIFICATE_CAVEAT,
)
from ..model.building import BuildingModel
from ..review.gate import ReviewResult


def render_assessment_report(
    model: BuildingModel,
    review: ReviewResult,
    compliance: ComplianceResult,
) -> str:
    lines: list[str] = []
    lines.append("# PlanAssess — Indicative Assessment Report")
    lines.append("")
    lines.append(f"Generated: {date.today().isoformat()} · Project: `{model.project.id}`")
    lines.append("")
    lines.append("> **⚠️ NOT A CERTIFICATE**")
    lines.append(f"> {NOT_A_CERTIFICATE_CAVEAT}")
    lines.append("")

    # --- Indicative NatHERS thermal ---
    lines.append("## 1. Indicative NatHERS thermal")
    lines.append("")
    lines.append(f"> {INDICATIVE_THERMAL_CAVEAT}")
    lines.append("")
    state = model.project.state.value
    lines.append(f"- State/territory: **{state.value if state else 'UNKNOWN — see gap report'}**")
    cz = model.project.climate_zone
    lines.append(
        f"- NatHERS climate zone: **{cz.value if not cz.is_missing else 'UNKNOWN — see gap report'}** "
        f"(confidence {cz.confidence:.2f})"
    )
    lines.append("- Indicative star band: _pending — thermal engine arrives in P2_")
    lines.append("- Estimated heating/cooling loads (MJ/m².yr): _pending (P2)_")
    lines.append("")

    # --- Jurisdiction compliance ---
    lines.append("## 2. Jurisdiction compliance pre-assessment")
    lines.append("")
    lines.append(f"- Strategy selected: **{compliance.strategy.value}**")
    lines.append(f"- Mandatory in jurisdiction: **{'yes' if compliance.mandatory else 'no'}**")
    lines.append(f"- {compliance.summary}")
    lines.append("")
    if compliance.categories:
        lines.append("| Category | Indicative result |")
        lines.append("|----------|-------------------|")
        for cat, res in compliance.categories.items():
            lines.append(f"| {cat} | {res} |")
        lines.append("")

    # --- Assumptions / extraction log ---
    lines.append("## 3. Assumptions & extraction log")
    lines.append("")
    meta = model.extraction_meta
    lines.append(f"- Source file: `{meta.source_file or 'n/a'}` · Adapter: `{meta.adapter or 'n/a'}`")
    lines.append(
        f"- Tracked fields: **{meta.field_count}** · Populated: **{meta.populated_count}** "
        f"· Completeness: **{meta.completeness:.0%}**"
    )
    lines.append(
        f"- Fields flagged for human review: **{review.gaps.__len__()}** "
        f"(threshold {review.threshold:.2f}) — see `gap_report.md`"
    )
    lines.append("")
    lines.append(
        "_No values were silently defaulted. Every figure above derives from a "
        "tracked value with a recorded source and confidence._"
    )
    lines.append("")
    return "\n".join(lines)


def write_assessment_report(
    model: BuildingModel,
    review: ReviewResult,
    compliance: ComplianceResult,
    out_dir: Path,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "assessment_report.md"
    path.write_text(render_assessment_report(model, review, compliance), encoding="utf-8")
    return path
