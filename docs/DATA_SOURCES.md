# Data sources & provenance

PlanAssess ships **seed/indicative** reference data so it runs out of the box.
The authoritative datasets below are published online but are **not vendored**
(licensing, size, and currency). This document records where they come from and
how to wire the real data in. All figures remain **indicative — verify against
the source before relying on them**.

> Note on access: the official datasets are hosted on Australian government sites
> (`nathers.gov.au`, `abcb.gov.au`, `data.gov.au`). A sandboxed/CI environment
> with an egress allowlist must add those hosts (or the file must be provided
> locally) before the build scripts can fetch them.
>
> Observed (2026-06-15) from an allowlisted sandbox: `data.gov.au` (CKAN API +
> resource downloads) and `www.abcb.gov.au` are reachable, but every path on
> `www.nathers.gov.au` returns an Akamai WAF block ("your request has been
> blocked") for the sandbox egress IP — i.e. reachable but IP-reputation
> filtered, independent of the egress allowlist. The NatHERS postcode file
> (item 1) therefore still has to be supplied locally; the ABCB NCC dataset
> (item 3) was retrieved successfully from `data.gov.au`.

## 1. Postcode → NatHERS climate zone (1–69)

- **Source:** NatHERS — *Climate Zones by postcode* (Excel + PDF), updated periodically.
  - Landing page: https://www.nathers.gov.au/climate-zone-postcodes
  - Example file: https://www.nathers.gov.au/sites/default/files/2024-09/NatHERSclimatezonesSep2024.pdf
- **Columns:** Postcode, Primary, Secondary, Tertiary NatHERS climate zone.
- **Wire it in:**
  ```bash
  pip install openpyxl pdfplumber
  python scripts/build_climate_zone_table.py NatHERSclimatezonesSept2025.xlsx --out config/climate_zones.yaml
  ```
  Postcodes with a single zone become high-confidence entries; postcodes spanning
  multiple zones become low-confidence `ambiguous` entries (gap-flagged), so no
  postcode is silently disambiguated.
- **Current state:** ✅ **Imported.** `config/climate_zones.yaml` holds the full
  national table built from `NatHERSclimatezonesSept2025.xlsx` (the
  September 2025 release) — ~2,000 unambiguous postcodes plus ~660 multi-zone
  `ambiguous` entries (gap-flagged for human confirmation).

## 2. Postcode → state/territory

- **Source:** Australia Post postcode ranges (well-defined; no download needed).
- **Status:** ✅ **Implemented** in `src/planassess/config/postcode_state.py` and used
  by the pipeline, so `--state` is optional and derived from the postcode.

## 3. NCC climate zones (1–8)

- **Source:** ABCB — *Australian Climate zone map* dataset, **CC BY 4.0** (jointly
  © Commonwealth, States & Territories of Australia, published by the ABCB).
  - Dataset: https://data.gov.au/data/dataset/australian-climate-zone-map
  - Dataset id: `97d6c684-a61f-4fdb-a322-4043e7075f8c`
  - Resources (retrieved 2026-06-15): `abcb-climate-zone-map.zip` (zone polygons,
    shapefile), `abcb-zone-files.zip` (per-zone shapefiles), and an `.eps` map.
  - Geometry vintage 2021-03-05; data.gov.au record last modified 2025-10-28.
  - **Attribution (required by CC BY 4.0):** "The Australian Climate zone map was
    provided by the Australian Building Codes Board under the CC BY 4.0 licence."
- **What it contains:** the dataset is **geospatial only** — eight zone polygons
  keyed by a `clim_zone` attribute (1–8), with **no postcode or suburb attribute**.
  Per-zone textual descriptors are not in the dataset, and the ABCB
  `climate-zone-map` web page is login-gated.
- **Use:** secondary cross-check / coarse zone; PlanAssess assessments use the
  finer NatHERS zones (item 1).
- **Wired in:** `config/ncc_climate_zones.yaml` records the eight zone numbers
  (verified from the shapefile) with full provenance/attribution, plus the NCC
  2022 zone descriptors marked **indicative** (confidence 0.5, < the review
  threshold) pending verification against NCC 2022. Loaded via
  `planassess.config.loader.load_ncc_climate_zones()`.
- **Postcode → NCC zone crosswalk (derived):** because the dataset has no
  postcode field, a postcode→zone table must be *derived* by spatially joining
  the zone polygons with ABS Postal Area (POA) boundaries:
  ```bash
  pip install pyshp shapely
  python scripts/build_ncc_zone_table.py "Climate zones AU.shp" POA_2021_AUST.shp \
      --out config/ncc_postcode_zones.yaml
  ```
  Single-zone postcodes become derived entries (confidence 0.8, below the
  official NatHERS table's 0.9); postcodes spanning multiple zones become
  low-confidence `ambiguous` entries. **Not built here:** ABS POA boundaries
  (`abs.gov.au`) were not reachable from the sandbox, so no crosswalk is shipped.

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
