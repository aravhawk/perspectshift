"""inspect command group."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from perceptshift_cli import output
from perceptshift_common.errors import ErrorCode, PerceptShiftError
from perceptshift_common.reason_codes import ReasonCode
from perceptshift_forge.bundle import verify_bundle
from perceptshift_forge.inspection import run_doctor
from perceptshift_forge.models.inspect import inspect_onnx_model
from perceptshift_forge.runs.storage import list_runs

app = typer.Typer(help="Inspect host, model, bundle, or run")


@app.command("host")
def host_cmd(ctx: typer.Context) -> None:
    report = run_doctor()
    output.emit(ctx, report)


@app.command("model")
def model_cmd(
    ctx: typer.Context,
    path: Path = typer.Argument(..., exists=True, dir_okay=False),
) -> None:
    result = inspect_onnx_model(path)
    output.emit(ctx, result.report)


@app.command("bundle")
def bundle_cmd(
    ctx: typer.Context,
    path: Path = typer.Argument(..., exists=True, file_okay=False),
) -> None:
    report = verify_bundle(path)
    output.emit(ctx, report)


@app.command("run")
def run_cmd(
    ctx: typer.Context,
    run_id: str | None = typer.Argument(None),
) -> None:
    runs = list_runs()
    if run_id is None:
        output.emit(ctx, {"runs": runs})
        return
    match = next((r for r in runs if r.get("run_id") == run_id), None)
    if match is None:
        raise PerceptShiftError(
            code=ErrorCode.NOT_FOUND,
            message=f"Run not found: {run_id}",
            details={"reason_code": ReasonCode.UNAVAILABLE_DATA},
        )
    run_json = Path(str(match["root"])) / "run.json"
    payload = json.loads(run_json.read_text(encoding="utf-8")) if run_json.is_file() else match
    output.emit(ctx, payload)
