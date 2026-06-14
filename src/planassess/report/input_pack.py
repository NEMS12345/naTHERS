"""input_pack.md / .csv — pre-filled field sheet for an assessor to key in.

Maps the canonical model to (a) NatHERS accredited-software input categories
ALWAYS, and (b) either BASIX tool sections (NSW) or NatHERS WoH module fields
(other jurisdictions). Each row carries the extracted value, its confidence and
source, and a clear "ACTION: confirm/provide" flag for low-confidence or missing
fields so nothing is silently assumed.
"""

from __future__ import annotations

import csv
from pathlib import Path

from ..assess.results import ComplianceResult
from ..assess.thermal import ThermalResult
from ..constants import NOT_A_CERTIFICATE_CAVEAT
from ..model.building import BuildingModel
from ..model.enums import JurisdictionStrategy, State
from ..model.tracked import TrackedValue

# Confidence at/below which a field is marked for assessor action.
_ACTION_THRESHOLD = 0.6


class Row:
    __slots__ = ("target", "section", "field", "value", "unit", "confidence", "source", "action")

    def __init__(self, target, section, field, tv: TrackedValue):
        self.target = target
        self.section = section
        self.field = field
        if tv is None or tv.is_missing:
            self.value = ""
            self.unit = (tv.unit if tv else "") or ""
            self.confidence = 0.0
            self.source = "—"
            self.action = "PROVIDE"
        else:
            self.value = tv.value.value if hasattr(tv.value, "value") else tv.value
            self.unit = tv.unit or ""
            self.confidence = tv.confidence
            self.source = tv.source.value
            self.action = "confirm" if tv.confidence < _ACTION_THRESHOLD else ""


def _nathers_rows(model: BuildingModel) -> list[Row]:
    """Always-present NatHERS accredited-software input categories."""
    rows: list[Row] = []
    p, s = model.project, model.site
    rows.append(Row("NatHERS", "Project", "Climate zone", p.climate_zone))
    rows.append(Row("NatHERS", "Site", "North angle (deg)", s.north_angle_deg))
    for z in model.zones:
        rows.append(Row("NatHERS", f"Zone {z.id}", "Name", z.name))
        rows.append(Row("NatHERS", f"Zone {z.id}", "Type", z.type))
        rows.append(Row("NatHERS", f"Zone {z.id}", "Floor area", z.floor_area))
        rows.append(Row("NatHERS", f"Zone {z.id}", "Ceiling height", z.ceiling_height))
    for w in model.walls:
        rows.append(Row("NatHERS", f"Wall {w.id}", "Orientation", w.orientation))
        rows.append(Row("NatHERS", f"Wall {w.id}", "Construction", w.construction))
        rows.append(Row("NatHERS", f"Wall {w.id}", "R-value", w.r_value))
        rows.append(Row("NatHERS", f"Wall {w.id}", "Area", w.area))
    for rf in model.roofs:
        rows.append(Row("NatHERS", f"Roof {rf.id}", "R-value", rf.r_value))
        rows.append(Row("NatHERS", f"Roof {rf.id}", "Solar absorptance", rf.solar_absorptance))
    for g in model.glazing:
        rows.append(Row("NatHERS", f"Glazing {g.id}", "Orientation", g.orientation))
        rows.append(Row("NatHERS", f"Glazing {g.id}", "Area", g.area))
        rows.append(Row("NatHERS", f"Glazing {g.id}", "U-value", g.u_value))
        rows.append(Row("NatHERS", f"Glazing {g.id}", "SHGC", g.shgc))
        rows.append(Row("NatHERS", f"Glazing {g.id}", "Eave/shading depth", g.eave_shading_depth))
    return rows


def _basix_rows(model: BuildingModel) -> list[Row]:
    s, fx = model.services, model.fixtures
    return [
        Row("BASIX", "Water", "WELS showers", fx.wels_showers),
        Row("BASIX", "Water", "WELS taps", fx.wels_taps),
        Row("BASIX", "Water", "WELS toilets", fx.wels_toilets),
        Row("BASIX", "Water", "Rainwater tank", fx.rainwater_tank_l),
        Row("BASIX", "Water", "Landscaping type", fx.landscaping_type),
        Row("BASIX", "Energy", "Hot water", s.hot_water),
        Row("BASIX", "Energy", "Heating", s.heating),
        Row("BASIX", "Energy", "Cooling", s.cooling),
        Row("BASIX", "Energy", "Cooktop", s.cooktop),
        Row("BASIX", "Energy", "Solar PV (kW)", s.solar_pv_kw),
        Row("BASIX", "Thermal Comfort", "See NatHERS envelope rows", model.walls[0].r_value
            if model.walls else fx.wels_taps),
    ]


def _woh_rows(model: BuildingModel) -> list[Row]:
    s = model.services
    return [
        Row("WoH", "Heating/Cooling", "Heating", s.heating),
        Row("WoH", "Heating/Cooling", "Cooling", s.cooling),
        Row("WoH", "Hot water", "Hot water", s.hot_water),
        Row("WoH", "Lighting", "Lighting", s.lighting),
        Row("WoH", "Pool/Spa", "Pool/spa", s.pool_spa),
        Row("WoH", "Cooking/Plug", "Cooktop", s.cooktop),
        Row("WoH", "On-site generation", "Solar PV (kW)", s.solar_pv_kw),
        Row("WoH", "On-site generation", "Battery (kWh)", s.battery_kwh),
    ]


def build_rows(model: BuildingModel, strategy: JurisdictionStrategy) -> list[Row]:
    rows = _nathers_rows(model)
    if strategy == JurisdictionStrategy.BASIX:
        rows += _basix_rows(model)
    else:
        rows += _woh_rows(model)
    return rows


def render_input_pack_md(model: BuildingModel, state: State, rows: list[Row]) -> str:
    lines = ["# PlanAssess — Input Pack", ""]
    lines.append(f"> {NOT_A_CERTIFICATE_CAVEAT}")
    lines.append("")
    lines.append(
        f"Pre-filled field sheet for **{state.value}**. `ACTION` = `PROVIDE` (missing) or "
        "`confirm` (low confidence). Blank action = ready to key in."
    )
    lines.append("")
    lines.append("| Target | Section | Field | Value | Unit | Conf. | Source | Action |")
    lines.append("|--------|---------|-------|-------|------|-------|--------|--------|")
    for r in rows:
        lines.append(
            f"| {r.target} | {r.section} | {r.field} | {r.value} | {r.unit} | "
            f"{r.confidence:.2f} | {r.source} | {r.action} |"
        )
    lines.append("")
    return "\n".join(lines)


def write_input_pack(
    model: BuildingModel,
    state: State,
    thermal: ThermalResult,
    compliance: ComplianceResult,
    out_dir: Path,
) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = build_rows(model, compliance.strategy)

    md_path = out_dir / "input_pack.md"
    md_path.write_text(render_input_pack_md(model, state, rows), encoding="utf-8")

    csv_path = out_dir / "input_pack.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["target", "section", "field", "value", "unit", "confidence", "source", "action"])
        for r in rows:
            writer.writerow([r.target, r.section, r.field, r.value, r.unit,
                             f"{r.confidence:.2f}", r.source, r.action])
    return [md_path, csv_path]
