"""Derive a postcode → NCC climate zone (1–8) crosswalk by spatial join.

The authoritative ABCB "Australian Climate zone map" (CC BY 4.0, data.gov.au) is
GEOSPATIAL ONLY: eight zone polygons keyed by a ``clim_zone`` attribute, with no
postcode attribute. To get a postcode → NCC-zone crosswalk we spatially join the
zone polygons against ABS Postal Area (POA) boundaries: for each postcode we keep
every NCC zone whose polygon intersects that postcode's polygon.

* a postcode intersecting a single zone -> ``postcodes`` entry (derived, but a
  clean single match -> reasonably high confidence);
* a postcode intersecting >1 zone       -> low-confidence ``ambiguous`` entry, so
  the review gate flags it instead of silently picking one.

This mirrors scripts/build_climate_zone_table.py (the NatHERS importer). It is
NOT run automatically: neither the ABCB polygons nor the ABS POA boundaries are
vendored. Download both, then:

    pip install pyshp shapely
    python scripts/build_ncc_zone_table.py \
        "Climate zones AU.shp" POA_2021_AUST.shp --out config/ncc_postcode_zones.yaml

Sources (verify currency before use):
    ABCB zones:   https://data.gov.au/data/dataset/australian-climate-zone-map
    ABS POA 2021: https://www.abs.gov.au/statistics/standards/australian-statistical-geography-standard-asgs-edition-3
"""

from __future__ import annotations

import argparse
import datetime as _dt
from collections import OrderedDict
from pathlib import Path

# confidence assigned to a postcode that intersects exactly one NCC zone. Lower
# than the NatHERS importer's 0.9 because this value is spatially DERIVED, not
# read from an official postcode table.
SINGLE_ZONE_CONFIDENCE = 0.8
AMBIGUOUS_CONFIDENCE = 0.4

ATTRIBUTION = (
    "Derived from the ABCB 'Australian Climate zone map' (CC BY 4.0) and ABS "
    "Postal Area boundaries by spatial join. Indicative cross-reference only."
)


def to_table(records: dict[str, list[int]]) -> tuple[dict, dict]:
    """Split a {postcode: [zones]} mapping into (postcodes, ambiguous) tables.

    Pure and side-effect free so it can be unit-tested without GIS libraries.
    """
    postcodes: "OrderedDict[str, dict]" = OrderedDict()
    ambiguous: "OrderedDict[str, dict]" = OrderedDict()
    for pc in sorted(records):
        zones = sorted({z for z in records[pc] if 1 <= z <= 8})
        if not zones:
            continue
        if len(zones) == 1:
            postcodes[pc] = {"zone": zones[0], "confidence": SINGLE_ZONE_CONFIDENCE}
        else:
            ambiguous[pc] = {
                "zones": zones,
                "confidence": AMBIGUOUS_CONFIDENCE,
                "note": "Postcode spans multiple NCC climate zones (derived by spatial join).",
            }
    return postcodes, ambiguous


def _field_index(reader, candidates: tuple[str, ...]) -> int:
    """Index of the first shapefile field whose name matches a candidate."""
    names = [f[0] for f in reader.fields[1:]]  # skip DeletionFlag
    lower = [n.lower() for n in names]
    for cand in candidates:
        for i, n in enumerate(lower):
            if cand in n:
                return i
    raise SystemExit(f"None of {candidates} found in shapefile fields {names}.")


def spatial_join(zones_shp: Path, poa_shp: Path) -> dict[str, list[int]]:
    """Intersect ABCB zone polygons with ABS POA polygons -> {postcode: [zones]}."""
    import shapefile  # pyshp
    from shapely.geometry import shape  # shapely
    from shapely.strtree import STRtree

    zr = shapefile.Reader(str(zones_shp))
    zfld = _field_index(zr, ("clim_zone", "zone"))
    zone_geoms: list = []
    zone_nums: list[int] = []
    for sr in zr.iterShapeRecords():
        try:
            num = int(str(sr.record[zfld]).strip())
        except (TypeError, ValueError):
            continue
        zone_geoms.append(shape(sr.shape.__geo_interface__))
        zone_nums.append(num)
    tree = STRtree(zone_geoms)

    pr = shapefile.Reader(str(poa_shp))
    pfld = _field_index(pr, ("poa_code", "postcode", "poa"))
    out: dict[str, list[int]] = {}
    for sr in pr.iterShapeRecords():
        pc = "".join(ch for ch in str(sr.record[pfld]) if ch.isdigit())
        if len(pc) != 4:
            continue
        geom = shape(sr.shape.__geo_interface__)
        hits = {zone_nums[i] for i in tree.query(geom) if geom.intersects(zone_geoms[i])}
        if hits:
            out.setdefault(pc, [])
            out[pc] = sorted(set(out[pc]) | hits)
    return out


def to_yaml(postcodes: dict, ambiguous: dict, source: str) -> str:
    import yaml

    doc = {
        "version": f"abcb-ncc-derived-{_dt.date.today().isoformat()}",
        "source": source,
        "attribution": ATTRIBUTION,
        "postcodes": {k: dict(v) for k, v in postcodes.items()},
        "ambiguous": {k: dict(v) for k, v in ambiguous.items()},
    }
    return yaml.safe_dump(doc, sort_keys=False, default_flow_style=False)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("zones", type=Path, help="ABCB climate-zone polygons (.shp)")
    ap.add_argument("poa", type=Path, help="ABS Postal Area boundaries (.shp)")
    ap.add_argument("--out", type=Path, default=Path("config/ncc_postcode_zones.yaml"))
    args = ap.parse_args()

    records = spatial_join(args.zones, args.poa)
    postcodes, ambiguous = to_table(records)
    source = f"{args.zones.name} x {args.poa.name}"
    args.out.write_text(to_yaml(postcodes, ambiguous, source), encoding="utf-8")
    print(f"wrote {args.out}: {len(postcodes)} postcodes, {len(ambiguous)} ambiguous")


if __name__ == "__main__":
    main()
