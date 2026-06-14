#!/usr/bin/env bash
# End-to-end CLI smoke test: drive PlanAssess over each committed fixture and
# assert the expected artefacts are produced. Used locally and in CI.
set -euo pipefail

OUT="${1:-out/smoke}"
rm -rf "$OUT"
mkdir -p "$OUT"

fail() { echo "SMOKE FAIL: $1" >&2; exit 1; }
check() { [ -s "$1" ] || fail "missing/empty output: $1"; }

echo "== demo (NSW / BASIX) =="
planassess demo --state NSW --postcode 2000 --out "$OUT/demo"
check "$OUT/demo/building_model.json"
check "$OUT/demo/assessment_report.md"
check "$OUT/demo/gap_report.md"
check "$OUT/demo/input_pack.csv"

echo "== assess DXF (NSW) =="
planassess assess tests/fixtures/synthetic_house.dxf --state NSW --postcode 2000 --out "$OUT/dxf"
check "$OUT/dxf/building_model.json"
check "$OUT/dxf/assessment_report.md"

echo "== assess PDF vector (VIC / WoH) =="
planassess assess tests/fixtures/synthetic_house.pdf --state VIC --postcode 3000 --out "$OUT/pdf"
check "$OUT/pdf/building_model.json"

echo "== assess PDF raster scan (QLD) =="
planassess assess tests/fixtures/synthetic_house_scan.pdf --state QLD --postcode 4000 --out "$OUT/scan"
check "$OUT/scan/building_model.json"

echo "== assess NT (WoH not required) =="
planassess assess tests/fixtures/synthetic_house.dxf --state NT --postcode 0800 --out "$OUT/nt"
grep -qi "not required\|not mandatory" "$OUT/nt/assessment_report.md" \
  || fail "NT report should mark WoH not required"

echo "SMOKE OK -> $OUT"
