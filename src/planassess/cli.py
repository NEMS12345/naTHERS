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
from .pipeline import review_only, run_pipeline
from .samples import synthetic_house
from .version import __version__


def _load_model(plan: Path):
    """Load a BuildingModel from a plan file (.json or via an ingestion adapter)."""
    if plan.suffix.lower() == ".json":
        model = BuildingModel.model_validate_json(plan.read_text(encoding="utf-8"))
        model.extraction_meta.source_file = str(plan)
        model.extraction_meta.adapter = model.extraction_meta.adapter or "building_model.json"
        return model
    return ingest_plan(plan, project_id=plan.stem)

app = typer.Typer(
    add_completion=False,
    help="PlanAssess — indicative NatHERS thermal + jurisdiction sustainability PRE-ASSESSMENT. "
    "Not a certificate.",
)


def _emit(out) -> None:
    typer.echo("")
    typer.secho(NOT_A_CERTIFICATE_CAVEAT, fg=typer.colors.YELLOW)
    typer.echo("")
    t = out.thermal
    if t.computed:
        typer.echo(
            f"Indicative thermal: {t.indicative_star} star "
            f"(target {t.star_target}) · total {t.total_load_mj_per_m2} MJ/m².yr — INDICATIVE ONLY"
        )
    else:
        typer.echo("Indicative thermal: not computable — insufficient data (see gap report)")
    typer.echo(f"Strategy: {out.compliance.strategy.value} (mandatory={out.compliance.mandatory})")
    for c in out.compliance.categories:
        verdict = "PASS" if c.passed else ("FAIL" if c.passed is False else "n/a")
        typer.echo(f"  - {c.name}: {verdict} (value {c.value} vs target {c.target})")
    typer.echo(
        f"Fields flagged for review: {len(out.review.gaps)} / {out.review.total_tracked} tracked"
    )
    typer.echo("Outputs:")
    for path in out.written:
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
    _emit(run_pipeline(model, state, out))


@app.command()
def review(
    plan: Path = typer.Argument(..., help="Plan file (DXF/DWG/PDF) or a building_model.json."),
    postcode: str | None = typer.Option(None, help="Postcode for state + climate-zone lookup."),
    out: Path = typer.Option(Path("./out"), help="Output directory."),
) -> None:
    """Extract and gate only: write the gap report and an editable review_template.csv.

    Fill the `your_value` column, then feed it to `assess --apply-review`.
    """
    if not plan.exists():
        typer.secho(f"File not found: {plan}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)
    try:
        model = _load_model(plan)
    except AdapterNotAvailable as exc:
        typer.secho(str(exc), fg=typer.colors.YELLOW, err=True)
        raise typer.Exit(code=3)
    except Exception as exc:
        typer.secho(f"Could not ingest '{plan}': {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=4)

    if postcode:
        from .model.enums import Provenance
        from .model.tracked import observed

        model.project.postcode = observed(postcode, Provenance.HUMAN, 1.0)

    from .model.validation import check_integrity

    for issue in check_integrity(model):
        typer.secho(f"  integrity: {issue}", fg=typer.colors.YELLOW, err=True)

    result, written = review_only(model, out)
    typer.echo(f"Flagged {len(result.gaps)} / {result.total_tracked} fields for review.")
    for path in written:
        typer.echo(f"  - {path}")
    typer.echo("Fill the `your_value` column in review_template.csv, then run "
               "`planassess assess <plan> --apply-review review_template.csv`.")


@app.command()
def assess(
    plan: Path = typer.Argument(..., help="Plan file (DXF/DWG/PDF) or a building_model.json."),
    state: State | None = typer.Option(
        None, help="State/territory (selects compliance strategy). Derived from postcode if omitted."
    ),
    postcode: str | None = typer.Option(None, help="Postcode for state + climate-zone lookup."),
    apply_review_csv: Path | None = typer.Option(
        None, "--apply-review", help="Filled review_template.csv to merge before assessing."
    ),
    out: Path = typer.Option(Path("./out"), help="Output directory."),
) -> None:
    """Assess a plan (DXF/DWG/PDF or building_model.json) and write the pre-assessment pack."""
    if not plan.exists():
        typer.secho(f"File not found: {plan}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)

    try:
        model = _load_model(plan)
    except AdapterNotAvailable as exc:
        typer.secho(
            f"{exc} Provide a building_model.json for now, or run `planassess demo`.",
            fg=typer.colors.YELLOW, err=True,
        )
        raise typer.Exit(code=3)
    except Exception as exc:  # parsing failure -> report, don't crash
        typer.secho(f"Could not ingest '{plan}': {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=4)

    from .model.enums import Provenance
    from .model.tracked import observed

    # Apply human review answers (if supplied) before assessing.
    if apply_review_csv is not None:
        if not apply_review_csv.exists():
            typer.secho(f"Review file not found: {apply_review_csv}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=2)
        from .review.review_io import apply_review

        applied, errors = apply_review(model, apply_review_csv)
        typer.echo(f"Applied {len(applied)} human review answer(s).")
        for err in errors:
            typer.secho(f"  review skip: {err.path} -> {err.error}", fg=typer.colors.YELLOW, err=True)

    # Postcode supplied on the CLI overrides/fills what the adapter couldn't read.
    if postcode:
        model.project.postcode = observed(postcode, Provenance.HUMAN, 1.0)

    # Resolve the jurisdiction: explicit --state wins; otherwise derive from postcode.
    if state is not None:
        model.project.state = observed(state, Provenance.HUMAN, 1.0)
        resolved = state
    else:
        from .config.postcode_state import state_from_postcode

        derived = state_from_postcode(postcode)
        if derived.is_missing:
            typer.secho(
                "Could not determine the state/territory: pass --state, or a valid Australian "
                "--postcode to derive it.",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(code=2)
        resolved = derived.value
        typer.echo(f"State derived from postcode {postcode}: {resolved.value} (confidence {derived.confidence:.2f})")

    _emit(run_pipeline(model, resolved, out))


if __name__ == "__main__":
    app()
