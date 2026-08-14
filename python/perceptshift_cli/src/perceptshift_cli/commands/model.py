"""model command group."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import typer

from perceptshift_cli import output
from perceptshift_common.errors import ErrorCode, PerceptShiftError
from perceptshift_forge.models.inspect import inspect_onnx_model
from perceptshift_forge.quantization import CalibrationMethod, quantize_static_qdq

app = typer.Typer(help="Model inspect/preprocess/quantize helpers")


@app.command("inspect")
def inspect_cmd(
    ctx: typer.Context,
    path: Path = typer.Argument(..., exists=True, dir_okay=False),
) -> None:
    result = inspect_onnx_model(path)
    output.emit(ctx, result.report)


@app.command("validate")
def validate_cmd(
    ctx: typer.Context,
    path: Path = typer.Argument(..., exists=True, dir_okay=False),
) -> None:
    result = inspect_onnx_model(path)
    output.emit(
        ctx,
        {"ok": True, "sha256": result.sha256, "node_count": result.report["node_count"]},
    )


@app.command("preprocess")
def preprocess_cmd(
    ctx: typer.Context,
    path: Path = typer.Argument(..., exists=True, dir_okay=False),
    output_path: Path = typer.Option(..., "--output", exists=False),
) -> None:
    """Recorded preprocess: ONNX shape inference + checker, then write copy."""
    import onnx
    from onnx import checker, shape_inference

    model = onnx.load(str(path))
    inferred = shape_inference.infer_shapes(model)
    checker.check_model(inferred)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    onnx.save(inferred, str(output_path))
    result = inspect_onnx_model(output_path)
    output.emit(ctx, {"ok": True, "output": str(output_path), "sha256": result.sha256})


@app.command("quantize")
def quantize_cmd(
    ctx: typer.Context,
    path: Path = typer.Argument(..., exists=True, dir_okay=False),
    output_path: Path = typer.Option(..., "--output"),
    method: str = typer.Option("minmax", "--method"),
    input_name: str = typer.Option("input", "--input-name"),
    calibration_npy: Path | None = typer.Option(
        None,
        "--calibration-npy",
        help="Path to .npy array used as a single calibration batch (N,C,H,W)",
    ),
    per_channel: bool = typer.Option(False, "--per-channel"),
) -> None:
    if calibration_npy is None or not calibration_npy.is_file():
        raise PerceptShiftError(
            code=ErrorCode.QUANTIZATION_FAILED,
            message="--calibration-npy is required and must point to a real array",
            remediation="Provide calibration tensors derived from the calibration dataset",
        )
    array = np.load(str(calibration_npy))
    if array.ndim != 4:
        raise PerceptShiftError(
            code=ErrorCode.QUANTIZATION_FAILED,
            message="Calibration array must have shape (N,C,H,W)",
        )
    samples = [{input_name: array[i : i + 1].astype(np.float32)} for i in range(array.shape[0])]
    result = quantize_static_qdq(
        path,
        output_path,
        method=CalibrationMethod(method),
        calibration_samples=samples,
        input_name=input_name,
        per_channel=per_channel,
    )
    output.emit(ctx, result.report)


@app.command("compare")
def compare_cmd(
    ctx: typer.Context,
    left: Path = typer.Argument(..., exists=True, dir_okay=False),
    right: Path = typer.Argument(..., exists=True, dir_okay=False),
) -> None:
    a = inspect_onnx_model(left)
    b = inspect_onnx_model(right)
    payload = {
        "left_sha256": a.sha256,
        "right_sha256": b.sha256,
        "identical_hash": a.sha256 == b.sha256,
        "left_nodes": a.report["node_count"],
        "right_nodes": b.report["node_count"],
    }
    output.emit(ctx, payload)
