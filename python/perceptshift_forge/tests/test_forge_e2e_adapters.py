"""Forge adapter E2E tests with runtime-generated fixtures only."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import yaml
from helpers import (
    canonical_preprocess,
    classification_manifest,
    coco_detection_manifest,
    make_classifier_onnx,
    make_tiny_onnx,
    make_yolo_like_onnx,
    raw_tensor_manifest,
    write_float_tensor,
    write_json,
    write_rgb_image,
)

from perceptshift_common.errors import ErrorCode, PerceptShiftError
from perceptshift_forge.datasets.stream import materialize_raw_image
from perceptshift_forge.orchestration import run_forge
from perceptshift_forge.preprocess import build_canonical_preprocess


def _forge_config(
    tmp_path: Path,
    *,
    model_path: Path,
    cal: Path,
    ev: Path,
    adapter: str,
    expected_input: dict,
    preprocess: dict,
    quality_metric: str,
    adapter_config: dict | None = None,
) -> Path:
    cfg = {
        "schema_version": "1.0",
        "document_type": "perceptshift.forge_config",
        "project": {
            "name": f"e2e-{adapter}",
            "output_root": str((tmp_path / "out").resolve()),
            "random_seed": 7,
        },
        "model": {
            "baseline_path": str(model_path.resolve()),
            "adapter": adapter,
            "adapter_config": adapter_config or {},
            "expected_input": expected_input,
            "preprocess": preprocess,
            "allowed_model_roots": [str(tmp_path.resolve())],
        },
        "datasets": {
            "calibration_manifest": str(cal.resolve()),
            "evaluation_manifest": str(ev.resolve()),
            "prohibit_cross_split_duplicates": True,
        },
        "quantization": {
            "enabled": False,
            "methods": ["minmax"],
            "format": "qdq",
            "activation_type": "qint8",
            "weight_type": "qint8",
            "per_channel_options": [False],
            "nodes_to_exclude": [],
            "calibration_sample_limit": None,
        },
        "candidates": {
            "include_baseline": True,
            "user_model_variants": [],
            "execution_providers": [{"name": "cpu", "provider_order": ["CPUExecutionProvider"]}],
            "xnnpack_thread_counts": [1],
            "ort_intra_op_thread_counts": [1],
            "ort_inter_op_thread_counts": [1],
            "allow_intra_op_spinning": [False],
            "graph_optimization_levels": ["all"],
            "preprocess_backends": ["scalar"],
            "input_variants": [],
        },
        "benchmark": {
            "warmup_iterations": 1,
            "measured_iterations": 1,
            "independent_trials": 1,
            "randomize_candidate_order": False,
            "cold_start_trials": 0,
            "per_candidate_timeout_seconds": 60,
            "maximum_worker_rss_mb": 1024,
            "minimum_stabilization_seconds": 0,
            "maximum_start_temperature_c": None,
            "maximum_temperature_drift_c": None,
            "require_no_throttling": False,
            "collect_perf": False,
            "collect_ros_trace": False,
            "bootstrap_resamples": 100,
        },
        "quality": {
            "metric_name": quality_metric,
            "direction": "higher_is_better",
            "minimum_absolute_value": 0.0,
            "maximum_degradation_from_baseline": 1.0,
            "confidence_level": 0.95,
        },
        "certification": {
            "deadline_ms": 5000.0,
            "maximum_peak_rss_mb": 4096,
            "maximum_model_size_mb": 1024,
            "require_xnnpack_assignment": False,
            "maximum_cpu_fallback_fraction": None,
            "require_valid_environment": False,
            "require_output_equivalence": False,
            "sign_bundle": False,
            "signing_key_path": None,
        },
        "report": {
            "formats": ["json"],
            "include_raw_sample_links": False,
            "include_environment": True,
        },
    }
    path = tmp_path / "forge.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


def test_materialize_raw_rejects_encoded_as_pixels(tmp_path: Path) -> None:
    png = tmp_path / "a.png"
    write_rgb_image(png, (1, 2, 3), size=(8, 8))
    raw_out = tmp_path / "a.rgb"
    meta = materialize_raw_image(png, raw_out)
    assert meta["byte_size"] == 8 * 8 * 3
    assert raw_out.stat().st_size == meta["byte_size"]
    assert png.read_bytes() != raw_out.read_bytes()
    assert len(png.read_bytes()) != meta["byte_size"]


def test_canonical_preprocess_requires_semantics_for_images() -> None:
    with pytest.raises(PerceptShiftError) as exc:
        build_canonical_preprocess(
            forge_config={"model": {"adapter": "image_classification"}},
        )
    assert exc.value.code == ErrorCode.CONFIG_INVALID


def test_forge_raw_tensor_e2e(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg-data"))
    model = make_tiny_onnx(tmp_path / "model.onnx", shape=(1, 3, 4, 4))
    cal_root = tmp_path / "cal"
    ev_root = tmp_path / "ev"
    write_float_tensor(cal_root / "a.npy", (1, 3, 4, 4))

    ev_root.mkdir(parents=True, exist_ok=True)
    np.save(str(ev_root / "b.npy"), np.ones((1, 3, 4, 4), dtype=np.float32))
    cal = write_json(
        tmp_path / "cal.json",
        raw_tensor_manifest(cal_root, [{"path": "a.npy", "item_id": "a", "label": 0}]),
    )
    ev_doc = raw_tensor_manifest(ev_root, [{"path": "b.npy", "item_id": "b", "label": 1}])
    ev_doc["split_name"] = "evaluation"
    ev = write_json(tmp_path / "ev.json", ev_doc)
    preprocess = canonical_preprocess(width=4, height=4)
    config = _forge_config(
        tmp_path,
        model_path=model,
        cal=cal,
        ev=ev,
        adapter="raw_tensor",
        expected_input={"shape": [1, 3, 4, 4], "layout": "nchw"},
        preprocess=preprocess,
        quality_metric="numeric_equivalence",
    )
    result = run_forge(config, maximum_candidates=8)
    assert result["status"] == "completed"
    root = Path(result["root"])
    stream = json.loads((root / "inputs" / "bench-stream.json").read_text(encoding="utf-8"))
    assert stream["samples"][0]["input_kind"] == "raw_tensor"
    assert (root / "bundle" / "profile-bundle" / "manifest.json").is_file()


def test_forge_classification_e2e(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg-data"))
    model = make_classifier_onnx(tmp_path / "cls.onnx", classes=2, height=8, width=8)
    cal_root = tmp_path / "cal"
    ev_root = tmp_path / "ev"
    write_rgb_image(cal_root / "a.png", (10, 20, 30), size=(8, 8))
    write_rgb_image(ev_root / "b.png", (40, 50, 60), size=(16, 16))  # different content/size
    cal = write_json(
        tmp_path / "cal.json",
        classification_manifest(cal_root, [{"path": "a.png", "class_id": 0, "item_id": "a"}]),
    )
    ev_doc = classification_manifest(ev_root, [{"path": "b.png", "class_id": 0, "item_id": "b"}])
    ev_doc["split_name"] = "evaluation"
    ev = write_json(tmp_path / "ev.json", ev_doc)
    preprocess = canonical_preprocess(width=8, height=8)
    config = _forge_config(
        tmp_path,
        model_path=model,
        cal=cal,
        ev=ev,
        adapter="image_classification",
        expected_input={"shape": [1, 3, 8, 8], "layout": "nchw"},
        preprocess=preprocess,
        quality_metric="classification_accuracy",
    )
    result = run_forge(config, maximum_candidates=8)
    assert result["status"] == "completed"
    root = Path(result["root"])
    stream = json.loads((root / "inputs" / "bench-stream.json").read_text(encoding="utf-8"))
    sample = stream["samples"][0]
    assert sample["input_kind"] == "raw_image"
    assert sample["image_path"].endswith(".rgb")
    assert sample["byte_size"] == sample["stride_bytes"] * sample["height"]
    # Encoded provenance exists separately; raw file is not PNG.
    raw_path = root / "inputs" / sample["image_path"]
    assert raw_path.is_file()
    assert raw_path.read_bytes()[:4] != b"\x89PNG"
    native = list((root / "evaluation").glob("*.native_outputs.json"))
    assert native, "bench worker must emit native_outputs for quality"


def test_forge_yolo_e2e(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg-data"))
    model = make_yolo_like_onnx(tmp_path / "yolo.onnx", height=32, width=32, classes=1)
    cal_root = tmp_path / "cal"
    ev_root = tmp_path / "ev"
    write_rgb_image(cal_root / "img.png", (5, 6, 7), size=(32, 32))
    write_rgb_image(ev_root / "img.png", (15, 16, 17), size=(32, 32))
    ann_cal = {
        "images": [{"id": 1, "file_name": "img.png", "width": 32, "height": 32}],
        "annotations": [
            {
                "id": 1,
                "image_id": 1,
                "category_id": 0,
                "bbox": [8, 8, 8, 8],
                "area": 64,
                "iscrowd": 0,
            }
        ],
        "categories": [{"id": 0, "name": "obj"}],
    }
    ann_ev = {
        "images": [{"id": 2, "file_name": "img.png", "width": 32, "height": 32}],
        "annotations": [
            {
                "id": 2,
                "image_id": 2,
                "category_id": 0,
                "bbox": [10, 10, 6, 6],
                "area": 36,
                "iscrowd": 0,
            }
        ],
        "categories": [{"id": 0, "name": "obj"}],
    }
    write_json(cal_root / "ann.json", ann_cal)
    write_json(ev_root / "ann.json", ann_ev)
    cal = write_json(
        tmp_path / "cal.json",
        coco_detection_manifest(cal_root, annotation_path="ann.json", width=32, height=32),
    )
    ev_doc = coco_detection_manifest(ev_root, annotation_path="ann.json", width=32, height=32)
    ev_doc["split_name"] = "evaluation"
    ev = write_json(tmp_path / "ev.json", ev_doc)
    preprocess = canonical_preprocess(width=32, height=32)
    config = _forge_config(
        tmp_path,
        model_path=model,
        cal=cal,
        ev=ev,
        adapter="yolo_v8_detection",
        expected_input={"shape": [1, 3, 32, 32], "layout": "nchw"},
        preprocess=preprocess,
        quality_metric="coco_map_50_95",
        adapter_config={"num_classes": 1, "confidence_threshold": 0.25},
    )
    result = run_forge(config, maximum_candidates=8)
    assert result["status"] == "completed"
    root = Path(result["root"])
    stream = json.loads((root / "inputs" / "bench-stream.json").read_text(encoding="utf-8"))
    assert stream["samples"][0]["input_kind"] == "raw_image"
    dets = list((root / "evaluation").glob("*.detections.json"))
    assert dets, "YOLO bench must emit detections.json"
