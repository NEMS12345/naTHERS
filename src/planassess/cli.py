"""PlanAssess command-line interface.

P0 commands:
    planassess version
    planassess demo   --state NSW --postcode 2000 --out ./out
    planassess assess <plan> --state NSW --postcode 2000 --out ./out

In P0, `assess` accepts a pre-built building_model.json (the canonical model).
Plan-file ingestion adapters (DXF/DWG/PDF) are wired in from P1 onward; until an
adapter exists for a given format, `assess` reports that clearly rather than
guessing.
"""

from __future__ import annotations

from pathlib import Path

import typer

from .constants import NOT_A_CERTIFICATE_CAVEAT
from .ingest import AdapterNotAvailable
from .ingest import ingest as ingest_plan
from .model.building import BuildingModel
from .model.enums import State
from .pipeline import run_pipeline
from .samples import synthetic_house
from .version import __version__

app = typer.Typer(
    add_completion=False,
    help="PlanAssess — indicative NatHERS thermal + jurisdiction sustainability PRE-ASSESSMENT. "
    "Not a certificate.",
)


def _emit(review, compliance, written) -> None:
    typer.echo("")
    typer.secho(NOT_A_CERTIFICATE_CAVEAT, fg=typer.colors.YELLOW)
    typer.echo("")
    typer.echo(f"Strategy: {compliance.strategy.value} (mandatory={compliance.mandatory})")
    typer.echo(f"Fields flagged for review: {len(review.gaps)} / {review.total_tracked} tracked")
    typer.echo("Outputs:")
    for path in written:
        typer.echo(f"  - {path}")


@app.command()
def version() -> None:
    """Print the PlanAssess version."""
    typer.echo(f"PlanAssess {__version__}")


@app.command()
def demo(
    state: State = typer.Option(State.NSW, help="State/territory for the demo dwelling."),
    postcode: str = typer.Option("2000", help="Postcode for climate-zone lookup."),
    out: Path = typer.Option(Path("./out"), help="Output directory."),
) -> None:
    """Run the full pipeline over a built-in synthetic house (no plan file needed)."""
    model = synthetic_house(postcode=postcode)
    # Keep the sample's state consistent with the requested jurisdiction.
    from .model.enums import Provenance
    from .model.tracked import observed

    model.project.state = observed(state, Provenance.HUMAN, 1.0)
    model.extraction_meta.source_file = "<synthetic demo>"
    model.extraction_meta.adapter = "samples.synthetic_house"
    review, compliance, written = run_pipeline(model, state, out)
    _emit(review, compliance, written)


@app.command()
def assess(
    plan: Path = typer.Argument(..., help="Plan file (DXF/DWG/PDF) or a building_model.json."),
    state: State = typer.Option(..., help="State/territory (selects compliance strategy)."),
    postcode: str | None = typer.Option(None, help="Postcode for climate-zone lookup."),
    out: Path = typer.Option(Path("./out"), help="Output directory."),
) -> None:
    """Assess a plan. P0 supports building_model.json input; adapters land in later phases."""
    if not plan.exists():
        typer.secho(f"File not found: {plan}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)

    suffix = plan.suffix.lower()
    if suffix == ".json":
        model = BuildingModel.model_validate_json(plan.read_text(encoding="utf-8"))
        model.extraction_meta.source_file = str(plan)
        model.extraction_meta.adapter = model.extraction_meta.adapter or "building_model.json"
    else:
        try:
            model = ingest_plan(plan, project_id=plan.stem)
        except AdapterNotAvailable as exc:
            typer.secho(
                f"{exc} Provide a building_model.json for now, or run `planassess demo`.",
                fg=typer.colors.YELLOW,
                err=True,
            )
            raise typer.Exit(code=3)
        except Exception as exc:  # parsing failure -> report, don't crash
            typer.secho(f"Could not ingest '{plan}': {exc}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=4)

    # Postcode supplied on the CLI overrides/fills what the adapter couldn't read.
    if postcode:
        from .model.enums import Provenance
        from .model.tracked import observed

        model.project.postcode = observed(postcode, Provenance.HUMAN, 1.0)

    review, compliance, written = run_pipeline(model, state, out)
    _emit(review, compliance, written)


if __name__ == "__main__":
    app()
