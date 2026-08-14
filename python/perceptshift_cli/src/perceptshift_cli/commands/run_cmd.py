"""run command group."""

from __future__ import annotations

from pathlib import Path

import typer

from perceptshift_cli import output
from perceptshift_common.errors import ErrorCode, PerceptShiftError
from perceptshift_common.reason_codes import ReasonCode
from perceptshift_forge.orchestration import find_native_binary, launch_bench_worker

app = typer.Typer(help="Standalone runtime helpers")


@app.command("standalone")
def standalone_cmd(
    ctx: typer.Context,
    config: Path = typer.Option(..., "--config", exists=True, dir_okay=False),
    timeout_seconds: float = typer.Option(30.0, "--timeout-seconds"),
) -> None:
    binary = find_native_binary("perceptshift_runtime") or find_native_binary("runtime")
    if binary is None:
        raise PerceptShiftError(
            code=ErrorCode.DEPENDENCY_UNAVAILABLE,
            message="Native runtime binary not found",
            details={"reason_code": ReasonCode.UNAVAILABLE_NATIVE_BINARY},
            remediation="Build cpp/ apps and ensure perceptshift_runtime is on PATH",
        )
    result = launch_bench_worker(
        worker_argv=[str(binary), "--config", str(config)],
        cwd=Path.cwd(),
        timeout_seconds=timeout_seconds,
    )
    output.emit(ctx, result)
