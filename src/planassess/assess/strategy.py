"""Runtime selection of the jurisdiction compliance strategy.

NSW -> BASIX. All other states/territories -> NatHERS Whole-of-Home (WoH).
NT -> WoH not mandatory (marked not required).

P0 wires the selection end to end and returns a typed placeholder result; the
BASIX and WoH calculation modules land in P2.
"""

from __future__ import annotations

from pydantic import BaseModel

from ..config.models import JurisdictionConfig, JurisdictionsConfig
from ..model.building import BuildingModel
from ..model.enums import JurisdictionStrategy, State


class ComplianceResult(BaseModel):
    """Result envelope shared by both strategies."""

    state: State
    strategy: JurisdictionStrategy
    mandatory: bool = True
    implemented: bool = False  # P0: calculation modules arrive in P2
    summary: str = ""
    categories: dict[str, str] = {}  # category -> indicative pass/fail/margin (P2)


def select_strategy(state: State, config: JurisdictionsConfig) -> tuple[JurisdictionStrategy, JurisdictionConfig]:
    """Pick the compliance strategy for a state/territory from config."""
    jc = config.for_state(state.value)
    return jc.strategy, jc


def run_compliance(model: BuildingModel, state: State, config: JurisdictionsConfig) -> ComplianceResult:
    """Select and run (P0: stub) the jurisdiction compliance pre-assessment."""
    strategy, jc = select_strategy(state, config)

    if strategy == JurisdictionStrategy.WOH:
        mandatory = jc.woh.mandatory if jc.woh else True
        if not mandatory:
            return ComplianceResult(
                state=state,
                strategy=strategy,
                mandatory=False,
                implemented=True,
                summary=(
                    f"{state.value}: NatHERS Whole-of-Home is NOT mandatory in this "
                    "jurisdiction — marked not required."
                ),
            )
        return ComplianceResult(
            state=state,
            strategy=strategy,
            mandatory=True,
            implemented=False,
            summary=(
                f"{state.value}: NatHERS Whole-of-Home pre-assessment selected "
                "(calculation arrives in P2)."
            ),
        )

    # NSW BASIX
    return ComplianceResult(
        state=state,
        strategy=strategy,
        mandatory=True,
        implemented=False,
        summary="NSW: BASIX pre-assessment selected (Energy/Water/Thermal Comfort — calculation arrives in P2).",
    )
