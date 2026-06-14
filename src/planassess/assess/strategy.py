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


def _adoption_context(state: State, jc: JurisdictionConfig) -> str:
    """One-line NCC 2022 adoption/7-star status for the jurisdiction (from config)."""
    if jc.ncc2022_adoption_date:
        base = f"NCC 2022 energy provisions adopted in {state.value} from {jc.ncc2022_adoption_date}"
    else:
        base = f"{state.value} has not adopted the NCC 2022 7-star/WoH energy provisions"
    star = "7-star thermal mandatory" if jc.seven_star_mandatory else "7-star thermal NOT yet mandated"
    return f"{base}; {star}."


def run_compliance(
    model: BuildingModel,
    state: State,
    config: JurisdictionsConfig,
    thermal: ThermalResult | None = None,
) -> ComplianceResult:
    """Select and run the jurisdiction compliance pre-assessment."""
    strategy, jc = select_strategy(state, config)
    adoption = _adoption_context(state, jc)

    if strategy == JurisdictionStrategy.BASIX:
        if jc.basix is None:
            raise ValueError("NSW jurisdiction config is missing the 'basix' section.")
        categories = assess_basix(model, jc.basix)
        return ComplianceResult(
            state=state, strategy=strategy, mandatory=True, implemented=True,
            categories=categories,
            summary=f"NSW BASIX pre-assessment (Energy, Water, Thermal Comfort). {adoption}",
        )

    # NatHERS Whole-of-Home.
    mandatory = jc.woh.mandatory if jc.woh else True
    if not mandatory:
        return ComplianceResult(
            state=state, strategy=strategy, mandatory=False, implemented=True,
            summary=(
                f"{state.value}: NatHERS Whole-of-Home is NOT mandatory in this "
                f"jurisdiction — marked not required. {adoption}"
            ),
        )
    benchmark = jc.woh.benchmark_score if jc.woh and jc.woh.benchmark_score is not None else 60.0
    category = assess_woh(model, benchmark, thermal=thermal)
    return ComplianceResult(
        state=state, strategy=strategy, mandatory=True, implemented=True,
        categories=[category],
        summary=(
            f"{state.value}: NatHERS Whole-of-Home pre-assessment (indicative score "
            f"vs {benchmark}). {adoption}"
        ),
    )
