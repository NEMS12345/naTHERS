# Contributing to PlanAssess

Thanks for helping improve PlanAssess. A few ground rules keep the tool honest.

## Non-negotiables (the project's hard constraints)

- **Pre-assessment only.** Never describe output as an official or lodgeable
  certificate. The thermal result is **indicative**, not a CSIRO Chenath rating.
- **No silent defaults.** Every extracted value is a `TrackedValue` with a source
  and confidence. If something can't be determined, it stays missing and is
  gap-flagged — don't guess.
- **Config-driven.** Compliance targets, star thresholds and benchmarks live in
  `config/` keyed by jurisdiction. Never hardcode them in the assessment modules.
- **Offline-first.** The tool must run end to end with the Tier-2 vision API
  disabled (it is off by default).
- **Australian spelling** throughout.

## Dev setup

```bash
pip install -e ".[dev,dxf,pdf,raster,report]"
sudo apt-get install -y tesseract-ocr   # raster OCR (P4)
```

## Before you push

```bash
ruff check src tests          # lint (auto-fix: ruff check --fix)
mypy                          # types (schema package; expand over time)
pytest -q                     # tests
bash scripts/smoke.sh out/smoke   # end-to-end CLI smoke
```

CI runs all of the above on every push/PR.

## Architecture

`ingest -> extract -> normalise (Building Model) -> [review gate] -> assess -> report`

- Ingestion adapters (`ingest/`) all return a `BuildingModel` via the shared
  `builder.py`; add new sources there.
- The assess stage selects a jurisdiction strategy at runtime (`assess/strategy.py`):
  NSW → BASIX, others → NatHERS Whole-of-Home.
- Reports (`report/`) must carry the disclaimers from `constants.py`.

## Data

Real reference data (climate zones, benchmarks) is sourced, not invented — see
`docs/DATA_SOURCES.md`. Seed data must be clearly labelled and low-confidence so
it is gap-flagged until replaced.
