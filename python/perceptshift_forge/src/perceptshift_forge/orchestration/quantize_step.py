"""Quantization step helpers for Forge orchestration."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import numpy as np

from perceptshift_common.errors import ErrorCode, PerceptShiftError
from perceptshift_common.hashing import sha256_canonical, sha256_file, write_atomic_json
from perceptshift_forge.quantization import CalibrationMethod, quantize_static_qdq


def run_quantization_variants(
    *,
    workspace_root: Path,
    config: dict[str, Any],
    baseline_model_path: Path,
    calibration_manifest_path: Path,
    stream_path: Path,
    model_inspection: dict[str, Any],
) -> list[dict[str, Any]]:
    quant_cfg = config.get("quantization") or {}
    if not quant_cfg.get("enabled"):
        return []

    methods = [CalibrationMethod(m) for m in (quant_cfg.get("methods") or ["minmax"])]
    per_channel_options = list(quant_cfg.get("per_channel_options") or [False])
    sample_limit = quant_cfg.get("calibration_sample_limit")
    input_name = "input"
    inputs = model_inspection.get("inputs") or []
    if inputs and isinstance(inputs[0], dict) and inputs[0].get("name"):
        input_name = str(inputs[0]["name"])

    cal_tensors, cal_meta = _load_calibration_tensors_native(
        config=config,
        workspace_root=workspace_root,
        stream_path=stream_path,
        input_name=input_name,
        sample_limit=int(sample_limit) if sample_limit is not None else None,
    )

    quantized: list[dict[str, Any]] = []
    out_root = workspace_root / "models" / "quantized"
    out_root.mkdir(parents=True, exist_ok=True)
    for method in methods:
        for per_channel in per_channel_options:
            label = f"{method.value}_pc{int(bool(per_channel))}"
            out_path = out_root / f"{label}.onnx"
            result = quantize_static_qdq(
                baseline_model_path,
                out_path,
                method=method,
                per_channel=bool(per_channel),
                calibration_samples=cal_tensors,
                input_name=input_name,
            )
            report = {
                "label": label,
                "output_path": str(out_path),
                "model_sha256": result.model_sha256,
                "method": method.value,
                "per_channel": bool(per_channel),
                "calibration_sample_count": result.calibration_sample_count,
                "calibration_meta": cal_meta,
                "calibration_manifest": str(calibration_manifest_path),
            }
            write_atomic_json(out_root / f"{label}.report.json", report)
            quantized.append(
                {
                    "label": label,
                    "model_path": f"models/quantized/{out_path.name}",
                    "model_sha256": result.model_sha256,
                    "lineage": {
                        "transformation": "static_qdq",
                        "label": label,
                        "calibration_meta": cal_meta,
                    },
                }
            )
    return quantized


def _load_calibration_tensors_native(
    *,
    config: dict[str, Any],
    workspace_root: Path,
    stream_path: Path,
    input_name: str,
    sample_limit: int | None,
) -> tuple[list[dict[str, np.ndarray]], dict[str, Any]]:
    """Materialize calibration tensors via the native production preprocessor."""
    adapter = str((config.get("model") or {}).get("adapter") or "")
    stream = json.loads(stream_path.read_text(encoding="utf-8"))
    samples = [
        s for s in (stream.get("samples") or []) if isinstance(s, dict) and s.get("role") == "calib"
    ]
    if sample_limit is not None:
        samples = samples[:sample_limit]
    if not samples:
        raise PerceptShiftError(
            code=ErrorCode.QUANTIZATION_FAILED,
            message="No calibration samples in benchmark stream",
            remediation="Ensure calibration dataset materializes into the benchmark stream",
        )

    preprocess_contract = (
        (config.get("model") or {}).get("preprocess")
        or (config.get("datasets") or {}).get("preprocess_contract")
        or {}
    )
    # Prefer contract embedded in stream document when present.
    if isinstance(stream.get("preprocess_contract"), dict):
        preprocess_contract = stream["preprocess_contract"]
    if not preprocess_contract and adapter == "raw_tensor":
        # Raw tensor calibration uses already-materialized float tensors.
        tensors: list[dict[str, np.ndarray]] = []
        for sample in samples:
            rel = sample.get("tensor_path")
            if not isinstance(rel, str):
                continue
            path = workspace_root / rel if not Path(rel).is_absolute() else Path(rel)
            if not path.is_file():
                alt = stream_path.parent / rel
                path = alt if alt.is_file() else path
            array = np.fromfile(str(path), dtype=np.float32)
            shape = sample.get("shape")
            if isinstance(shape, list) and shape:
                array = array.reshape([int(x) for x in shape])
            tensors.append({input_name: np.asarray(array, dtype=np.float32)})
        meta = {
            "path": "raw_tensor_stream",
            "preprocess_contract_hash": sha256_canonical(preprocess_contract or {}),
            "sample_count": len(tensors),
        }
        return tensors, meta

    worker = None
    # Late import avoids circular dependency with orchestration.__init__.
    from perceptshift_forge.orchestration import find_native_binary

    worker = find_native_binary("perceptshift-preprocess-worker")
    if worker is None:
        raise PerceptShiftError(
            code=ErrorCode.QUANTIZATION_FAILED,
            message="perceptshift-preprocess-worker not found; required for production calibration",
            remediation="Build native targets including perceptshift-preprocess-worker",
        )

    contract_path = workspace_root / "inputs" / "calibration-preprocess-contract.json"
    write_atomic_json(contract_path, preprocess_contract)
    contract_hash = sha256_file(contract_path)
    out_dir = workspace_root / "models" / "calibration_tensors"
    out_dir.mkdir(parents=True, exist_ok=True)

    tensors = []
    for idx, sample in enumerate(samples):
        if sample.get("input_kind") == "raw_image":
            image_rel = sample.get("image_path")
            if not isinstance(image_rel, str):
                raise PerceptShiftError(
                    code=ErrorCode.QUANTIZATION_FAILED,
                    message=f"Calibration sample missing image_path: {sample.get('sample_id')}",
                )
            image_path = workspace_root / image_rel
            if not image_path.is_file():
                image_path = stream_path.parent / image_rel
            out_path = out_dir / f"calib_{idx}.f32"
            cmd = [
                str(worker),
                "--image",
                str(image_path),
                "--contract",
                str(contract_path),
                "--output",
                str(out_path),
                "--pixel-format",
                str(sample.get("pixel_format") or "rgb8"),
                "--width",
                str(int(sample["width"])),
                "--height",
                str(int(sample["height"])),
                "--stride-bytes",
                str(int(sample.get("stride_bytes") or 0)),
            ]
            proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
            if proc.returncode != 0:
                raise PerceptShiftError(
                    code=ErrorCode.QUANTIZATION_FAILED,
                    message="Native preprocess worker failed for calibration sample",
                    details={"stderr": proc.stderr, "stdout": proc.stdout, "argv": cmd},
                )
            array = np.fromfile(str(out_path), dtype=np.float32)
            # NCHW float tensor: 3 * H * W
            h = int(
                preprocess_contract.get("input_height") or preprocess_contract.get("height") or 0
            )
            w = int(preprocess_contract.get("input_width") or preprocess_contract.get("width") or 0)
            if h > 0 and w > 0 and array.size == 3 * h * w:
                array = array.reshape(1, 3, h, w)
            tensors.append({input_name: array})
        else:
            rel = sample.get("tensor_path")
            if not isinstance(rel, str):
                continue
            path = workspace_root / rel
            if not path.is_file():
                path = stream_path.parent / rel
            array = np.fromfile(str(path), dtype=np.float32)
            shape = sample.get("shape")
            if isinstance(shape, list) and shape:
                array = array.reshape([int(x) for x in shape])
            tensors.append({input_name: np.asarray(array, dtype=np.float32)})

    if not tensors:
        raise PerceptShiftError(
            code=ErrorCode.QUANTIZATION_FAILED,
            message="Unable to load calibration tensors for quantization",
        )
    meta = {
        "path": "native_preprocess_worker",
        "preprocess_contract_hash": contract_hash,
        "model_adapter": adapter,
        "sample_count": len(tensors),
        "worker": str(worker),
    }
    write_atomic_json(workspace_root / "models" / "calibration_meta.json", meta)
    return tensors, meta
