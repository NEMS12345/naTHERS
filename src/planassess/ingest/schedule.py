"""Tolerant parser for window/door schedule text found on plans.

Real schedules vary widely, so the parser extracts whatever it recognises and
sets confidence from how many fields were found — partial parses still flow
through with the missing pieces gap-flagged rather than guessed.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from ..model.enums import Orientation

_ID_RE = re.compile(r"\b([WD]\d+)\b")
_DIM_RE = re.compile(r"(\d{3,5})\s*[x×]\s*(\d{3,5})")  # e.g. 2000x1500 (mm)
_U_RE = re.compile(r"\bU\s*=\s*([\d.]+)", re.IGNORECASE)
_SHGC_RE = re.compile(r"\bSHGC\s*=\s*([\d.]+)", re.IGNORECASE)
_ORIENT_RE = re.compile(r"\b(N|NE|E|SE|S|SW|W|NW)\b")
_FRAME_RE = re.compile(r"\b(aluminium|aluminum|timber|upvc|pvc|steel|composite)\b", re.IGNORECASE)
_GLASS_RE = re.compile(r"\b(single|double|triple|low-?e|tinted|clear|laminated)\b", re.IGNORECASE)


class ScheduleItem(BaseModel):
    raw: str
    item_id: str | None = None
    is_door: bool = False
    room: str | None = None
    orientation: Orientation | None = None
    width_mm: float | None = None
    height_mm: float | None = None
    frame: str | None = None
    glazing_type: str | None = None
    u_value: float | None = None
    shgc: float | None = None
    confidence: float = 0.0

    @property
    def area_m2(self) -> float | None:
        if self.width_mm and self.height_mm:
            return round(self.width_mm * self.height_mm / 1_000_000, 3)
        return None


def parse_schedule_line(line: str) -> ScheduleItem | None:
    """Parse one schedule line. Returns None if it has no W#/D# identifier."""
    id_match = _ID_RE.search(line)
    if not id_match:
        return None

    item_id = id_match.group(1)
    parts = [p.strip() for p in line.split("|")]
    fields_found = 1  # the id itself

    item = ScheduleItem(raw=line, item_id=item_id, is_door=item_id.startswith("D"))

    if dim := _DIM_RE.search(line):
        item.width_mm = float(dim.group(1))
        item.height_mm = float(dim.group(2))
        fields_found += 1
    if (m := _U_RE.search(line)) and not item.is_door:
        item.u_value = float(m.group(1))
        fields_found += 1
    if (m := _SHGC_RE.search(line)) and not item.is_door:
        item.shgc = float(m.group(1))
        fields_found += 1
    if m := _FRAME_RE.search(line):
        item.frame = m.group(1)
        fields_found += 1
    if (m := _GLASS_RE.search(line)) and not item.is_door:
        item.glazing_type = m.group(0)
        fields_found += 1
    # Orientation: prefer a standalone pipe field to avoid matching letters in words.
    for p in parts:
        if _ORIENT_RE.fullmatch(p):
            item.orientation = Orientation(p)
            fields_found += 1
            break
    # Room: the first pipe field that is not the id, a dimension, or a known token.
    for p in parts[1:]:
        if p and not _DIM_RE.search(p) and not _ORIENT_RE.fullmatch(p) and "=" not in p:
            if not _FRAME_RE.fullmatch(p) and not _GLASS_RE.fullmatch(p):
                item.room = p
                break

    # Confidence scales with how complete the parse is (windows expect more fields).
    expected = 4 if item.is_door else 7
    item.confidence = round(min(0.9, 0.35 + 0.1 * fields_found), 2)
    return item


def parse_schedule(lines: list[str]) -> list[ScheduleItem]:
    items: list[ScheduleItem] = []
    for line in lines:
        if parsed := parse_schedule_line(line):
            items.append(parsed)
    return items
