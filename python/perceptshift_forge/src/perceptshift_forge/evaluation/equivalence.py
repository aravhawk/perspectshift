"""Numeric output-equivalence evaluation for raw_tensor adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from perceptshift_common.errors import ErrorCode, PerceptShiftError
from perceptshift_common.hashing import sha256_canonical
from perceptshift_common.producer import envelope_fields
from perceptshift_common.version import get_version
from perceptshift_forge.evaluation.types import EvaluationResult


@dataclass(slots=True)
class EquivalenceTolerances:
    max_abs_error: float = 1e-5
    max_rel_error: float = 1e-5
    max_mean_abs_error: float | None = None
    min_cosine_similarity: float | None = None


def numeric_equivalence(
    reference_outputs: list[np.ndarray],
    candidate_outputs: list[np.ndarray],
    *,
    dataset_hash: str,
    adapter_name: str,
    adapter_config: dict[str, Any] | None = None,
    tolerances: EquivalenceTolerances | None = None,
) -> EvaluationResult:
    if len(reference_outputs) != len(candidate_outputs):
        raise PerceptShiftError(
            code=ErrorCode.EQUIVALENCE_GATE_FAILED,
            message="Reference/candidate output count mismatch",
        )
    if not reference_outputs:
        raise PerceptShiftError(
            code=ErrorCode.DATASET_INVALID,
            message="Cannot evaluate equivalence on empty output set",
        )
    tol = tolerances or EquivalenceTolerances()
    max_abs = 0.0
    max_rel = 0.0
    abs_errors: list[float] = []
    cosine_values: list[float] = []
    for ref, cand in zip(reference_outputs, candidate_outputs, strict=True):
        r = np.asarray(ref, dtype=np.float64)
        c = np.asarray(cand, dtype=np.float64)
        if r.shape != c.shape:
            raise PerceptShiftError(
                code=ErrorCode.EQUIVALENCE_GATE_FAILED,
                message=f"Output shape mismatch: {r.shape} vs {c.shape}",
            )
        if r.dtype != c.dtype and r.dtype.kind != c.dtype.kind:
            pass  # compared as float64 above
        diff = np.abs(r - c)
        abs_err = float(np.max(diff)) if diff.size else 0.0
        denom = np.maximum(np.abs(r), 1e-12)
        rel_err = float(np.max(diff / denom)) if diff.size else 0.0
        max_abs = max(max_abs, abs_err)
        max_rel = max(max_rel, rel_err)
        abs_errors.append(float(np.mean(diff)) if diff.size else 0.0)
        flat_r = r.reshape(-1)
        flat_c = c.reshape(-1)
        norm_r = float(np.linalg.norm(flat_r))
        norm_c = float(np.linalg.norm(flat_c))
        if norm_r > 0 and norm_c > 0:
            cosine_values.append(float(np.dot(flat_r, flat_c) / (norm_r * norm_c)))
        else:
            cosine_values.append(1.0 if abs_err == 0.0 else 0.0)

    mean_abs = float(np.mean(abs_errors)) if abs_errors else 0.0
    min_cos = min(cosine_values) if cosine_values else 1.0
    passed = max_abs <= tol.max_abs_error and max_rel <= tol.max_rel_error
    if tol.max_mean_abs_error is not None and mean_abs > tol.max_mean_abs_error:
        passed = False
    if tol.min_cosine_similarity is not None and min_cos < tol.min_cosine_similarity:
        passed = False

    # Higher is better score in [0, 1] derived from abs error vs tolerance.
    score = 1.0 if passed else max(0.0, 1.0 - max_abs / max(tol.max_abs_error, 1e-12))

    attestation = envelope_fields(document_type="perceptshift.quality_attestation")
    attestation.update(
        {
            "dataset_hash": dataset_hash,
            "evaluator_version": get_version(),
            "adapter_name": adapter_name,
            "adapter_config_hash": sha256_canonical(adapter_config or {}),
            "metric_name": "numeric_equivalence",
            "metric_direction": "higher_is_better",
            "baseline_value": 1.0,
            "candidate_value": score,
            "absolute_delta": score - 1.0,
            "relative_delta": score - 1.0,
            "sample_count": len(reference_outputs),
            "class_breakdown": {
                "max_abs_error": max_abs,
                "max_rel_error": max_rel,
                "mean_abs_error": mean_abs,
                "min_cosine_similarity": min_cos,
            },
            "pass": passed,
            "threshold_contract": {
                "max_abs_error": tol.max_abs_error,
                "max_rel_error": tol.max_rel_error,
                "max_mean_abs_error": tol.max_mean_abs_error,
                "min_cosine_similarity": tol.min_cosine_similarity,
            },
        }
    )
    return EvaluationResult(
        metric_name="numeric_equivalence",
        metric_direction="higher_is_better",
        value=score,
        sample_count=len(reference_outputs),
        class_breakdown=attestation["class_breakdown"],
        attestation=attestation,
        unavailable_reason=None,
    )
