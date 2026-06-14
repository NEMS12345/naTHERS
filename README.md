# PlanAssess

PlanAssess ingests residential building plans (DXF, DWG, PDF) and produces an
**indicative** NatHERS thermal assessment plus a jurisdiction-specific
sustainability **pre-assessment**, with national scope across all Australian
states and territories.

> ## ⚠️ This tool does not produce certificates
>
> - PlanAssess output is a **pre-assessment and data-preparation pack only**. It
>   is **not** an official or lodgeable certificate.
> - The thermal result is **indicative only**. Official NatHERS star ratings
>   require the CSIRO **Chenath** engine inside **accredited software**.
>   PlanAssess does **not** reimplement or imitate Chenath.
> - **BASIX** certificates issue only via the **NSW Planning Portal**. **NatHERS
>   Whole-of-Home** outputs only via **accredited software**. PlanAssess produces
>   pre-assessments and pre-filled input packs for both paths — never the
>   certificate itself.
> - Every extracted value carries a **confidence score and a source**. Anything
>   below the configured threshold is **gap-flagged for human review**. There are
>   **no silent defaults**.

## Pipeline

```
ingest ──▶ extract ──▶ normalise (canonical Building Model) ──▶ [REVIEW GATE] ──▶ assess ──▶ report
```

The human-in-the-loop **review gate** sits between extract and assess. The
**assess** stage selects a jurisdiction strategy at runtime:

- **NSW** → BASIX pre-assessment (Energy, Water, Thermal Comfort)
- **All other states/territories** → NatHERS Whole-of-Home (WoH) pre-assessment
  (NT: WoH not mandatory — marked *not required*)

All compliance targets, star thresholds and benchmarks live in a **versioned,
jurisdiction-keyed config** (`config/`), never hardcoded.

### Data & provenance

`config/jurisdictions.yaml` carries `last_reviewed`, a `sources` list and
per-jurisdiction NCC 2022 adoption dates / 7-star-mandatory flags (TAS and NT
had not adopted the 7-star/WoH provisions at the last review). These figures
were sourced from NatHERS/ABCB/NSW Planning publications and are **indicative —
verify against the cited sources before relying on them**. The indicative
scoring models (BASIX energy/water/thermal proxies and the WoH score) are
**directional only** and are not the regulated BASIX or NatHERS Whole-of-Home
calculations; the BASIX `energy` figure is an efficiency index, not the
regulated percentage (the regulated target is recorded alongside as a note).
The postcode→climate-zone and climate degree-day tables remain seed subsets
pending a sourced national dataset — see [`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md)
for the authoritative sources and the one-command importer
(`scripts/build_climate_zone_table.py`). Postcode→**state** is fully wired from
the Australia Post ranges (offline), so `--state` is optional.

## Status — build phases

| Phase | Deliverable | State |
|------|-------------|-------|
| P0 | Repo scaffold, pydantic Building Model schema, CLI, jurisdiction config, synthetic fixtures, passing tests | ✅ done |
| P1 | DXF ingestion → Building Model (wall-network room closing, north-arrow orientation, schedule parsing) | ✅ done |
| P2 | Indicative thermal + jurisdiction compliance (BASIX / WoH) + report/gap/input-pack | ✅ done |
| P3 | PDF vector ingestion (PyMuPDF; scale + north detection) | ✅ done |
| P4 | PDF raster Tier 1 (OpenCV + tesseract, offline) + optional Tier 2 vision fallback (off by default) | ✅ done |
| P5 | Review UI | out of scope (later) |

PDF dispatch sniffs the first page: vector PDFs route to the vector adapter,
scanned/image PDFs to the raster adapter. Raster is the lowest-confidence path
(scanned room separation is unreliable), so its values are readily gap-flagged;
the optional Tier-2 vision fallback (Anthropic API, **off by default**) can be
enabled in `config/settings.yaml` to resolve residual cropped regions. The tool
runs end to end with the API disabled.

## Install

```bash
pip install -e ".[dev]"                       # core + tests
pip install -e ".[dev,dxf]"                   # + DXF ingestion (also used by DWG)
pip install -e ".[dev,dxf,pdf,raster,report]" # + PDF vector/raster ingestion and PDF report
```

External dependency (DWG path): **ODA File Converter** (free desktop tool)
converts DWG → DXF; PlanAssess auto-invokes it if present and otherwise reports
clearly. Raster OCR (P4) needs the **tesseract** binary. The `assessment_report.pdf`
needs the `report` extra (reportlab); without it the markdown report is still produced.

## Usage

```bash
planassess assess path/to/plan.dxf --state NSW --postcode 2000 --out ./out
# --state is optional: if omitted it is derived from the postcode
planassess assess path/to/plan.dxf --postcode 4000 --out ./out   # -> QLD
```

Outputs written to `--out`:

- `building_model.json` — canonical model with confidence and sources
- `assessment_report.md` / `.pdf` — indicative NatHERS band + jurisdiction result + assumptions log
- `gap_report.md` — every low-confidence / missing field, grouped by the assessment that needs it
- `input_pack.md` / `.csv` — pre-filled field sheet for accredited software + BASIX/WoH

## Development

```bash
pip install -e ".[dev]"
pytest
```
