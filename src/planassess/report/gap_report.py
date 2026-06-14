"""gap_report.md — every low-confidence/missing field, grouped by the assessment that needs it."""

from __future__ import annotations

from pathlib import Path

from ..constants import CONFIDENCE_CAVEAT
from ..review.gate import Gap, ReviewResult


def _group_by_assessment(gaps: list[Gap]) -> dict[str, list[Gap]]:
    groups: dict[str, list[Gap]] = {}
    for gap in gaps:
        keys = gap.needed_by or ("unattributed",)
        for key in keys:
            groups.setdefault(key, []).append(gap)
    return groups


def render_gap_report(result: ReviewResult) -> str:
    lines: list[str] = []
    lines.append("# PlanAssess — Gap Report")
    lines.append("")
    lines.append(f"> {CONFIDENCE_CAVEAT}")
    lines.append("")
    lines.append(
        f"Review threshold: **{result.threshold:.2f}** · "
        f"Tracked fields: **{result.total_tracked}** · "
        f"Populated: **{result.populated}** · "
        f"Flagged for review: **{len(result.gaps)}**"
    )
    lines.append("")

    if result.passed:
        lines.append("✅ No fields require human review at the current threshold.")
        lines.append("")
        return "\n".join(lines)

    for assessment, gaps in sorted(_group_by_assessment(result.gaps).items()):
        lines.append(f"## Needed by: {assessment}")
        lines.append("")
        lines.append("| Field | Reason | Confidence | Source | Notes |")
        lines.append("|-------|--------|-----------|--------|-------|")
        for gap in gaps:
            notes = (gap.notes or "").replace("|", "\\|")
            lines.append(
                f"| `{gap.path}` | {gap.reason} | {gap.confidence:.2f} | {gap.source} | {notes} |"
            )
        lines.append("")
    return "\n".join(lines)


def write_gap_report(result: ReviewResult, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "gap_report.md"
    path.write_text(render_gap_report(result), encoding="utf-8")
    return path
