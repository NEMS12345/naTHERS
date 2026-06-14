"""Runtime selection and execution of the jurisdiction compliance strategy.

NSW -> BASIX (Energy/Water/Thermal Comfort). All other states/territories ->
NatHERS Whole-of-Home. NT -> WoH not mandatory (marked not required).
"""

from __future__ import annotations

from ..config.models import JurisdictionConfig, JurisdictionsConfig
from ..model.building import BuildingModel
from ..model.enums import JurisdictionStrategy, State
from .basix import assess_basix
from .results import ComplianceResult
from .thermal import ThermalResult
from .woh import assess_woh


def select_strategy(
    state: State, config: JurisdictionsConfig
) -> tuple[JurisdictionStrategy, JurisdictionConfig]:
    """Pick the compliance strategy for a state/territory from config."""
    jc = config.for_state(state.value)
    return jc.strategy, jc


def run_compliance(
    model: BuildingModel,
    state: State,
    config: JurisdictionsConfig,
    thermal: ThermalResult | None = None,
) -> ComplianceResult:
    """Select and run the jurisdiction compliance pre-assessment."""
    strategy, jc = select_strategy(state, config)

    if strategy == JurisdictionStrategy.BASIX:
        if jc.basix is None:
            raise ValueError("NSW jurisdiction config is missing the 'basix' section.")
        categories = assess_basix(model, jc.basix)
        result = ComplianceResult(
            state=state, strategy=strategy, mandatory=True, implemented=True,
            categories=categories,
            summary="NSW BASIX pre-assessment (Energy, Water, Thermal Comfort).",
        )
        return result

    # NatHERS Whole-of-Home.
    mandatory = jc.woh.mandatory if jc.woh else True
    if not mandatory:
        return ComplianceResult(
            state=state, strategy=strategy, mandatory=False, implemented=True,
            summary=(
                f"{state.value}: NatHERS Whole-of-Home is NOT mandatory in this "
                "jurisdiction — marked not required."
            ),
        )
    benchmark = jc.woh.benchmark_score if jc.woh and jc.woh.benchmark_score is not None else 60.0
    category = assess_woh(model, benchmark, thermal=thermal)
    return ComplianceResult(
        state=state, strategy=strategy, mandatory=True, implemented=True,
        categories=[category],
        summary=f"{state.value}: NatHERS Whole-of-Home pre-assessment (indicative score vs {benchmark}).",
    )
