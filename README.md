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

## Status — build phases

| Phase | Deliverable | State |
|------|-------------|-------|
| P0 | Repo scaffold, pydantic Building Model schema, CLI, jurisdiction config, synthetic fixtures, passing tests | ✅ done |
| P1 | DXF ingestion → Building Model | ⏳ next |
| P2 | Indicative thermal + jurisdiction compliance (BASIX / WoH) + report/gap/input-pack | ⏳ |
| P3 | PDF vector ingestion | ⏳ |
| P4 | PDF raster Tier 1 (offline) + optional Tier 2 API fallback | ⏳ |
| P5 | Review UI | out of scope (later) |

## Install

```bash
pip install -e ".[dev]"          # core + tests (P0)
pip install -e ".[dev,dxf]"      # add DXF ingestion (P1)
```

External dependency (P2 DWG path): **ODA File Converter** (free desktop tool)
converts DWG → DXF; PlanAssess auto-invokes it if present.

## Usage

```bash
planassess assess path/to/plan.dxf --state NSW --postcode 2000 --out ./out
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
