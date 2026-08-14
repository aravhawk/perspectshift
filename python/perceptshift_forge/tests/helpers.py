"""Runtime fixture helpers for forge tests (no committed binaries)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image


def canonical_preprocess(
    *,
    width: int = 8,
    height: int = 8,
    mean: list[float] | None = None,
    std: list[float] | None = None,
    scale: float = 1.0 / 255.0,
    backend: str = "scalar",
) -> dict[str, object]:
    return {
        "input_width": width,
        "input_height": height,
        "input_layout": "nchw",
        "accepted_source_formats": ["rgb8", "bgr8", "rgba8", "bgra8", "mono8"],
        "source_color_handling": "convert_to_rgb",
        "resize_mode": "stretch",
        "resize_interpolation": "bilinear",
        "scale": scale,
        "mean": mean if mean is not None else [0.0, 0.0, 0.0],
        "std": std if std is not None else [1.0, 1.0, 1.0],
        "swap_rb": False,
        "letterbox_pad_value": None,
        "output_dtype": "float32",
        "backend": backend,
    }


def make_tiny_onnx(path: Path, shape: tuple[int, ...] = (1, 3, 4, 4)) -> Path:
    """Generate a tiny ONNX identity graph at runtime (never committed)."""
    pytest.importorskip("onnx")
    import onnx
    from onnx import TensorProto, helper

    dims = [int(d) for d in shape]
    x = helper.make_tensor_value_info("input", TensorProto.FLOAT, dims)
    y = helper.make_tensor_value_info("output", TensorProto.FLOAT, dims)
    node = helper.make_node("Identity", ["input"], ["output"])
    graph = helper.make_graph([node], "tiny", [x], [y])
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
    model.ir_version = 8
    onnx.checker.check_model(model)
    path.parent.mkdir(parents=True, exist_ok=True)
    onnx.save(model, str(path))
    return path


def make_classifier_onnx(path: Path, *, classes: int = 2, height: int = 8, width: int = 8) -> Path:
    """Deterministic classifier: GlobalAveragePool + tiny Gemm-like MatMul via ReduceMean + Add.

    Output shape [1, classes] with fixed bias favoring class 0 for dark images.
    """
    pytest.importorskip("onnx")
    import onnx
    from onnx import TensorProto, helper, numpy_helper

    # Identity-like path: flatten mean of channels → logits via fixed weights.
    x = helper.make_tensor_value_info("input", TensorProto.FLOAT, [1, 3, height, width])
    y = helper.make_tensor_value_info("output", TensorProto.FLOAT, [1, classes])
    # Reduce mean over H,W → [1,3,1,1] then reshape to [1,3]
    reduce = helper.make_node(
        "ReduceMean",
        ["input"],
        ["pooled"],
        axes=[2, 3],
        keepdims=0,
    )
    # weights [3, classes]
    w = np.zeros((3, classes), dtype=np.float32)
    w[0, 0] = 1.0
    w[1, 1 % classes] = 1.0
    w_init = numpy_helper.from_array(w, name="W")
    b = np.zeros((classes,), dtype=np.float32)
    b[0] = 0.5
    b_init = numpy_helper.from_array(b, name="B")
    matmul = helper.make_node("MatMul", ["pooled", "W"], ["logits"])
    bias = helper.make_node("Add", ["logits", "B"], ["output"])
    graph = helper.make_graph(
        [reduce, matmul, bias],
        "tiny_cls",
        [x],
        [y],
        initializer=[w_init, b_init],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
    model.ir_version = 8
    onnx.checker.check_model(model)
    path.parent.mkdir(parents=True, exist_ok=True)
    onnx.save(model, str(path))
    return path


def make_yolo_like_onnx(path: Path, *, height: int = 32, width: int = 32, classes: int = 1) -> Path:
    """YOLO-v8-like single-output [1, 4+classes, N] with one deterministic detection."""
    pytest.importorskip("onnx")
    import onnx
    from onnx import TensorProto, helper, numpy_helper

    n_anchors = 4
    channels = 4 + classes
    x = helper.make_tensor_value_info("input", TensorProto.FLOAT, [1, 3, height, width])
    y = helper.make_tensor_value_info("output", TensorProto.FLOAT, [1, channels, n_anchors])
    const = np.zeros((1, channels, n_anchors), dtype=np.float32)
    const[0, 0, 0] = float(width) / 2.0
    const[0, 1, 0] = float(height) / 2.0
    const[0, 2, 0] = float(width) / 4.0
    const[0, 3, 0] = float(height) / 4.0
    const[0, 4, 0] = 0.9
    det = numpy_helper.from_array(const, name="DET")
    zero = numpy_helper.from_array(np.array([0.0], dtype=np.float32), name="ZERO")
    one = numpy_helper.from_array(np.array(1.0, dtype=np.float32), name="ONE")
    # Consume input: scale = 1 + sum(input)*0 → multiply DET
    reduce = helper.make_node("ReduceMean", ["input"], ["rm"], keepdims=1)
    reduce2 = helper.make_node("ReduceMean", ["rm"], ["rm2"], keepdims=0)
    mul = helper.make_node("Mul", ["rm2", "ZERO"], ["z"])
    reduce3 = helper.make_node("ReduceSum", ["z"], ["zs"], keepdims=0)
    add_s = helper.make_node("Add", ["ONE", "zs"], ["scale"])
    mul_out = helper.make_node("Mul", ["DET", "scale"], ["output"])
    graph = helper.make_graph(
        [reduce, reduce2, mul, reduce3, add_s, mul_out],
        "tiny_yolo",
        [x],
        [y],
        initializer=[det, zero, one],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
    model.ir_version = 8
    onnx.checker.check_model(model)
    path.parent.mkdir(parents=True, exist_ok=True)
    onnx.save(model, str(path))
    return path


def write_rgb_image(
    path: Path,
    color: tuple[int, int, int] = (10, 20, 30),
    size: tuple[int, int] = (8, 8),
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.full((size[1], size[0], 3), color, dtype=np.uint8), mode="RGB").save(path)


def classification_manifest(root: Path, items: list[dict[str, object]]) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "document_type": "perceptshift.dataset_manifest",
        "dataset_type": "image_classification_manifest",
        "dataset_name": "tiny-cls",
        "root": str(root.resolve()),
        "license_reference": "test-only",
        "split_name": "calibration",
        "preprocess_contract": canonical_preprocess(width=8, height=8),
        "items": items,
        "notes": "test_fixture=true; claim_scope=software_correctness_only",
    }


def coco_detection_manifest(
    root: Path,
    *,
    annotation_path: str,
    width: int = 32,
    height: int = 32,
) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "document_type": "perceptshift.dataset_manifest",
        "dataset_type": "coco_detection",
        "dataset_name": "tiny-coco",
        "root": str(root.resolve()),
        "license_reference": "test-only",
        "split_name": "calibration",
        "annotation_path": annotation_path,
        "crowd_treatment": "exclude",
        "preprocess_contract": canonical_preprocess(width=width, height=height),
        "notes": "test_fixture=true; claim_scope=software_correctness_only",
    }


def raw_tensor_manifest(root: Path, items: list[dict[str, object]]) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "document_type": "perceptshift.dataset_manifest",
        "dataset_type": "raw_tensor",
        "dataset_name": "tiny-raw",
        "root": str(root.resolve()),
        "license_reference": "test-only",
        "split_name": "calibration",
        "preprocess_contract": canonical_preprocess(width=4, height=4),
        "items": items,
        "test_fixture": True,
        "claim_scope": "software_correctness_only",
    }


def write_float_tensor(path: Path, shape: tuple[int, ...] = (1, 3, 4, 4)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.save(str(path), np.zeros(shape, dtype=np.float32))
    return path


def write_ed25519_private_key(path: Path) -> Path:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    key = Ed25519PrivateKey.generate()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(key.private_bytes_raw())
    path.chmod(0o600)
    return path


def write_json(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path
