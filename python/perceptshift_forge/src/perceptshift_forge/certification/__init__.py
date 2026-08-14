"""Certification gates (section 13.18)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from perceptshift_common.reason_codes import ReasonCode
from perceptshift_forge.certification.context import build_certification_context


@dataclass(slots=True)
class GateResult:
    name: str
    passed: bool
    required: bool
    evidence_references: list[str] = field(default_factory=list)
    measured_value: Any = None
    threshold: Any = None
    reason_codes: list[str] = field(default_factory=list)
    remediation: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "pass": self.passed,
            "required": self.required,
            "evidence_references": self.evidence_references,
            "measured_value": self.measured_value,
            "threshold": self.threshold,
            "reason_codes": self.reason_codes,
            "remediation": self.remediation,
        }


GateFn = Callable[[dict[str, Any]], GateResult]


def schema_gate(ctx: dict[str, Any]) -> GateResult:
    ok = bool(ctx.get("schema_valid", False))
    return GateResult(
        name="schema_gate",
        passed=ok,
        required=True,
        evidence_references=list(ctx.get("schema_evidence", [])),
        measured_value=ok,
        threshold=True,
        reason_codes=[] if ok else [ReasonCode.GATE_SCHEMA],
        remediation=None if ok else "Repair documents to satisfy config/schemas contracts",
    )


def integrity_gate(ctx: dict[str, Any]) -> GateResult:
    ok = bool(ctx.get("integrity_ok", False))
    return GateResult(
        name="integrity_gate",
        passed=ok,
        required=True,
        evidence_references=list(ctx.get("integrity_evidence", [])),
        measured_value=ok,
        threshold=True,
        reason_codes=[] if ok else [ReasonCode.GATE_INTEGRITY],
        remediation=None if ok else "Recompute and compare SHA-256 inventories",
    )


def model_validation_gate(ctx: dict[str, Any]) -> GateResult:
    ok = bool(ctx.get("model_valid", False))
    return GateResult(
        name="model_validation_gate",
        passed=ok,
        required=True,
        evidence_references=list(ctx.get("model_evidence", [])),
        measured_value=ok,
        threshold=True,
        reason_codes=[] if ok else [ReasonCode.GATE_MODEL_VALIDATION],
        remediation=None if ok else "Run onnx.checker and fix model issues",
    )


def host_compatibility_gate(ctx: dict[str, Any]) -> GateResult:
    ok = bool(ctx.get("host_compatible", False))
    return GateResult(
        name="host_compatibility_gate",
        passed=ok,
        required=True,
        evidence_references=list(ctx.get("host_evidence", [])),
        measured_value=ok,
        threshold=True,
        reason_codes=[] if ok else [ReasonCode.GATE_HOST_COMPATIBILITY],
        remediation=None if ok else "Certify on a matching host fingerprint",
    )


def provider_gate(ctx: dict[str, Any]) -> GateResult:
    ok = bool(ctx.get("provider_ok", False))
    return GateResult(
        name="provider_gate",
        passed=ok,
        required=True,
        evidence_references=list(ctx.get("provider_evidence", [])),
        measured_value=ctx.get("provider_assignment"),
        threshold=ctx.get("provider_threshold"),
        reason_codes=[] if ok else [ReasonCode.GATE_PROVIDER],
        remediation=None if ok else "Adjust EP order or relax provider requirements",
    )


def tensor_contract_gate(ctx: dict[str, Any]) -> GateResult:
    ok = bool(ctx.get("tensor_contract_ok", False))
    return GateResult(
        name="tensor_contract_gate",
        passed=ok,
        required=True,
        evidence_references=list(ctx.get("tensor_evidence", [])),
        measured_value=ok,
        threshold=True,
        reason_codes=[] if ok else [ReasonCode.GATE_TENSOR_CONTRACT],
        remediation=None if ok else "Align model IO tensors with adapter contracts",
    )


def semantic_equivalence_gate(ctx: dict[str, Any]) -> GateResult:
    required = bool(ctx.get("require_output_equivalence", True))
    ok = bool(ctx.get("equivalence_ok", False))
    return GateResult(
        name="semantic_equivalence_gate",
        passed=ok if required else True,
        required=required,
        evidence_references=list(ctx.get("equivalence_evidence", [])),
        measured_value=ctx.get("equivalence_score"),
        threshold=ctx.get("equivalence_threshold"),
        reason_codes=[] if ok or not required else [ReasonCode.GATE_SEMANTIC_EQUIVALENCE],
        remediation=None if ok or not required else "Investigate output digests vs baseline",
    )


def quality_gate(ctx: dict[str, Any]) -> GateResult:
    ok = bool(ctx.get("quality_ok", False))
    return GateResult(
        name="quality_gate",
        passed=ok,
        required=True,
        evidence_references=list(ctx.get("quality_evidence", [])),
        measured_value=ctx.get("quality_value"),
        threshold=ctx.get("quality_threshold"),
        reason_codes=[] if ok else [ReasonCode.GATE_QUALITY],
        remediation=None if ok else "Improve quality or relax documented thresholds",
    )


def memory_gate(ctx: dict[str, Any]) -> GateResult:
    peak = ctx.get("peak_rss_mb")
    limit = ctx.get("maximum_peak_rss_mb")
    ok = peak is not None and limit is not None and float(peak) <= float(limit)
    return GateResult(
        name="memory_gate",
        passed=bool(ok),
        required=True,
        evidence_references=list(ctx.get("memory_evidence", [])),
        measured_value=peak,
        threshold=limit,
        reason_codes=[] if ok else [ReasonCode.GATE_MEMORY],
        remediation=None if ok else "Reduce peak RSS or raise maximum_peak_rss_mb",
    )


def latency_gate(ctx: dict[str, Any]) -> GateResult:
    measured = ctx.get("latency_ms")
    deadline = ctx.get("deadline_ms")
    ok = measured is not None and deadline is not None and float(measured) <= float(deadline)
    return GateResult(
        name="latency_gate",
        passed=bool(ok),
        required=True,
        evidence_references=list(ctx.get("latency_evidence", [])),
        measured_value=measured,
        threshold=deadline,
        reason_codes=[] if ok else [ReasonCode.GATE_LATENCY],
        remediation=None if ok else "Select a faster candidate or raise deadline_ms",
    )


def environment_gate(ctx: dict[str, Any]) -> GateResult:
    required = bool(ctx.get("require_valid_environment", True))
    status = ctx.get("environment_status", "invalid")
    ok = status in {"valid", "valid_with_warnings"}
    passed = ok if required else True
    return GateResult(
        name="environment_gate",
        passed=passed,
        required=required,
        evidence_references=list(ctx.get("environment_evidence", [])),
        measured_value=status,
        threshold="valid|valid_with_warnings",
        reason_codes=[] if passed else [ReasonCode.GATE_ENVIRONMENT],
        remediation=None if passed else "Resolve preflight environment failures",
    )


def warmup_gate(ctx: dict[str, Any]) -> GateResult:
    ok = bool(ctx.get("warmup_ok", False))
    return GateResult(
        name="warmup_gate",
        passed=ok,
        required=True,
        evidence_references=list(ctx.get("warmup_evidence", [])),
        measured_value=ctx.get("warmup_iterations_completed"),
        threshold=ctx.get("warmup_iterations_required"),
        reason_codes=[] if ok else [ReasonCode.GATE_WARMUP],
        remediation=None if ok else "Ensure warmup iterations complete without errors",
    )


def artifact_completeness_gate(ctx: dict[str, Any]) -> GateResult:
    ok = bool(ctx.get("artifacts_complete", False))
    return GateResult(
        name="artifact_completeness_gate",
        passed=ok,
        required=True,
        evidence_references=list(ctx.get("artifact_evidence", [])),
        measured_value=ok,
        threshold=True,
        reason_codes=[] if ok else [ReasonCode.GATE_ARTIFACT_COMPLETENESS],
        remediation=None if ok else "Restore missing trial/evaluation/certification artifacts",
    )


ALL_GATES: list[GateFn] = [
    schema_gate,
    integrity_gate,
    model_validation_gate,
    host_compatibility_gate,
    provider_gate,
    tensor_contract_gate,
    semantic_equivalence_gate,
    quality_gate,
    memory_gate,
    latency_gate,
    environment_gate,
    warmup_gate,
    artifact_completeness_gate,
]


def run_certification_gates(ctx: dict[str, Any]) -> list[GateResult]:
    return [gate(ctx) for gate in ALL_GATES]


def is_certified(results: list[GateResult]) -> bool:
    return all(result.passed for result in results if result.required)


def pareto_select(
    candidates: list[dict[str, Any]],
    *,
    maximize: tuple[str, ...] = ("quality",),
    minimize: tuple[str, ...] = ("p99_latency_ms", "peak_rss_mb"),
) -> list[dict[str, Any]]:
    """Deterministic nondominated set over comparable numeric objectives."""
    feasible = [c for c in candidates if c.get("certified") is True]
    frontier: list[dict[str, Any]] = []
    for candidate in feasible:
        dominated = False
        for other in feasible:
            if other is candidate:
                continue
            if _dominates(other, candidate, maximize=maximize, minimize=minimize):
                dominated = True
                break
        if not dominated:
            frontier.append(candidate)
    frontier.sort(key=lambda c: str(c.get("candidate_id", "")))
    return frontier


__all__ = [
    "ALL_GATES",
    "GateResult",
    "artifact_completeness_gate",
    "build_certification_context",
    "environment_gate",
    "host_compatibility_gate",
    "integrity_gate",
    "is_certified",
    "latency_gate",
    "memory_gate",
    "model_validation_gate",
    "pareto_select",
    "provider_gate",
    "quality_gate",
    "run_certification_gates",
    "schema_gate",
    "semantic_equivalence_gate",
    "tensor_contract_gate",
    "warmup_gate",
]


def _dominates(
    a: dict[str, Any],
    b: dict[str, Any],
    *,
    maximize: tuple[str, ...],
    minimize: tuple[str, ...],
) -> bool:
    better_or_equal = True
    strictly_better = False
    for key in maximize:
        av = a.get(key)
        bv = b.get(key)
        if av is None or bv is None:
            return False
        if float(av) < float(bv):
            better_or_equal = False
        if float(av) > float(bv):
            strictly_better = True
    for key in minimize:
        av = a.get(key)
        bv = b.get(key)
        if av is None or bv is None:
            continue
        if float(av) > float(bv):
            better_or_equal = False
        if float(av) < float(bv):
            strictly_better = True
    return better_or_equal and strictly_better
