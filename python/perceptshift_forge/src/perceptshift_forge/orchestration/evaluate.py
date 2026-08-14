"""Offline quality evaluation helpers used by Forge orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from perceptshift_common.errors import ErrorCode, PerceptShiftError
from perceptshift_common.hashing import write_atomic_json
from perceptshift_common.reason_codes import ReasonCode
from perceptshift_forge.datasets.stream import load_stream_tensors
from perceptshift_forge.evaluation import (
    EquivalenceTolerances,
    classification_accuracy,
    coco_map_50_95,
    numeric_equivalence,
    softmax_argmax,
)


def evaluate_candidate_quality(
    *,
    workspace_root: Path,
    config: dict[str, Any],
    candidate_id: str,
    candidate_manifest: dict[str, Any],
    baseline_model_path: Path,
    evaluation_manifest: dict[str, Any],
    evaluation_manifest_hash: str,
    stream_path: Path,
) -> dict[str, Any]:
    adapter_name = str((config.get("model") or {}).get("adapter") or "raw_tensor")
    quality_cfg = config.get("quality") or {}
    adapter_config = (config.get("model") or {}).get("adapter_config") or {}
    model_path = Path(
        candidate_manifest.get("model_absolute_path")
        or (workspace_root / str(candidate_manifest.get("model_path", "")))
    )
    eval_samples = load_stream_tensors(stream_path, role="eval")
    if not eval_samples:
        return {
            "candidate_id": candidate_id,
            "adapter": adapter_name,
            "quality_metric_name": quality_cfg.get("metric_name"),
            "quality_value": None,
            "quality_ok": False,
            "equivalence_ok": False,
            "unavailable_reason": str(ReasonCode.UNAVAILABLE_DATA),
            "message": "No evaluation samples in benchmark stream",
        }

    if adapter_name == "raw_tensor":
        return _evaluate_raw_tensor(
            candidate_id=candidate_id,
            adapter_name=adapter_name,
            adapter_config=adapter_config,
            baseline_model_path=baseline_model_path,
            candidate_model_path=model_path,
            eval_samples=eval_samples,
            dataset_hash=evaluation_manifest_hash,
            quality_cfg=quality_cfg,
            workspace_root=workspace_root,
        )

    if adapter_name == "image_classification":
        return _evaluate_classification(
            candidate_id=candidate_id,
            adapter_name=adapter_name,
            adapter_config=adapter_config,
            candidate_model_path=model_path,
            eval_samples=eval_samples,
            dataset_hash=evaluation_manifest_hash,
            quality_cfg=quality_cfg,
            workspace_root=workspace_root,
            baseline_model_path=baseline_model_path,
        )

    if adapter_name == "yolo_v8_detection":
        return _evaluate_yolo(
            candidate_id=candidate_id,
            adapter_name=adapter_name,
            adapter_config=adapter_config,
            evaluation_manifest=evaluation_manifest,
            dataset_hash=evaluation_manifest_hash,
            quality_cfg=quality_cfg,
            workspace_root=workspace_root,
            baseline_model_path=baseline_model_path,
        )

    return {
        "candidate_id": candidate_id,
        "adapter": adapter_name,
        "quality_metric_name": quality_cfg.get("metric_name"),
        "quality_value": None,
        "quality_ok": False,
        "equivalence_ok": False,
        "unavailable_reason": "EVALUATION_UNSUPPORTED_ADAPTER",
        "message": f"No evaluator wired for adapter {adapter_name}",
    }


def _run_onnx(model_path: Path, tensors: list[np.ndarray]) -> list[np.ndarray]:
    try:
        import onnxruntime as ort
    except ImportError as exc:
        raise PerceptShiftError(
            code=ErrorCode.DEPENDENCY_UNAVAILABLE,
            message="onnxruntime required for offline quality evaluation",
            cause=exc,
        ) from exc
    if not model_path.is_file():
        raise PerceptShiftError(
            code=ErrorCode.MODEL_INVALID,
            message=f"Model missing for evaluation: {model_path}",
        )
    session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
    input_name = session.get_inputs()[0].name
    outputs: list[np.ndarray] = []
    for tensor in tensors:
        feeds = {input_name: np.asarray(tensor, dtype=np.float32)}
        out = session.run(None, feeds)
        outputs.append(np.asarray(out[0]))
    return outputs


def _evaluate_raw_tensor(
    *,
    candidate_id: str,
    adapter_name: str,
    adapter_config: dict[str, Any],
    baseline_model_path: Path,
    candidate_model_path: Path,
    eval_samples: list[dict[str, Any]],
    dataset_hash: str,
    quality_cfg: dict[str, Any],
    workspace_root: Path,
) -> dict[str, Any]:
    tensors = [np.asarray(s["tensor"], dtype=np.float32) for s in eval_samples]
    baseline_out = _run_onnx(baseline_model_path, tensors)
    candidate_out = _run_onnx(candidate_model_path, tensors)
    tol = EquivalenceTolerances(
        max_abs_error=float(adapter_config.get("max_abs_error", 1e-4)),
        max_rel_error=float(adapter_config.get("max_rel_error", 1e-4)),
    )
    result = numeric_equivalence(
        baseline_out,
        candidate_out,
        dataset_hash=dataset_hash,
        adapter_name=adapter_name,
        adapter_config=adapter_config,
        tolerances=tol,
    )
    attestation_rel = f"evaluation/{candidate_id}.attestation.json"
    write_atomic_json(workspace_root / attestation_rel, result.attestation)
    # Quality is not_applicable when equivalence is the certification metric.
    quality_ok = bool(result.attestation.get("pass"))
    return {
        "candidate_id": candidate_id,
        "adapter": adapter_name,
        "quality_metric_name": "not_applicable",
        "quality_value": None,
        "quality_status": "not_applicable",
        "quality_ok": quality_ok,
        "equivalence_ok": quality_ok,
        "equivalence_score": result.value,
        "equivalence_status": "pass" if quality_ok else "fail",
        "attestation_path": attestation_rel,
        "unavailable_reason": None,
        "sample_count": result.sample_count,
        "class_breakdown": result.class_breakdown,
        "metric_name_configured": quality_cfg.get("metric_name"),
    }


def _evaluate_classification(
    *,
    candidate_id: str,
    adapter_name: str,
    adapter_config: dict[str, Any],
    candidate_model_path: Path,
    eval_samples: list[dict[str, Any]],
    dataset_hash: str,
    quality_cfg: dict[str, Any],
    workspace_root: Path,
    baseline_model_path: Path | None = None,
) -> dict[str, Any]:
    labels = []
    for sample in eval_samples:
        if sample.get("label") is None:
            return {
                "candidate_id": candidate_id,
                "adapter": adapter_name,
                "quality_metric_name": "classification_accuracy",
                "quality_value": None,
                "quality_ok": False,
                "equivalence_ok": False,
                "equivalence_status": "not_required",
                "unavailable_reason": "EVALUATION_REQUIRES_LABELS",
                "message": "Evaluation samples missing class labels",
            }
        labels.append(int(sample["label"]))

    # Prefer production ProfileExecutor outputs from the native bench worker.
    native_path = workspace_root / "evaluation" / f"{candidate_id}.native_outputs.json"
    predictions: list[int] | None = None
    if native_path.is_file():
        import json

        native = json.loads(native_path.read_text(encoding="utf-8"))
        by_id = {
            str(s.get("sample_id")): s for s in (native.get("samples") or []) if isinstance(s, dict)
        }
        preds: list[int] = []
        complete = True
        for sample in eval_samples:
            sid = str(sample.get("sample_id"))
            row = by_id.get(sid)
            if not row:
                complete = False
                break
            if "top_class_id" in row:
                preds.append(int(row["top_class_id"]))
            elif row.get("classifications"):
                preds.append(int(row["classifications"][0]["class_id"]))
            else:
                complete = False
                break
        if complete and len(preds) == len(labels):
            predictions = preds

    if predictions is None:
        # Fallback only when native outputs are unavailable (should not happen in
        # production Forge path after bench worker emission).
        tensors = [np.asarray(s["tensor"], dtype=np.float32) for s in eval_samples]
        outputs = _run_onnx(candidate_model_path, tensors)
        predictions = []
        for out in outputs:
            flat = np.asarray(out).reshape(-1)
            if flat.size == 1:
                predictions.append(round(float(flat[0])))
            else:
                predictions.append(softmax_argmax(flat))

    baseline_value: float | None = None
    max_deg = quality_cfg.get("maximum_degradation_from_baseline")

    def _is_baseline_candidate(cand: str, doc: dict[str, Any]) -> bool:
        if "baseline" in cand.lower():
            return True
        man_path = workspace_root / "candidates" / "manifests" / f"{cand}.json"
        if man_path.is_file():
            import json as _json

            man = _json.loads(man_path.read_text(encoding="utf-8"))
            label = str(man.get("label") or "")
            lineage = (man.get("provenance") or {}).get("lineage") or man.get("lineage") or {}
            if lineage.get("transformation") == "baseline" or label.lower().startswith("baseline"):
                return True
        lineage = (doc.get("provenance") or {}).get("lineage") or doc.get("lineage") or {}
        return lineage.get("transformation") == "baseline"

    # Prefer baseline candidate native outputs (identical production path).
    current_is_baseline = False
    man_path = workspace_root / "candidates" / "manifests" / f"{candidate_id}.json"
    if man_path.is_file():
        import json as _json

        man = _json.loads(man_path.read_text(encoding="utf-8"))
        label = str(man.get("label") or "")
        lineage = (man.get("provenance") or {}).get("lineage") or man.get("lineage") or {}
        current_is_baseline = lineage.get(
            "transformation"
        ) == "baseline" or label.lower().startswith("baseline")
    if current_is_baseline and predictions is not None:
        baseline_value = sum(
            1 for p, y in zip(predictions, labels, strict=True) if int(p) == int(y)
        ) / len(labels)
    else:
        baseline_native = None
        for path in sorted((workspace_root / "evaluation").glob("*.native_outputs.json")):
            import json as _json

            doc = _json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(doc, dict):
                continue
            cand = str(doc.get("candidate_id") or path.name.replace(".native_outputs.json", ""))
            if _is_baseline_candidate(cand, doc):
                baseline_native = doc
                break
        if baseline_native is not None:
            by_id = {
                str(s.get("sample_id")): s
                for s in (baseline_native.get("samples") or [])
                if isinstance(s, dict)
            }
            baseline_preds: list[int] = []
            complete = True
            for sample in eval_samples:
                sid = str(sample.get("sample_id"))
                row = by_id.get(sid)
                if not row:
                    complete = False
                    break
                if "top_class_id" in row:
                    baseline_preds.append(int(row["top_class_id"]))
                elif row.get("classifications"):
                    baseline_preds.append(int(row["classifications"][0]["class_id"]))
                else:
                    complete = False
                    break
            if complete and len(baseline_preds) == len(labels):
                baseline_value = sum(
                    1 for p, y in zip(baseline_preds, labels, strict=True) if int(p) == int(y)
                ) / len(labels)
    if baseline_value is None and max_deg is not None:
        raise PerceptShiftError(
            code=ErrorCode.QUALITY_GATE_FAILED,
            message=(
                "maximum_degradation_from_baseline requires measured baseline accuracy "
                "from the native production path; baseline native outputs unavailable"
            ),
        )
    _ = baseline_model_path  # reserved for explicit baseline model path overrides

    result = classification_accuracy(
        predictions,
        labels,
        dataset_hash=dataset_hash,
        adapter_name=adapter_name,
        adapter_config=adapter_config,
        baseline_value=baseline_value,
        minimum_absolute_value=float(quality_cfg.get("minimum_absolute_value") or 0.0),
        maximum_degradation=max_deg,
    )
    attestation_rel = f"evaluation/{candidate_id}.attestation.json"
    write_atomic_json(workspace_root / attestation_rel, result.attestation)
    return {
        "candidate_id": candidate_id,
        "adapter": adapter_name,
        "quality_metric_name": result.metric_name,
        "quality_value": result.value,
        "baseline_accuracy": baseline_value,
        "quality_ok": bool(result.attestation.get("pass")),
        "equivalence_ok": True,
        "equivalence_status": "not_required",
        "attestation_path": attestation_rel,
        "unavailable_reason": None,
        "sample_count": result.sample_count,
        "class_breakdown": result.class_breakdown,
        "predictions_source": "native_bench_worker" if native_path.is_file() else "ort_fallback",
    }


def _evaluate_yolo(
    *,
    candidate_id: str,
    adapter_name: str,
    adapter_config: dict[str, Any],
    evaluation_manifest: dict[str, Any],
    dataset_hash: str,
    quality_cfg: dict[str, Any],
    workspace_root: Path,
    baseline_model_path: Path | None = None,
) -> dict[str, Any]:
    root = Path(evaluation_manifest["root"])
    annotation_rel = evaluation_manifest.get("annotation_path")
    if not isinstance(annotation_rel, str):
        return {
            "candidate_id": candidate_id,
            "adapter": adapter_name,
            "quality_metric_name": "coco_map_50_95",
            "quality_value": None,
            "quality_ok": False,
            "equivalence_ok": False,
            "equivalence_status": "not_required",
            "unavailable_reason": str(ReasonCode.UNAVAILABLE_DATA),
            "message": "YOLO evaluation requires annotation_path",
        }
    gt_path = root / annotation_rel
    detections_path = workspace_root / "evaluation" / f"{candidate_id}.detections.json"
    if not detections_path.is_file():
        return {
            "candidate_id": candidate_id,
            "adapter": adapter_name,
            "quality_metric_name": "coco_map_50_95",
            "quality_value": None,
            "quality_ok": False,
            "equivalence_ok": False,
            "equivalence_status": "not_required",
            "unavailable_reason": "EVALUATION_REQUIRES_LABELED_INFERENCE_FOR_ADAPTER",
            "message": (
                "YOLO mAP requires normalized detection JSON from the bench worker; "
                f"missing {detections_path.name}"
            ),
        }
    import json

    detections = json.loads(detections_path.read_text(encoding="utf-8"))
    if not isinstance(detections, list):
        detections = detections.get("detections") or []
    # Keep only detections whose sample_id maps to evaluation GT images.
    gt = json.loads(gt_path.read_text(encoding="utf-8"))
    eval_ids = {str(img.get("id")) for img in (gt.get("images") or []) if isinstance(img, dict)}
    detections = [
        d
        for d in detections
        if isinstance(d, dict) and str(d.get("sample_id") or d.get("image_id") or "") in eval_ids
    ]

    max_deg = quality_cfg.get("maximum_degradation_from_baseline")
    baseline_value: float | None = None

    def _baseline_manifest(cand: str) -> bool:
        man_path = workspace_root / "candidates" / "manifests" / f"{cand}.json"
        if not man_path.is_file():
            return "baseline" in cand.lower()
        man = json.loads(man_path.read_text(encoding="utf-8"))
        label = str(man.get("label") or "")
        lineage = (man.get("provenance") or {}).get("lineage") or man.get("lineage") or {}
        return lineage.get("transformation") == "baseline" or label.lower().startswith("baseline")

    current_is_baseline = _baseline_manifest(candidate_id)

    # Measure baseline mAP from baseline candidate detections on the same GT set.
    baseline_det_path = None
    for path in sorted((workspace_root / "evaluation").glob("*.detections.json")):
        cand = path.name.replace(".detections.json", "")
        if _baseline_manifest(cand):
            baseline_det_path = path
            break
    if baseline_det_path is None:
        for path in sorted((workspace_root / "evaluation").glob("*.detections.json")):
            doc = json.loads(path.read_text(encoding="utf-8"))
            cid = str(doc.get("candidate_id") or "")
            if _baseline_manifest(cid):
                baseline_det_path = path
                break

    # When evaluating the baseline candidate itself, compute its mAP first and use
    # it as both baseline and candidate (near-zero degradation by definition).
    if current_is_baseline and baseline_det_path is None:
        baseline_det_path = detections_path

    if baseline_det_path is not None:
        baseline_dets = json.loads(baseline_det_path.read_text(encoding="utf-8"))
        if not isinstance(baseline_dets, list):
            baseline_dets = baseline_dets.get("detections") or []
        baseline_dets = [
            d
            for d in baseline_dets
            if isinstance(d, dict)
            and str(d.get("sample_id") or d.get("image_id") or "") in eval_ids
        ]
        try:
            baseline_result = coco_map_50_95(
                gt_path,
                baseline_dets,
                dataset_hash=dataset_hash,
                adapter_name=adapter_name,
                adapter_config=adapter_config,
                minimum_absolute_value=0.0,
                maximum_degradation=None,
            )
            baseline_value = float(baseline_result.value)
            write_atomic_json(
                workspace_root / "evaluation" / "baseline_map_attestation.json",
                baseline_result.attestation,
            )
        except PerceptShiftError as exc:
            return {
                "candidate_id": candidate_id,
                "adapter": adapter_name,
                "quality_metric_name": "coco_map_50_95",
                "quality_value": None,
                "quality_ok": False,
                "equivalence_ok": False,
                "equivalence_status": "not_required",
                "unavailable_reason": str(
                    (exc.details or {}).get("reason_code", ReasonCode.UNAVAILABLE_COCO_TOOLS)
                ),
                "message": f"Baseline mAP measurement failed: {exc.message}",
            }
    if max_deg is not None and baseline_value is None:
        return {
            "candidate_id": candidate_id,
            "adapter": adapter_name,
            "quality_metric_name": "coco_map_50_95",
            "quality_value": None,
            "quality_ok": False,
            "equivalence_ok": False,
            "equivalence_status": "not_required",
            "unavailable_reason": "BASELINE_MAP_REQUIRED",
            "message": (
                "maximum_degradation_from_baseline requires measured baseline mAP "
                "on the held-out evaluation set"
            ),
        }

    try:
        result = coco_map_50_95(
            gt_path,
            detections,
            dataset_hash=dataset_hash,
            adapter_name=adapter_name,
            adapter_config=adapter_config,
            baseline_value=baseline_value,
            minimum_absolute_value=float(quality_cfg.get("minimum_absolute_value") or 0.0),
            maximum_degradation=max_deg,
        )
    except PerceptShiftError as exc:
        return {
            "candidate_id": candidate_id,
            "adapter": adapter_name,
            "quality_metric_name": "coco_map_50_95",
            "quality_value": None,
            "quality_ok": False,
            "equivalence_ok": False,
            "equivalence_status": "not_required",
            "unavailable_reason": str(
                (exc.details or {}).get("reason_code", ReasonCode.UNAVAILABLE_COCO_TOOLS)
            ),
            "message": exc.message,
        }
    attestation_rel = f"evaluation/{candidate_id}.attestation.json"
    write_atomic_json(workspace_root / attestation_rel, result.attestation)
    return {
        "candidate_id": candidate_id,
        "adapter": adapter_name,
        "quality_metric_name": result.metric_name,
        "quality_value": result.value,
        "baseline_map": baseline_value,
        "quality_ok": bool(result.attestation.get("pass")),
        "equivalence_ok": True,
        "equivalence_status": "not_required",
        "attestation_path": attestation_rel,
        "unavailable_reason": None,
        "sample_count": result.sample_count,
    }
