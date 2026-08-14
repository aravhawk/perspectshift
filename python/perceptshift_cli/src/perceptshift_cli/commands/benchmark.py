"""benchmark command group."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from perceptshift_cli import output
from perceptshift_common.errors import ErrorCode, PerceptShiftError
from perceptshift_common.reason_codes import ReasonCode
from perceptshift_forge.orchestration import launch_bench_worker
from perceptshift_forge.statistics import summarize_latencies

app = typer.Typer(help="Benchmark worker helpers")


@app.command("run")
def run_cmd(
    ctx: typer.Context,
    worker: Path = typer.Option(..., "--worker", exists=True, dir_okay=False),
    request: Path = typer.Option(..., "--request", exists=True, dir_okay=False),
    cwd: Path | None = typer.Option(None, "--cwd"),
    timeout_seconds: float = typer.Option(900.0, "--timeout-seconds"),
) -> None:
    result = launch_bench_worker(
        worker_argv=[str(worker), "--request", str(request)],
        cwd=cwd or Path.cwd(),
        timeout_seconds=timeout_seconds,
    )
    output.emit(ctx, result)


@app.command("resume")
def resume_cmd(ctx: typer.Context, run_root: Path = typer.Argument(..., exists=True)) -> None:
    raise PerceptShiftError(
        code=ErrorCode.DEPENDENCY_UNAVAILABLE,
        message="Standalone benchmark resume is available through `perceptshift forge resume`",
        details={"reason_code": ReasonCode.UNAVAILABLE_DATA},
    )


@app.command("summarize")
def summarize_cmd(
    ctx: typer.Context,
    samples: Path = typer.Argument(..., exists=True, dir_okay=False),
    bootstrap_resamples: int = typer.Option(0, "--bootstrap-resamples"),
    seed: int = typer.Option(1729, "--seed"),
) -> None:
    values: list[float] = []
    for line in samples.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("valid") is False:
            continue
        duration = row.get("inference_duration_ns") or row.get("total_duration_ns")
        if duration is None:
            continue
        values.append(float(duration))
    if not values:
        raise PerceptShiftError(
            code=ErrorCode.NOT_FOUND,
            message="No valid latency samples found",
        )
    stats = summarize_latencies(values, bootstrap_resamples=bootstrap_resamples, seed=seed)
    output.emit(ctx, stats.to_dict())


@app.command("compare")
def compare_cmd(
    ctx: typer.Context,
    left: Path = typer.Argument(..., exists=True, dir_okay=False),
    right: Path = typer.Argument(..., exists=True, dir_okay=False),
) -> None:
    left_doc = json.loads(left.read_text(encoding="utf-8"))
    right_doc = json.loads(right.read_text(encoding="utf-8"))
    output.emit(ctx, {"left": left_doc, "right": right_doc})
