"""Regression tests for Forge quality baseline / degradation semantics."""

from __future__ import annotations

from pathlib import Path

import pytest

from perceptshift_common.errors import ErrorCode, PerceptShiftError
from perceptshift_forge.evaluation import classification_accuracy, coco_map_50_95
from perceptshift_forge.orchestration.evaluate import _evaluate_classification


def test_classification_identical_predictions_zero_degradation() -> None:
    result = classification_accuracy(
        [0, 1, 1],
        [0, 1, 1],
        dataset_hash="d",
        adapter_name="image_classification",
        baseline_value=1.0,
        maximum_degradation=0.01,
    )
    assert result.value == 1.0
    assert result.attestation["pass"] is True
    assert result.attestation["absolute_delta"] == 0.0


def test_classification_degraded_fails_threshold() -> None:
    result = classification_accuracy(
        [0, 0, 0],
        [0, 1, 1],
        dataset_hash="d",
        adapter_name="image_classification",
        baseline_value=1.0,
        maximum_degradation=0.1,
    )
    assert result.value == pytest.approx(1 / 3)
    assert result.attestation["pass"] is False


def test_evaluate_classification_requires_baseline_when_configured(tmp_path: Path) -> None:
    (tmp_path / "evaluation").mkdir()
    (tmp_path / "candidates" / "manifests").mkdir(parents=True)
    # Provide native predictions so evaluation reaches the baseline gate.
    (tmp_path / "evaluation" / "cand.native_outputs.json").write_text(
        '{"candidate_id":"cand","samples":[{"sample_id":"a","top_class_id":0}]}',
        encoding="utf-8",
    )
    samples = [{"sample_id": "a", "label": 0, "tensor": [0.0]}]
    with pytest.raises(PerceptShiftError) as exc:
        _evaluate_classification(
            candidate_id="cand",
            adapter_name="image_classification",
            adapter_config={},
            candidate_model_path=tmp_path / "missing.onnx",
            eval_samples=samples,
            dataset_hash="h",
            quality_cfg={"maximum_degradation_from_baseline": 0.01, "minimum_absolute_value": 0.0},
            workspace_root=tmp_path,
            baseline_model_path=None,
        )
    assert exc.value.code == ErrorCode.QUALITY_GATE_FAILED
    assert "baseline" in exc.value.message.lower()


def test_coco_map_requires_detections(tmp_path: Path) -> None:
    gt = tmp_path / "gt.json"
    gt.write_text(
        '{"images":[{"id":1,"file_name":"a.png","width":10,"height":10}],'
        '"annotations":[],"categories":[{"id":0,"name":"obj"}]}',
        encoding="utf-8",
    )
    with pytest.raises(PerceptShiftError):
        coco_map_50_95(
            gt,
            [],
            dataset_hash="h",
            adapter_name="yolo_v8_detection",
        )
