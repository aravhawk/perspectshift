"""forge command group."""

from __future__ import annotations

from pathlib import Path

import typer

from perceptshift_cli import output
from perceptshift_forge.orchestration import resume_forge, run_forge
from perceptshift_forge.runs.storage import list_runs

app = typer.Typer(help="Forge orchestration")


@app.command("run")
def run_cmd(
    ctx: typer.Context,
    config: Path = typer.Option(..., "--config", exists=True, dir_okay=False),
    maximum_candidates: int = typer.Option(256, "--maximum-candidates"),
) -> None:
    result = run_forge(config, maximum_candidates=maximum_candidates)
    output.emit(ctx, result)


@app.command("resume")
def resume_cmd(
    ctx: typer.Context,
    run_root: Path = typer.Argument(..., exists=True, file_okay=False),
    maximum_candidates: int = typer.Option(256, "--maximum-candidates"),
) -> None:
    result = resume_forge(run_root, maximum_candidates=maximum_candidates)
    output.emit(ctx, result)


@app.command("status")
def status_cmd(ctx: typer.Context) -> None:
    output.emit(ctx, {"runs": list_runs()})
