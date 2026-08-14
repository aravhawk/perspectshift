"""Runtime-generated certified profile bundles for ROS/API E2E (never committed)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _canonical_preprocess(*, width: int = 8, height: int = 8) -> dict[str, object]:
    return {
        "input_width": width,
        "input_height": height,
        "input_layout": "nchw",
        "accepted_source_formats": ["rgb8", "bgr8", "rgba8", "bgra8", "mono8"],
        "source_color_handling": "convert_to_rgb",
        "resize_mode": "stretch",
        "resize_interpolation": "bilinear",
        "scale": 1.0 / 255.0,
        "mean": [0.0, 0.0, 0.0],
        "std": [1.0, 1.0, 1.0],
        "swap_rb": False,
        "letterbox_pad_value": None,
        "output_dtype": "float32",
        "backend": "scalar",
    }


def _make_classifier_onnx(path: Path, *, classes: int = 2, height: int = 8, width: int = 8) -> Path:
    import onnx
    from onnx import TensorProto, helper, numpy_helper

    x = helper.make_tensor_value_info("input", TensorProto.FLOAT, [1, 3, height, width])
    y = helper.make_tensor_value_info("output", TensorProto.FLOAT, [1, classes])
    reduce = helper.make_node("ReduceMean", ["input"], ["pooled"], axes=[2, 3], keepdims=0)
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


def write_classification_bundle(root: Path, *, width: int = 8, height: int = 8) -> Path:
    """Write a loadable profile-bundle with a tiny classifier ONNX."""
    root = root.resolve()
    (root / "models").mkdir(parents=True, exist_ok=True)
    (root / "profiles").mkdir(parents=True, exist_ok=True)

    model = _make_classifier_onnx(
        root / "models" / "cls.onnx", classes=2, height=height, width=width
    )
    model_sha = _sha256_file(model)
    preprocess = _canonical_preprocess(width=width, height=height)

    profile = {
        "profile_id": "baseline_cpu",
        "label": "baseline_cpu",
        "model_sha256": model_sha,
        "model_relative_path": "models/cls.onnx",
        "model_size_bytes": model.stat().st_size,
        "status": "certified",
        "session": {
            "provider_order": ["CPUExecutionProvider"],
            "intra_op_threads": 1,
            "inter_op_threads": 1,
            "graph_optimization_level": "all",
            "execution_mode": "sequential",
            "xnnpack_threads": None,
            "allow_spinning": False,
        },
        "adapter": {
            "name": "image_classification",
            "config": {"class_labels": ["a", "b"], "apply_softmax": True},
        },
        "preprocess": preprocess,
        "certified_p99_ms": 40.0,
        "certified_quality": 1.0,
        "offline_envelope_ms": 40.0,
        "quality_metric_name": "top1_accuracy",
        "quality_value": 1.0,
    }
    profile_path = root / "profiles" / "baseline_cpu.json"
    profile_path.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
    profile_sha = _sha256_file(profile_path)

    files = [
        {
            "path": "models/cls.onnx",
            "sha256": model_sha,
            "size_bytes": model.stat().st_size,
        },
        {
            "path": "profiles/baseline_cpu.json",
            "sha256": profile_sha,
            "size_bytes": profile_path.stat().st_size,
        },
    ]
    manifest = {
        "schema_version": "1.0",
        "document_type": "perceptshift.profile_bundle",
        "bundle_id": "e2e-classification-bundle",
        "product_version": "0.1.0",
        "minimum_compatible_runtime_version": "0.1.0",
        "created_at": "2026-01-01T00:00:00Z",
        "producer": {"name": "perceptshift-e2e", "version": "0.1.0"},
        "adapter": {"name": "image_classification"},
        "quality_metric_name": "top1_accuracy",
        "quality_direction": "higher_is_better",
        "profiles": [profile],
        "files": files,
    }
    man_path = root / "manifest.json"
    man_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (root / "manifest.sha256").write_text(_sha256_file(man_path) + "\n", encoding="utf-8")
    return root
