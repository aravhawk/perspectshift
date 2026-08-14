"""Forge package tests with runtime-generated fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import yaml
from helpers import (
    classification_manifest,
    make_tiny_onnx,
    write_json,
    write_rgb_image,
)

from perceptshift_common.errors import ErrorCode, PerceptShiftError
from perceptshift_common.hashing import sha256_file
from perceptshift_forge.certification import is_certified, pareto_select, run_certification_gates
from perceptshift_forge.datasets.validate import validate_dataset_manifest
from perceptshift_forge.evaluation import classification_accuracy
from perceptshift_forge.models.inspect import inspect_onnx_model
from perceptshift_forge.orchestration import launch_bench_worker, make_run_id, run_forge
from perceptshift_forge.quantization import CalibrationMethod, quantize_static_qdq
from perceptshift_forge.reporting import build_report_document, redact_path
from perceptshift_forge.statistics import summarize_latencies


def test_dataset_path_containment_and_hash(tmp_path: Path) -> None:
    root = tmp_path / "data"
    img = root / "a.png"
    write_rgb_image(img)
    man = classification_manifest(
        root,
        [{"path": "a.png", "class_id": 0, "item_id": "a"}],
    )
    path = write_json(tmp_path / "cal.json", man)
    result = validate_dataset_manifest(path)
    assert result.ok
    assert result.item_count == 1
    assert result.content_hashes[0] == sha256_file(img)


def test_dataset_rejects_escape(tmp_path: Path) -> None:
    root = tmp_path / "data"
    root.mkdir()
    outside = tmp_path / "outside.png"
    write_rgb_image(outside)
    man = classification_manifest(
        root,
        [{"path": "../outside.png", "class_id": 0}],
    )
    path = write_json(tmp_path / "cal.json", man)
    result = validate_dataset_manifest(path)
    assert not result.ok


def test_model_inspect_tiny_onnx(tmp_path: Path) -> None:
    model_path = make_tiny_onnx(tmp_path / "tiny.onnx")
    report = inspect_onnx_model(model_path)
    assert report.sha256 == sha256_file(model_path)
    assert report.report["node_count"] == 1


def test_statistics_known_values_and_bootstrap_seed() -> None:
    samples = [10, 20, 30, 40, 50]
    a = summarize_latencies(samples, bootstrap_resamples=200, seed=7)
    b = summarize_latencies(samples, bootstrap_resamples=200, seed=7)
    assert a.p50 == 30
    assert a.mean == 30
    assert a.bootstrap_ci is not None
    assert b.bootstrap_ci is not None
    assert a.bootstrap_ci["mean"] == b.bootstrap_ci["mean"]


def test_classification_accuracy_known() -> None:
    result = classification_accuracy(
        [0, 1, 1, 0],
        [0, 1, 0, 0],
        dataset_hash="abc",
        adapter_name="image_classification",
    )
    assert result.value == 0.75
    assert result.attestation["pass"] is True


def test_certification_gates_matrix() -> None:
    ctx = {
        "schema_valid": True,
        "integrity_ok": True,
        "model_valid": True,
        "host_compatible": True,
        "provider_ok": True,
        "tensor_contract_ok": True,
        "require_output_equivalence": True,
        "equivalence_ok": True,
        "quality_ok": True,
        "peak_rss_mb": 100,
        "maximum_peak_rss_mb": 200,
        "latency_ms": 10,
        "deadline_ms": 20,
        "require_valid_environment": True,
        "environment_status": "valid",
        "warmup_ok": True,
        "artifacts_complete": True,
    }
    results = run_certification_gates(ctx)
    assert len(results) == 13
    assert is_certified(results)
    ctx["quality_ok"] = False
    assert not is_certified(run_certification_gates(ctx))


def test_pareto_known_front() -> None:
    candidates = [
        {
            "candidate_id": "a",
            "certified": True,
            "quality": 0.9,
            "p99_latency_ms": 20,
            "peak_rss_mb": 100,
        },
        {
            "candidate_id": "b",
            "certified": True,
            "quality": 0.8,
            "p99_latency_ms": 10,
            "peak_rss_mb": 90,
        },
        {
            "candidate_id": "c",
            "certified": True,
            "quality": 0.7,
            "p99_latency_ms": 30,
            "peak_rss_mb": 200,
        },
        {
            "candidate_id": "d",
            "certified": False,
            "quality": 0.99,
            "p99_latency_ms": 1,
            "peak_rss_mb": 1,
        },
    ]
    front = pareto_select(candidates)
    ids = {c["candidate_id"] for c in front}
    assert "a" in ids
    assert "b" in ids
    assert "c" not in ids
    assert "d" not in ids


def test_report_redaction(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    home = tmp_path / "homeuser"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    text = redact_path(str(home / "secret" / "x"), home=str(home))
    assert str(home) not in text
    assert "${HOME}" in text
    doc = build_report_document(
        {
            "run_identity": {"run_id": "r1", "path": str(home / "run")},
            "limitations": [{"reason_code": "unavailable.sensor"}],
        }
    )
    dumped = json.dumps(doc)
    assert str(home) not in dumped
    assert "${HOME}" in dumped


def test_worker_timeout(tmp_path: Path) -> None:
    script = tmp_path / "slow.py"
    script.write_text("import time\ntime.sleep(5)\n", encoding="utf-8")
    with pytest.raises(PerceptShiftError) as exc:
        launch_bench_worker(
            worker_argv=["python3", str(script)],
            cwd=tmp_path,
            timeout_seconds=0.2,
        )
    assert exc.value.code == ErrorCode.BENCHMARK_TIMEOUT


def test_quantize_static_when_available(tmp_path: Path) -> None:
    pytest.importorskip("onnxruntime")
    model_path = make_tiny_onnx(tmp_path / "tiny.onnx")
    # Identity may not quantize meaningfully; ensure typed failure or success without fabrication.
    samples = [{"input": np.zeros((1, 3, 4, 4), dtype=np.float32)}]
    out = tmp_path / "q.onnx"
    try:
        result = quantize_static_qdq(
            model_path,
            out,
            method=CalibrationMethod.MINMAX,
            calibration_samples=samples,
            input_name="input",
        )
        assert result.output_path.is_file()
        assert result.calibration_sample_count == 1
    except PerceptShiftError as exc:
        assert exc.code in {
            ErrorCode.QUANTIZATION_FAILED,
            ErrorCode.QUANTIZATION_UNAVAILABLE,
        }


def _minimal_forge_config(tmp_path: Path, model_path: Path, cal: Path, ev: Path) -> Path:
    cfg = {
        "schema_version": "1.0",
        "document_type": "perceptshift.forge_config",
        "project": {
            "name": "unit",
            "output_root": str((tmp_path / "out").resolve()),
            "random_seed": 7,
        },
        "model": {
            "baseline_path": str(model_path.resolve()),
            "adapter": "raw_tensor",
            "adapter_config": {},
            "expected_input": {},
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
            "per_candidate_timeout_seconds": 30,
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
            "metric_name": "classification_accuracy",
            "direction": "higher_is_better",
            "minimum_absolute_value": 0.0,
            "maximum_degradation_from_baseline": 1.0,
            "confidence_level": 0.95,
        },
        "certification": {
            "deadline_ms": 100.0,
            "maximum_peak_rss_mb": 2048,
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


def test_forge_run_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg-data"))
    model_path = make_tiny_onnx(tmp_path / "model.onnx")
    cal_root = tmp_path / "cal"
    ev_root = tmp_path / "ev"
    from helpers import raw_tensor_manifest, write_float_tensor

    write_float_tensor(cal_root / "a.npy", (1, 3, 4, 4))
    import numpy as np

    ev_root.mkdir(parents=True, exist_ok=True)
    np.save(str(ev_root / "b.npy"), np.ones((1, 3, 4, 4), dtype=np.float32))
    cal = write_json(
        tmp_path / "cal.json",
        raw_tensor_manifest(cal_root, [{"path": "a.npy", "item_id": "a", "label": 0}]),
    )
    ev_doc = raw_tensor_manifest(ev_root, [{"path": "b.npy", "item_id": "b", "label": 1}])
    ev_doc["split_name"] = "evaluation"
    ev = write_json(tmp_path / "ev.json", ev_doc)
    config = _minimal_forge_config(tmp_path, model_path, cal, ev)
    # Inject expected_input + preprocess into forge yaml
    cfg = yaml.safe_load(config.read_text(encoding="utf-8"))
    cfg["model"]["expected_input"] = {"shape": [1, 3, 4, 4], "layout": "nchw"}
    cfg["model"]["preprocess"] = {
        "input_width": 4,
        "input_height": 4,
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
    config.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    result = run_forge(config, maximum_candidates=16)
    assert Path(result["root"]).is_dir()
    assert (Path(result["root"]) / "run.json").is_file()
    assert result["status"] == "completed"
    assert "benchmarking" in result["steps"]
    assert "building_bundle" in result["steps"]
    root = Path(result["root"])
    stream = json.loads((root / "inputs" / "bench-stream.json").read_text(encoding="utf-8"))
    assert stream["document_type"] == "perceptshift.benchmark_stream"
    assert "samples" in stream and len(stream["samples"]) >= 1
    assert "synthetic_float_samples" not in stream or "samples" in stream
    bundle = root / "bundle" / "profile-bundle" / "manifest.json"
    assert bundle.is_file()
    manifest = json.loads(bundle.read_text(encoding="utf-8"))
    paths = {f["path"] for f in manifest["files"]}
    assert any(p.startswith("models/") for p in paths)
    assert any(p.startswith("profiles/") for p in paths)
    assert any(p.startswith("attestations/") for p in paths)
    for entry in manifest["files"]:
        assert not Path(entry["path"]).is_absolute()
        assert ".." not in Path(entry["path"]).parts
    # Certification facts must cite evidence, not bare literals without refs.
    cert_files = [p for p in (root / "certification").glob("*.json") if p.name != "frontier.json"]
    assert cert_files
    cert = json.loads(cert_files[0].read_text(encoding="utf-8"))
    assert cert.get("evidence_root")
    for gate in cert.get("gates") or []:
        assert gate.get("evidence_references"), gate
    assert make_run_id("unit")


def test_ed25519_bundle_sign_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from helpers import raw_tensor_manifest, write_ed25519_private_key, write_float_tensor

    from perceptshift_forge.bundle import sign_bundle, verify_bundle, verify_bundle_signature

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg-data"))
    model_path = make_tiny_onnx(tmp_path / "model.onnx")
    cal_root = tmp_path / "cal"
    ev_root = tmp_path / "ev"
    write_float_tensor(cal_root / "a.npy", (1, 3, 4, 4))
    import numpy as np

    ev_root.mkdir(parents=True, exist_ok=True)
    np.save(str(ev_root / "b.npy"), np.ones((1, 3, 4, 4), dtype=np.float32))
    cal = write_json(
        tmp_path / "cal.json",
        raw_tensor_manifest(cal_root, [{"path": "a.npy", "item_id": "a", "label": 0}]),
    )
    ev_doc = raw_tensor_manifest(ev_root, [{"path": "b.npy", "item_id": "b", "label": 1}])
    ev_doc["split_name"] = "evaluation"
    ev = write_json(tmp_path / "ev.json", ev_doc)
    config = _minimal_forge_config(tmp_path, model_path, cal, ev)
    cfg = yaml.safe_load(config.read_text(encoding="utf-8"))
    cfg["model"]["expected_input"] = {"shape": [1, 3, 4, 4], "layout": "nchw"}
    cfg["model"]["preprocess"] = {
        "input_width": 4,
        "input_height": 4,
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
    cfg["quality"]["metric_name"] = "numeric_equivalence"
    config.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    result = run_forge(config, maximum_candidates=16)
    bundle_root = Path(result["root"]) / "bundle" / "profile-bundle"
    key = write_ed25519_private_key(tmp_path / "ed25519.key")
    signed = sign_bundle(bundle_root, key_path=key)
    assert signed["algorithm"] == "ed25519"
    assert signed["ok"] is True
    sig = json.loads((bundle_root / "manifest.sig").read_text(encoding="utf-8"))
    assert sig["algorithm"] == "ed25519"
    assert len(sig["signature"]) == 128
    assert len(sig["public_key"]) == 64
    verified = verify_bundle_signature(bundle_root)
    assert verified["ok"] is True
    report = verify_bundle(bundle_root)
    assert report["signature_present"] is True
    assert report["signature_ok"] is True


def test_raw_tensor_manifest_and_equivalence(tmp_path: Path) -> None:
    from helpers import raw_tensor_manifest, write_float_tensor

    from perceptshift_forge.datasets.validate import validate_dataset_manifest
    from perceptshift_forge.evaluation import numeric_equivalence

    root = tmp_path / "raw"
    write_float_tensor(root / "a.npy")
    write_float_tensor(root / "b.npy")
    man = raw_tensor_manifest(
        root,
        [
            {"path": "a.npy", "item_id": "a"},
            {"path": "b.npy", "item_id": "b"},
        ],
    )
    path = write_json(tmp_path / "raw.json", man)
    result = validate_dataset_manifest(path)
    assert result.ok
    assert result.item_count == 2
    ref = [np.zeros((1, 3, 4, 4), dtype=np.float32)]
    cand = [np.zeros((1, 3, 4, 4), dtype=np.float32)]
    eq = numeric_equivalence(ref, cand, dataset_hash="x", adapter_name="raw_tensor")
    assert eq.attestation["pass"] is True


def test_no_hardcoded_cert_literals_in_orchestration_source() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "perceptshift_forge"
        / "orchestration"
        / "__init__.py"
    ).read_text(encoding="utf-8")
    assert '"schema_valid": True' not in source
    assert '"integrity_ok": True' not in source
    assert '"peak_rss_mb": 64.0' not in source
    assert 'write_atomic_json(dataset_stream, {"synthetic_float_samples"' not in source
    assert "build_certification_context" in source
    assert "build_benchmark_stream" in source
    assert "evaluate_candidate_quality" in source


def test_blake2b_not_accepted_as_ed25519(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from helpers import raw_tensor_manifest, write_float_tensor

    from perceptshift_forge.bundle import verify_bundle_signature

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg-data"))
    model_path = make_tiny_onnx(tmp_path / "model.onnx")
    cal_root = tmp_path / "cal"
    ev_root = tmp_path / "ev"
    write_float_tensor(cal_root / "a.npy", (1, 3, 4, 4))
    import numpy as np

    ev_root.mkdir(parents=True, exist_ok=True)
    np.save(str(ev_root / "b.npy"), np.ones((1, 3, 4, 4), dtype=np.float32))
    cal = write_json(
        tmp_path / "cal.json",
        raw_tensor_manifest(cal_root, [{"path": "a.npy", "item_id": "a", "label": 0}]),
    )
    ev_doc = raw_tensor_manifest(ev_root, [{"path": "b.npy", "item_id": "b", "label": 1}])
    ev_doc["split_name"] = "evaluation"
    ev = write_json(tmp_path / "ev.json", ev_doc)
    config = _minimal_forge_config(tmp_path, model_path, cal, ev)
    cfg = yaml.safe_load(config.read_text(encoding="utf-8"))
    cfg["model"]["expected_input"] = {"shape": [1, 3, 4, 4], "layout": "nchw"}
    cfg["model"]["preprocess"] = {
        "input_width": 4,
        "input_height": 4,
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
    cfg["quality"]["metric_name"] = "numeric_equivalence"
    config.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    result = run_forge(config, maximum_candidates=16)
    bundle_root = Path(result["root"]) / "bundle" / "profile-bundle"
    (bundle_root / "manifest.sig").write_text("deadbeef" * 8 + "\n", encoding="utf-8")
    with pytest.raises(PerceptShiftError) as exc:
        verify_bundle_signature(bundle_root)
    assert exc.value.code == ErrorCode.SIGNATURE_INVALID
