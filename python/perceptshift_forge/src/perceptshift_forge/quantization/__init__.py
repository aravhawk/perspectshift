"""Static QDQ INT8 quantization via ONNX Runtime when available."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

import numpy as np

from perceptshift_common.errors import ErrorCode, PerceptShiftError
from perceptshift_common.hashing import sha256_file
from perceptshift_common.producer import envelope_fields
from perceptshift_common.reason_codes import ReasonCode


class CalibrationMethod(StrEnum):
    MINMAX = "minmax"
    ENTROPY = "entropy"
    PERCENTILE = "percentile"


@dataclass(slots=True)
class QuantizationResult:
    output_path: Path
    method: CalibrationMethod
    per_channel: bool
    model_sha256: str
    calibration_sample_count: int
    options: dict[str, Any]
    report: dict[str, Any]


def _require_quantization_apis() -> Any:
    try:
        from onnxruntime.quantization import (  # type: ignore[import-untyped]
            CalibrationMethod as OrtCalibrationMethod,
        )
        from onnxruntime.quantization import (
            QuantFormat,
            QuantType,
            quantize_static,
        )
    except ImportError as exc:
        raise PerceptShiftError(
            code=ErrorCode.QUANTIZATION_UNAVAILABLE,
            message="ONNX Runtime quantization APIs are unavailable",
            remediation="Install onnxruntime==1.28.0 with quantization support",
            details={"reason_code": ReasonCode.UNAVAILABLE_QUANTIZATION_API},
            cause=exc,
        ) from exc
    return OrtCalibrationMethod, QuantFormat, QuantType, quantize_static


def _map_method(method: CalibrationMethod, ort_method_cls: Any) -> Any:
    mapping = {
        CalibrationMethod.MINMAX: ort_method_cls.MinMax,
        CalibrationMethod.ENTROPY: ort_method_cls.Entropy,
        CalibrationMethod.PERCENTILE: ort_method_cls.Percentile,
    }
    if method not in mapping:
        raise PerceptShiftError(
            code=ErrorCode.QUANTIZATION_FAILED,
            message=f"Unsupported calibration method: {method}",
        )
    return mapping[method]


class _NumpyDataReader:
    """Minimal calibration data reader compatible with ORT quantization APIs."""

    def __init__(
        self,
        samples: Sequence[dict[str, np.ndarray]],
        input_name: str,
    ) -> None:
        self._samples = list(samples)
        self._input_name = input_name
        self._index = 0

    def get_next(self) -> dict[str, np.ndarray] | None:
        if self._index >= len(self._samples):
            return None
        sample = self._samples[self._index]
        self._index += 1
        if self._input_name in sample:
            return sample
        if len(sample) == 1:
            only = next(iter(sample.values()))
            return {self._input_name: only}
        raise PerceptShiftError(
            code=ErrorCode.QUANTIZATION_FAILED,
            message=f"Calibration sample missing input '{self._input_name}'",
        )

    def rewind(self) -> None:
        self._index = 0


def quantize_static_qdq(
    model_path: Path,
    output_path: Path,
    *,
    method: CalibrationMethod,
    calibration_samples: Sequence[dict[str, np.ndarray]],
    input_name: str,
    per_channel: bool = False,
    nodes_to_exclude: Iterable[str] | None = None,
    extra_options: dict[str, Any] | None = None,
) -> QuantizationResult:
    if not calibration_samples:
        raise PerceptShiftError(
            code=ErrorCode.QUANTIZATION_FAILED,
            message="Static quantization requires at least one calibration sample",
            remediation="Provide real calibration tensors from the calibration dataset",
        )
    if not model_path.is_file():
        raise PerceptShiftError(
            code=ErrorCode.MODEL_INVALID,
            message=f"Baseline model not found: {model_path}",
        )

    OrtCalibrationMethod, QuantFormat, QuantType, quantize_static = _require_quantization_apis()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    reader = _NumpyDataReader(calibration_samples, input_name)
    options = {
        "quant_format": "QDQ",
        "activation_type": "QInt8",
        "weight_type": "QInt8",
        "per_channel": per_channel,
        "calibrate_method": str(method),
        "nodes_to_exclude": list(nodes_to_exclude or []),
        "extra_options": dict(extra_options or {}),
    }

    try:
        quantize_static(
            model_input=str(model_path),
            model_output=str(output_path),
            calibration_data_reader=reader,
            quant_format=QuantFormat.QDQ,
            activation_type=QuantType.QInt8,
            weight_type=QuantType.QInt8,
            per_channel=per_channel,
            calibrate_method=_map_method(method, OrtCalibrationMethod),
            nodes_to_exclude=list(nodes_to_exclude or []),
            extra_options=dict(extra_options or {}),
        )
    except PerceptShiftError:
        raise
    except Exception as exc:
        raise PerceptShiftError(
            code=ErrorCode.QUANTIZATION_FAILED,
            message=f"Static quantization failed: {exc}",
            remediation="Inspect model ops, calibration tensors, and ORT quantization logs",
            cause=exc,
            details=options,
        ) from exc

    if not output_path.is_file():
        raise PerceptShiftError(
            code=ErrorCode.QUANTIZATION_FAILED,
            message="Quantization completed without writing an output model",
            details=options,
        )

    try:
        import onnx
        from onnx import checker

        checker.check_model(onnx.load(str(output_path)))
    except ImportError:
        pass
    except Exception as exc:
        raise PerceptShiftError(
            code=ErrorCode.QUANTIZATION_FAILED,
            message=f"Quantized model failed ONNX checker: {exc}",
            cause=exc,
        ) from exc

    digest = sha256_file(output_path)
    report = envelope_fields(document_type="perceptshift.quantization_result")
    report.update(
        {
            "baseline_path": str(model_path),
            "output_path": str(output_path),
            "model_sha256": digest,
            "calibration_sample_count": len(calibration_samples),
            "options": options,
        }
    )
    return QuantizationResult(
        output_path=output_path,
        method=method,
        per_channel=per_channel,
        model_sha256=digest,
        calibration_sample_count=len(calibration_samples),
        options=options,
        report=report,
    )


def make_random_is_forbidden() -> Callable[[], None]:
    """Guardrail: random calibration tensors are never used."""

    def _raise() -> None:
        raise PerceptShiftError(
            code=ErrorCode.QUANTIZATION_FAILED,
            message="Random calibration tensors are forbidden",
            remediation="Use real calibration samples through the configured preprocess contract",
        )

    return _raise
