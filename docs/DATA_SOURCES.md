# Data sources & provenance

PlanAssess ships **seed/indicative** reference data so it runs out of the box.
The authoritative datasets below are published online but are **not vendored**
(licensing, size, and currency). This document records where they come from and
how to wire the real data in. All figures remain **indicative — verify against
the source before relying on them**.

> Note on access: the official datasets are hosted on Australian government sites
> (`nathers.gov.au`, `abcb.gov.au`, `data.gov.au`). A sandboxed/CI environment
> with an egress allowlist must add those hosts (or the file must be provided
> locally) before the build scripts can fetch them. They are not reachable from
> the default environment.

## 1. Postcode → NatHERS climate zone (1–69)

- **Source:** NatHERS — *Climate Zones by postcode* (Excel + PDF), updated periodically.
  - Landing page: https://www.nathers.gov.au/climate-zone-postcodes
  - Example file: https://www.nathers.gov.au/sites/default/files/2024-09/NatHERSclimatezonesSep2024.pdf
- **Columns:** Postcode, Primary, Secondary, Tertiary NatHERS climate zone.
- **Wire it in:**
  ```bash
  pip install openpyxl pdfplumber
  python scripts/build_climate_zone_table.py NatHERSclimatezones.xlsx --out config/climate_zones.yaml
  ```
  Postcodes with a single zone become high-confidence entries; postcodes spanning
  multiple zones become low-confidence `ambiguous` entries (gap-flagged), so no
  postcode is silently disambiguated.
- **Current state:** `config/climate_zones.yaml` holds a small capital-city seed.

## 2. Postcode → state/territory

- **Source:** Australia Post postcode ranges (well-defined; no download needed).
- **Status:** ✅ **Implemented** in `src/planassess/config/postcode_state.py` and used
  by the pipeline, so `--state` is optional and derived from the postcode.

## 3. NCC climate zones (1–8)

- **Source:** ABCB — *Australian climate zone map* dataset (CC BY 4.0).
  - https://www.abcb.gov.au/resources/climate-zone-map
  - Data: https://data.gov.au/data/dataset/australian-climate-zone-map
- **Use:** secondary cross-check / coarse zone; PlanAssess assessments use the
  NatHERS zones (item 1). Not yet wired.

## 4. Climate benchmarks (degree days, star-band load limits, WoH budgets)

- **Source:** NatHERS heating/cooling load limits and Whole-of-Home methodology
  (NatHERS technical notes / accredited-software reference data), and ABCB NCC
  2022 Volume One Part J.
  - https://www.nathers.gov.au/nathers-accredited-software/nathers-climate-zones-and-weather-files
  - https://ncc.abcb.gov.au/editions/ncc-2022/adopted/volume-one/j-energy-efficiency/part-j1-energy-efficiency-performance-requirements
- **Current state:** `config/climate_data.yaml` holds **indicative** degree-days and
  star-band load thresholds for the seed zones. Replace with sourced per-zone
  figures; the schema (`heating_degree_days`, `cooling_degree_days`,
  `solar_irradiance_factor`, `star_bands`) is already in place.

## 5. BASIX / Whole-of-Home compliance targets

- **Source:** NSW Planning Portal (BASIX) and NCC 2022 / NatHERS (WoH).
  - https://pp.planningportal.nsw.gov.au/BASIX-standards
  - https://www.basix.nsw.gov.au/iframe/new-to-basix/basix-assessment/basix-targets.html
  - https://www.nathers.gov.au/blog/victoria-and-queensland-adopt-ncc-2022
- **Status:** adoption dates, 7-star-mandatory flags and headline targets are wired
  into `config/jurisdictions.yaml` with a `sources` list and `last_reviewed` date.
  The indicative scoring models are **directional proxies**, not the regulated
  BASIX/WoH calculations.
