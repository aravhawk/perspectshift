"""Quality evaluation: classification accuracy and COCO mAP when available."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

from perceptshift_common.errors import ErrorCode, PerceptShiftError
from perceptshift_common.hashing import sha256_canonical
from perceptshift_common.producer import envelope_fields
from perceptshift_common.reason_codes import ReasonCode
from perceptshift_common.version import get_version
from perceptshift_forge.evaluation.equivalence import (
    EquivalenceTolerances,
    numeric_equivalence,
)
from perceptshift_forge.evaluation.types import EvaluationResult

__all__ = [
    "EquivalenceTolerances",
    "EvaluationResult",
    "classification_accuracy",
    "coco_map_50_95",
    "numeric_equivalence",
    "softmax_argmax",
]


def classification_accuracy(
    predictions: list[int],
    labels: list[int],
    *,
    dataset_hash: str,
    adapter_name: str,
    adapter_config: dict[str, Any] | None = None,
    baseline_value: float | None = None,
    maximum_degradation: float | None = None,
    minimum_absolute_value: float = 0.0,
) -> EvaluationResult:
    if len(predictions) != len(labels):
        raise PerceptShiftError(
            code=ErrorCode.INTERNAL_INVARIANT_FAILED,
            message="predictions and labels length mismatch",
        )
    if not labels:
        raise PerceptShiftError(
            code=ErrorCode.DATASET_INVALID,
            message="Cannot evaluate empty label set",
        )
    correct = sum(1 for p, y in zip(predictions, labels, strict=True) if int(p) == int(y))
    value = correct / len(labels)
    breakdown: dict[str, Any] = {}
    for label in sorted(set(labels)):
        idxs = [i for i, y in enumerate(labels) if y == label]
        hits = sum(1 for i in idxs if int(predictions[i]) == int(labels[i]))
        breakdown[str(label)] = {
            "count": len(idxs),
            "correct": hits,
            "accuracy": hits / len(idxs) if idxs else 0.0,
        }

    passed = value >= minimum_absolute_value
    absolute_delta = None if baseline_value is None else value - baseline_value
    if baseline_value is not None and maximum_degradation is not None:
        if (baseline_value - value) > maximum_degradation:
            passed = False

    attestation = envelope_fields(document_type="perceptshift.quality_attestation")
    attestation.update(
        {
            "dataset_hash": dataset_hash,
            "evaluator_version": get_version(),
            "adapter_name": adapter_name,
            "adapter_config_hash": sha256_canonical(adapter_config or {}),
            "metric_name": "classification_accuracy",
            "metric_direction": "higher_is_better",
            "baseline_value": baseline_value if baseline_value is not None else value,
            "candidate_value": value,
            "absolute_delta": absolute_delta if absolute_delta is not None else 0.0,
            "relative_delta": (
                None
                if baseline_value in (None, 0)
                else (value - baseline_value) / abs(baseline_value)
            ),
            "sample_count": len(labels),
            "class_breakdown": breakdown,
            "pass": passed,
            "threshold_contract": {
                "minimum_absolute_value": minimum_absolute_value,
                "maximum_degradation_from_baseline": maximum_degradation,
            },
        }
    )
    return EvaluationResult(
        metric_name="classification_accuracy",
        metric_direction="higher_is_better",
        value=value,
        sample_count=len(labels),
        class_breakdown=breakdown,
        attestation=attestation,
    )


def _normalize_detections_for_coco(
    detections: list[dict[str, Any]], coco_gt: Any
) -> list[dict[str, Any]]:
    """Convert native bench-worker detections into pycocotools loadRes records.

    Bench worker emits top-left ``bbox: {x,y,w,h}`` (canonical Detection) with
    ``sample_id`` / ``class_id`` / ``confidence``. COCO expects the same top-left
    xywh plus ``image_id``, ``category_id``, and ``score``.
    """
    # Map sample_id / file_name → image_id from GT.
    id_by_sample: dict[str, int] = {}
    for img in coco_gt.dataset.get("images") or []:
        if not isinstance(img, dict):
            continue
        image_id = int(img["id"])
        id_by_sample[str(image_id)] = image_id
        if "file_name" in img:
            id_by_sample[str(img["file_name"])] = image_id
            id_by_sample[Path(str(img["file_name"])).stem] = image_id

    results: list[dict[str, Any]] = []
    for det in detections:
        if not isinstance(det, dict):
            continue
        # Already COCO-shaped?
        if "image_id" in det and "bbox" in det and isinstance(det["bbox"], list):
            results.append(
                {
                    "image_id": int(det["image_id"]),
                    "category_id": int(det.get("category_id", det.get("class_id", 0))),
                    "bbox": [float(x) for x in det["bbox"][:4]],
                    "score": float(det.get("score", det.get("confidence", 0.0))),
                }
            )
            continue
        sample_id = str(det.get("sample_id") or det.get("image_id") or "")
        image_id = id_by_sample.get(sample_id)
        if image_id is None and sample_id.isdigit():
            image_id = int(sample_id)
        if image_id is None:
            continue
        bbox = det.get("bbox")
        if isinstance(bbox, dict):
            # Canonical Detection already stores top-left x,y + w,h.
            x0 = float(bbox.get("x", 0.0))
            y0 = float(bbox.get("y", 0.0))
            w = float(bbox.get("w", 0.0))
            h = float(bbox.get("h", 0.0))
            coco_bbox = [x0, y0, w, h]
        elif isinstance(bbox, list) and len(bbox) >= 4:
            coco_bbox = [float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])]
        else:
            continue
        results.append(
            {
                "image_id": int(image_id),
                "category_id": int(det.get("class_id", det.get("category_id", 0))),
                "bbox": coco_bbox,
                "score": float(det.get("confidence", det.get("score", 0.0))),
            }
        )
    return results


def coco_map_50_95(
    coco_gt_path: Path,
    detections: list[dict[str, Any]],
    *,
    dataset_hash: str,
    adapter_name: str,
    adapter_config: dict[str, Any] | None = None,
    baseline_value: float | None = None,
    maximum_degradation: float | None = None,
    minimum_absolute_value: float = 0.0,
) -> EvaluationResult:
    try:
        from pycocotools.coco import COCO
        from pycocotools.cocoeval import COCOeval
    except ImportError as exc:
        attestation = envelope_fields(document_type="perceptshift.quality_attestation")
        attestation.update(
            {
                "dataset_hash": dataset_hash,
                "evaluator_version": get_version(),
                "adapter_name": adapter_name,
                "adapter_config_hash": sha256_canonical(adapter_config or {}),
                "metric_name": "coco_map_50_95",
                "metric_direction": "higher_is_better",
                "baseline_value": 0.0,
                "candidate_value": 0.0,
                "sample_count": 0,
                "pass": False,
                "threshold_contract": {
                    "minimum_absolute_value": minimum_absolute_value,
                    "maximum_degradation_from_baseline": maximum_degradation,
                },
                "unavailable": {
                    "reason_code": ReasonCode.UNAVAILABLE_COCO_TOOLS,
                    "message": "pycocotools is not installed",
                },
            }
        )
        raise PerceptShiftError(
            code=ErrorCode.DEPENDENCY_UNAVAILABLE,
            message="pycocotools is required for COCO mAP evaluation",
            remediation="Install optional dependency group: perceptshift-forge[coco]",
            details={"reason_code": ReasonCode.UNAVAILABLE_COCO_TOOLS},
            cause=exc,
        ) from exc

    if not coco_gt_path.is_file():
        raise PerceptShiftError(
            code=ErrorCode.DATASET_INVALID,
            message=f"COCO ground-truth file missing: {coco_gt_path}",
        )
    if not detections:
        raise PerceptShiftError(
            code=ErrorCode.DATASET_INVALID,
            message="No detections provided for COCO evaluation",
        )

    coco_gt = COCO(str(coco_gt_path))
    coco_results = _normalize_detections_for_coco(detections, coco_gt)
    if not coco_results:
        raise PerceptShiftError(
            code=ErrorCode.DATASET_INVALID,
            message="No COCO-compatible detections after normalization",
        )
    # pycocotools loadRes expects a JSON file path, not an in-memory list.
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tmp:
        json.dump(coco_results, tmp)
        tmp_path = Path(tmp.name)
    try:
        coco_dt = coco_gt.loadRes(str(tmp_path))
    finally:
        tmp_path.unlink(missing_ok=True)
    evaluator = COCOeval(coco_gt, coco_dt, iouType="bbox")
    evaluator.evaluate()
    evaluator.accumulate()
    evaluator.summarize()
    value = float(evaluator.stats[0])  # AP @ IoU=0.50:0.95
    sample_count = len(coco_gt.getImgIds())

    passed = value >= minimum_absolute_value
    absolute_delta = None if baseline_value is None else value - baseline_value
    if baseline_value is not None and maximum_degradation is not None:
        if (baseline_value - value) > maximum_degradation:
            passed = False

    attestation = envelope_fields(document_type="perceptshift.quality_attestation")
    attestation.update(
        {
            "dataset_hash": dataset_hash,
            "evaluator_version": get_version(),
            "adapter_name": adapter_name,
            "adapter_config_hash": sha256_canonical(adapter_config or {}),
            "metric_name": "coco_map_50_95",
            "metric_direction": "higher_is_better",
            "baseline_value": baseline_value if baseline_value is not None else value,
            "candidate_value": value,
            "absolute_delta": absolute_delta if absolute_delta is not None else 0.0,
            "relative_delta": (
                None
                if baseline_value in (None, 0)
                else (value - baseline_value) / abs(baseline_value)
            ),
            "sample_count": sample_count,
            "class_breakdown": {},
            "pass": passed,
            "threshold_contract": {
                "minimum_absolute_value": minimum_absolute_value,
                "maximum_degradation_from_baseline": maximum_degradation,
            },
        }
    )
    return EvaluationResult(
        metric_name="coco_map_50_95",
        metric_direction="higher_is_better",
        value=value,
        sample_count=sample_count,
        class_breakdown={},
        attestation=attestation,
    )


def softmax_argmax(logits: np.ndarray) -> int:
    if logits.ndim != 1:
        raise PerceptShiftError(
            code=ErrorCode.INFERENCE_FAILED,
            message="Expected 1-D logits for classification argmax",
        )
    return int(np.argmax(logits))
