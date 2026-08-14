"""system command group."""

from __future__ import annotations

import typer

from perceptshift_cli import output
from perceptshift_common.paths import path_inventory

app = typer.Typer(help="System path and benchmark environment helpers")


@app.command("paths")
def paths_cmd(ctx: typer.Context) -> None:
    output.emit(ctx, path_inventory())


@app.command("prepare-benchmark")
def prepare_cmd(ctx: typer.Context) -> None:
    output.emit(
        ctx,
        {
            "status": "noop",
            "message": "No system governor changes applied; document host prep manually",
        },
    )


@app.command("restore-benchmark")
def restore_cmd(ctx: typer.Context) -> None:
    output.emit(
        ctx,
        {
            "status": "noop",
            "message": "No system governor changes to restore",
        },
    )
