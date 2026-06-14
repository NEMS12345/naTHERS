"""Referential-integrity checks for the canonical Building Model.

The relational links (dwelling_id / zone_id / wall_id) are plain string fields,
so nothing stops an ingestion adapter emitting a dangling reference or duplicate
id. These checks surface such structural problems early (e.g. a wall pointing at
a zone that does not exist) without touching the domain data.
"""

from __future__ import annotations

from .building import BuildingModel


def check_integrity(model: BuildingModel) -> list[str]:
    """Return a list of referential-integrity problems (empty when sound)."""
    issues: list[str] = []

    def _dupes(kind: str, ids: list[str]) -> set[str]:
        seen: set[str] = set()
        dup: set[str] = set()
        for i in ids:
            (dup if i in seen else seen).add(i)
        for d in dup:
            issues.append(f"duplicate {kind} id: {d!r}")
        return seen

    dwelling_ids = _dupes("dwelling", [d.id for d in model.dwellings])
    zone_ids = _dupes("zone", [z.id for z in model.zones])
    wall_ids = _dupes("wall", [w.id for w in model.walls])

    def _ref(kind: str, owner: str, ref: str | None, valid: set[str]) -> None:
        if ref is not None and ref not in valid:
            issues.append(f"{kind} {owner!r} references missing id {ref!r}")

    for z in model.zones:
        _ref("zone", z.id, z.dwelling_id, dwelling_ids)
    for w in model.walls:
        _ref("wall", w.id, w.zone_id, zone_ids)
    for r in model.roofs:
        _ref("roof", r.id, r.zone_id, zone_ids)
    for f in model.floors:
        _ref("floor", f.id, f.zone_id, zone_ids)
    for g in model.glazing:
        _ref("glazing", g.id, g.zone_id, zone_ids)
        _ref("glazing", g.id, g.wall_id, wall_ids)
    for d in model.doors:
        _ref("door", d.id, d.zone_id, zone_ids)
        _ref("door", d.id, d.wall_id, wall_ids)

    return issues
