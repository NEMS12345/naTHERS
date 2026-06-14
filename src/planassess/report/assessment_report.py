"""assessment_report.md — indicative NatHERS band + jurisdiction compliance result.

Renders the indicative thermal estimate, the jurisdiction compliance categories
with margins, and a full assumptions/extraction log. Mandatory disclaimers come
from the single source of truth in constants.py.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from ..assess.results import ComplianceResult
from ..assess.thermal import ThermalResult
from ..constants import INDICATIVE_THERMAL_CAVEAT, NOT_A_CERTIFICATE_CAVEAT
from ..model.building import BuildingModel
from ..review.gate import ReviewResult


def _fmt(v) -> str:
    return "—" if v is None else f"{v}"


def _pass_str(passed) -> str:
    if passed is None:
        return "not assessable"
    return "PASS ✅" if passed else "FAIL ❌"


def render_assessment_report(
    model: BuildingModel,
    review: ReviewResult,
    thermal: ThermalResult,
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

    # --- 1. Indicative NatHERS thermal ---
    lines.append("## 1. Indicative NatHERS thermal")
    lines.append("")
    lines.append(f"> {INDICATIVE_THERMAL_CAVEAT}")
    lines.append("")
    state = model.project.state.value
    cz = model.project.climate_zone
    lines.append(f"- State/territory: **{state.value if state else 'UNKNOWN — see gap report'}**")
    lines.append(
        f"- NatHERS climate zone: **{cz.value if not cz.is_missing else 'UNKNOWN — see gap report'}** "
        f"(confidence {cz.confidence:.2f})"
    )
    lines.append(
        "  - _Note: NatHERS climate zones (1–69) are distinct from NCC climate "
        "zones (1–8); this assessment uses the NatHERS zones._"
    )
    if thermal.computed:
        lines.append(
            f"- **Indicative star: {_fmt(thermal.indicative_star)}** "
            f"(target {_fmt(thermal.star_target)} — {_pass_str(thermal.meets_target)})"
        )
        lines.append(f"- Conditioned floor area: {_fmt(thermal.conditioned_floor_area_m2)} m²")
        lines.append(f"- Envelope conductance (UA): {_fmt(thermal.ua_w_per_k)} W/K")
        lines.append(f"- Indicative heating load: **{_fmt(thermal.heating_load_mj_per_m2)} MJ/m².yr**")
        lines.append(f"- Indicative cooling load: **{_fmt(thermal.cooling_load_mj_per_m2)} MJ/m².yr**")
        lines.append(f"- Indicative total load: **{_fmt(thermal.total_load_mj_per_m2)} MJ/m².yr**")
    else:
        lines.append("- Indicative star: **not computable — insufficient data**")
    for note in thermal.notes:
        lines.append(f"  - _{note}_")
    lines.append("")

    # --- 2. Jurisdiction compliance ---
    lines.append("## 2. Jurisdiction compliance pre-assessment")
    lines.append("")
    lines.append(f"- Strategy: **{compliance.strategy.value}** · "
                 f"Mandatory: **{'yes' if compliance.mandatory else 'no'}**")
    lines.append(f"- {compliance.summary}")
    overall = compliance.overall_pass
    lines.append(f"- Overall (assessable categories): **{_pass_str(overall)}**")
    lines.append("")
    if compliance.categories:
        lines.append("| Category | Result | Value | Target | Margin | Method |")
        lines.append("|----------|--------|-------|--------|--------|--------|")
        for c in compliance.categories:
            lines.append(
                f"| {c.name} | {_pass_str(c.passed)} | {_fmt(c.value)} {c.unit or ''} | "
                f"{_fmt(c.target)} | {_fmt(c.margin)} | {c.method or ''} |"
            )
        lines.append("")
        for c in compliance.categories:
            if c.notes:
                lines.append(f"**{c.name} notes:**")
                for n in c.notes:
                    lines.append(f"- {n}")
                lines.append("")

    # --- 3. Assumptions & extraction log ---
    lines.append("## 3. Assumptions & extraction log")
    lines.append("")
    meta = model.extraction_meta
    lines.append(f"- Source file: `{meta.source_file or 'n/a'}` · Adapter: `{meta.adapter or 'n/a'}`")
    lines.append(
        f"- Tracked fields: **{meta.field_count}** · Populated: **{meta.populated_count}** "
        f"· Completeness: **{meta.completeness:.0%}**"
    )
    lines.append(
        f"- Fields flagged for human review: **{len(review.gaps)}** "
        f"(threshold {review.threshold:.2f}) — see `gap_report.md`"
    )
    lines.append("")
    all_assumptions = list(thermal.assumptions)
    for c in compliance.categories:
        all_assumptions.extend(f"[{c.name}] {a}" for a in c.assumptions)
    if all_assumptions:
        lines.append("**Method assumptions (not extracted from the plan):**")
        for a in all_assumptions:
            lines.append(f"- {a}")
        lines.append("")
    lines.append(
        "_No values were silently defaulted. Every figure above derives from a "
        "tracked value with a recorded source and confidence, or a logged method "
        "assumption._"
    )
    lines.append("")
    return "\n".join(lines)


def write_assessment_report(
    model: BuildingModel,
    review: ReviewResult,
    thermal: ThermalResult,
    compliance: ComplianceResult,
    out_dir: Path,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "assessment_report.md"
    path.write_text(
        render_assessment_report(model, review, thermal, compliance), encoding="utf-8"
    )
    return path
