"""certify command group."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from perceptshift_cli import output
from perceptshift_forge.certification import is_certified, run_certification_gates

app = typer.Typer(help="Certification gates")


@app.command("run")
def run_cmd(
    ctx: typer.Context,
    context_path: Path = typer.Argument(..., exists=True, dir_okay=False),
) -> None:
    ctx_doc = json.loads(context_path.read_text(encoding="utf-8"))
    results = run_certification_gates(ctx_doc)
    payload = {
        "certified": is_certified(results),
        "gates": [r.to_dict() for r in results],
    }
    output.emit(ctx, payload)


@app.command("explain")
def explain_cmd(
    ctx: typer.Context,
    context_path: Path = typer.Argument(..., exists=True, dir_okay=False),
) -> None:
    ctx_doc = json.loads(context_path.read_text(encoding="utf-8"))
    results = run_certification_gates(ctx_doc)
    failed = [r.to_dict() for r in results if not r.passed]
    output.emit(ctx, {"failed_gates": failed, "certified": is_certified(results)})
