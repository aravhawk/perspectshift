"""ONNX model inspection."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from perceptshift_common.errors import ErrorCode, PerceptShiftError
from perceptshift_common.hashing import sha256_file
from perceptshift_common.producer import envelope_fields
from perceptshift_common.reason_codes import ReasonCode


@dataclass(slots=True)
class ModelInspection:
    path: Path
    sha256: str
    report: dict[str, Any]


def inspect_onnx_model(path: Path) -> ModelInspection:
    if not path.is_file():
        raise PerceptShiftError(
            code=ErrorCode.MODEL_INVALID,
            message=f"Model file not found: {path}",
        )
    try:
        import onnx
        from onnx import checker, numpy_helper, shape_inference
    except ImportError as exc:
        raise PerceptShiftError(
            code=ErrorCode.DEPENDENCY_UNAVAILABLE,
            message="onnx package is required for model inspection",
            remediation="Install onnx via the workspace dependencies",
            details={"reason_code": ReasonCode.UNAVAILABLE_DEPENDENCY},
            cause=exc,
        ) from exc

    try:
        model = onnx.load(str(path))
        checker.check_model(model)
        inferred = shape_inference.infer_shapes(model)
    except Exception as exc:
        raise PerceptShiftError(
            code=ErrorCode.MODEL_INVALID,
            message=f"ONNX model validation failed: {exc}",
            remediation="Fix the model with onnx.checker / shape inference errors",
            cause=exc,
        ) from exc

    graph = inferred.graph
    inputs = [
        _tensor_info(value) for value in graph.input if value.name not in _initializer_names(graph)
    ]
    outputs = [_tensor_info(value) for value in graph.output]
    initializers = [
        {
            "name": init.name,
            "dims": list(init.dims),
            "data_type": int(init.data_type),
            "raw_byte_size": len(numpy_helper.to_array(init).tobytes()),
        }
        for init in graph.initializer
    ]

    report = envelope_fields(document_type="perceptshift.model_inspection")
    report.update(
        {
            "path": str(path.resolve()),
            "sha256": sha256_file(path),
            "ir_version": int(model.ir_version),
            "opset_imports": [
                {"domain": op.domain or "", "version": int(op.version)} for op in model.opset_import
            ],
            "producer_name": model.producer_name or None,
            "producer_version": model.producer_version or None,
            "inputs": inputs,
            "outputs": outputs,
            "initializer_count": len(initializers),
            "node_count": len(graph.node),
            "node_ops": sorted({node.op_type for node in graph.node}),
        }
    )
    return ModelInspection(path=path, sha256=report["sha256"], report=report)


def _initializer_names(graph: Any) -> set[str]:
    return {init.name for init in graph.initializer}


def _tensor_info(value_info: Any) -> dict[str, Any]:
    tensor_type = value_info.type.tensor_type
    shape: list[int | str | None] = []
    for dim in tensor_type.shape.dim:
        if dim.HasField("dim_value"):
            shape.append(int(dim.dim_value))
        elif dim.HasField("dim_param"):
            shape.append(str(dim.dim_param))
        else:
            shape.append(None)
    return {
        "name": value_info.name,
        "elem_type": int(tensor_type.elem_type),
        "shape": shape,
    }
