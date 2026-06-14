"""Shared result envelopes for the jurisdiction compliance pre-assessment."""

from __future__ import annotations

from pydantic import BaseModel

from ..model.enums import JurisdictionStrategy, State


class CategoryResult(BaseModel):
    """One assessable category (e.g. BASIX Water, or WoH energy)."""

    name: str
    value: float | None = None       # indicative computed metric
    target: float | None = None
    unit: str | None = None
    passed: bool | None = None        # None when it could not be assessed
    margin: float | None = None       # value - target (signed; positive = better)
    method: str | None = None
    assumptions: list[str] = []
    missing_inputs: list[str] = []
    notes: list[str] = []


class ComplianceResult(BaseModel):
    """Result envelope shared by both jurisdiction strategies."""

    state: State
    strategy: JurisdictionStrategy
    mandatory: bool = True
    implemented: bool = False
    summary: str = ""
    categories: list[CategoryResult] = []

    @property
    def overall_pass(self) -> bool | None:
        """True only if every assessable category passes; None if none assessable."""
        assessed = [c.passed for c in self.categories if c.passed is not None]
        if not assessed:
            return None
        return all(assessed)
