"""assessment_report.pdf — PDF rendering of the indicative assessment.

Built from the same structured data as the markdown report (not by parsing
markdown), so the two stay in lock-step. reportlab is an optional dependency
(`[report]` extra); if it is absent, :func:`write_assessment_pdf` returns None
and the pipeline simply omits the PDF — the markdown report is always produced.

Carries the mandatory disclaimers from the single source of truth.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from ..assess.results import ComplianceResult
from ..assess.thermal import ThermalResult
from ..constants import INDICATIVE_THERMAL_CAVEAT, NOT_A_CERTIFICATE_CAVEAT
from ..model.building import BuildingModel
from ..review.gate import ReviewResult


def _pass_str(passed) -> str:
    if passed is None:
        return "not assessable"
    return "PASS" if passed else "FAIL"


def write_assessment_pdf(
    model: BuildingModel,
    review: ReviewResult,
    thermal: ThermalResult,
    compliance: ComplianceResult,
    out_dir: Path,
) -> Path | None:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError:
        return None  # PDF export is optional; markdown report is always written

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "assessment_report.pdf"

    styles = getSampleStyleSheet()
    h1, h2, body = styles["Heading1"], styles["Heading2"], styles["BodyText"]
    warn = styles["BodyText"].clone("warn")
    warn.textColor = colors.HexColor("#8a4b00")

    story = []
    story.append(Paragraph("PlanAssess — Indicative Assessment Report", h1))
    story.append(Paragraph(f"Generated {date.today().isoformat()} · Project {model.project.id}", body))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("⚠️ NOT A CERTIFICATE", h2))
    story.append(Paragraph(NOT_A_CERTIFICATE_CAVEAT, warn))
    story.append(Spacer(1, 4 * mm))

    # 1. Indicative thermal
    story.append(Paragraph("1. Indicative NatHERS thermal", h2))
    story.append(Paragraph(INDICATIVE_THERMAL_CAVEAT, warn))
    cz = model.project.climate_zone
    rows = [["Climate zone", "—" if cz.is_missing else str(cz.value)]]
    if thermal.computed:
        rows += [
            ["Indicative star", f"{thermal.indicative_star} (target {thermal.star_target} — {_pass_str(thermal.meets_target)})"],
            ["Conditioned floor area", f"{thermal.conditioned_floor_area_m2} m²"],
            ["Heating load", f"{thermal.heating_load_mj_per_m2} MJ/m².yr"],
            ["Cooling load", f"{thermal.cooling_load_mj_per_m2} MJ/m².yr"],
            ["Total load", f"{thermal.total_load_mj_per_m2} MJ/m².yr"],
        ]
    else:
        rows.append(["Indicative star", "not computable — insufficient data"])
    story.append(_table(Table, TableStyle, colors, mm, rows))
    story.append(Spacer(1, 4 * mm))

    # 2. Compliance
    story.append(Paragraph("2. Jurisdiction compliance pre-assessment", h2))
    story.append(Paragraph(
        f"Strategy: {compliance.strategy.value} · Mandatory: "
        f"{'yes' if compliance.mandatory else 'no'} · Overall: {_pass_str(compliance.overall_pass)}",
        body,
    ))
    if compliance.categories:
        crows = [["Category", "Result", "Value", "Target", "Margin"]]
        for c in compliance.categories:
            crows.append([
                c.name, _pass_str(c.passed),
                f"{c.value} {c.unit or ''}".strip() if c.value is not None else "—",
                "—" if c.target is None else str(c.target),
                "—" if c.margin is None else str(c.margin),
            ])
        story.append(_table(Table, TableStyle, colors, mm, crows, header=True))
    story.append(Spacer(1, 4 * mm))

    # 3. Assumptions / extraction log
    story.append(Paragraph("3. Assumptions & extraction log", h2))
    meta = model.extraction_meta
    story.append(Paragraph(
        f"Source: {meta.source_file or 'n/a'} · Adapter: {meta.adapter or 'n/a'} · "
        f"Completeness: {meta.completeness:.0%} · "
        f"Flagged for review: {len(review.gaps)} (threshold {review.threshold:.2f}) — see gap_report.md",
        body,
    ))
    assumptions = list(thermal.assumptions) + [
        f"[{c.name}] {a}" for c in compliance.categories for a in c.assumptions
    ]
    for a in assumptions:
        story.append(Paragraph(f"• {a}", body))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(
        "No values were silently defaulted. Every figure derives from a tracked "
        "value with a recorded source and confidence, or a logged method assumption.",
        body,
    ))

    SimpleDocTemplate(str(path), pagesize=A4, title="PlanAssess Indicative Assessment").build(story)
    return path


def _table(Table, TableStyle, colors, mm, rows, header: bool = False):
    t = Table(rows, hAlign="LEFT")
    style = [
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]
    if header:
        style.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee")))
        style.append(("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"))
    t.setStyle(TableStyle(style))
    return t
