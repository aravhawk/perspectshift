"""Build certification gate context from validator evidence (no hardcoded facts)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from perceptshift_common.hashing import sha256_file, write_atomic_json
from perceptshift_common.producer import envelope_fields, utc_now_rfc3339
from perceptshift_common.reason_codes import ReasonCode
from perceptshift_common.schema import validate_document
from perceptshift_common.version import get_version


def _evidence(
    evidence_dir: Path,
    name: str,
    payload: dict[str, Any],
) -> tuple[str, str]:
    path = evidence_dir / f"{name}.json"
    doc = envelope_fields(document_type="perceptshift.certification_evidence")
    doc.update(
        {
            "validator": name,
            "validator_version": get_version(),
            "timestamp": utc_now_rfc3339(),
            **payload,
        }
    )
    write_atomic_json(path, doc)
    rel = f"certification/evidence/{path.name}"
    return rel, sha256_file(path)


def build_certification_context(
    *,
    workspace_root: Path,
    candidate_id: str,
    candidate_manifest: dict[str, Any],
    trial: dict[str, Any],
    evaluation: dict[str, Any],
    model_inspection: dict[str, Any] | None,
    cert_cfg: dict[str, Any],
    environment_status: str | None,
    host_fingerprint_path: Path | None = None,
) -> dict[str, Any]:
    """Compute gate inputs from artifacts; never invent measurements."""
    evidence_dir = workspace_root / "certification" / "evidence" / candidate_id
    evidence_dir.mkdir(parents=True, exist_ok=True)

    ctx: dict[str, Any] = {
        "require_output_equivalence": bool(cert_cfg.get("require_output_equivalence")),
        "require_valid_environment": bool(cert_cfg.get("require_valid_environment")),
        "maximum_peak_rss_mb": float(cert_cfg.get("maximum_peak_rss_mb") or 2048),
        "deadline_ms": float(cert_cfg.get("deadline_ms") or 100.0),
        "quality_threshold": (cert_cfg.get("quality") or {}).get("minimum_absolute_value"),
    }

    # Schema validity of candidate manifest (runtime-only keys stripped).
    schema_manifest = {k: v for k, v in candidate_manifest.items() if k != "model_absolute_path"}
    schema_ok = False
    schema_message = "not_run"
    try:
        validate_document(schema_manifest, "candidate_manifest")
        schema_ok = True
        schema_message = "candidate_manifest schema valid"
    except Exception as exc:
        schema_message = str(exc)
    schema_ref, _ = _evidence(
        evidence_dir,
        "schema",
        {"status": "pass" if schema_ok else "fail", "message": schema_message},
    )
    ctx["schema_valid"] = schema_ok
    ctx["schema_evidence"] = [schema_ref]

    # Integrity: model file hash matches manifest.
    model_path = Path(
        candidate_manifest.get("model_absolute_path")
        or (workspace_root / str(candidate_manifest.get("model_path", "")))
    )
    expected_hash = str(candidate_manifest.get("model_sha256") or "")
    integrity_ok = False
    integrity_msg = "model missing"
    if model_path.is_file() and expected_hash:
        actual = sha256_file(model_path)
        integrity_ok = actual == expected_hash
        integrity_msg = "hash match" if integrity_ok else f"hash mismatch {actual}"
    integ_ref, _ = _evidence(
        evidence_dir,
        "integrity",
        {
            "status": "pass" if integrity_ok else "fail",
            "message": integrity_msg,
            "expected_sha256": expected_hash,
        },
    )
    ctx["integrity_ok"] = integrity_ok
    ctx["integrity_evidence"] = [integ_ref]

    # Model validation must be candidate-specific (hash + ONNX check), never inherited
    # solely from the baseline inspection report.
    model_valid = False
    model_msg = "candidate model missing"
    candidate_validation: dict[str, Any] = {}
    if model_path.is_file() and expected_hash:
        actual = sha256_file(model_path)
        hash_ok = actual == expected_hash
        onnx_ok = False
        onnx_msg = "onnx check not run"
        try:
            import onnx

            model = onnx.load(str(model_path))
            onnx.checker.check_model(model)
            onnx_ok = True
            onnx_msg = "onnx.checker.check_model passed"
            inputs = [
                {
                    "name": i.name,
                    "type": str(i.type),
                }
                for i in model.graph.input
            ]
            outputs = [{"name": o.name, "type": str(o.type)} for o in model.graph.output]
            candidate_validation = {
                "sha256": actual,
                "expected_sha256": expected_hash,
                "hash_ok": hash_ok,
                "onnx_ok": onnx_ok,
                "inputs": inputs,
                "outputs": outputs,
                "model_size_bytes": model_path.stat().st_size,
            }
        except Exception as exc:
            onnx_msg = str(exc)
            candidate_validation = {
                "sha256": actual,
                "expected_sha256": expected_hash,
                "hash_ok": hash_ok,
                "onnx_ok": False,
                "message": onnx_msg,
            }
        model_valid = hash_ok and onnx_ok
        model_msg = "candidate validation ok" if model_valid else f"hash_ok={hash_ok}; {onnx_msg}"
    model_ref, _ = _evidence(
        evidence_dir,
        "model_validation",
        {
            "status": "pass" if model_valid else "fail",
            "message": model_msg,
            "candidate_validation": candidate_validation,
            "baseline_inspection_sha256": (model_inspection or {}).get("sha256"),
        },
    )
    ctx["model_valid"] = model_valid
    ctx["model_evidence"] = [model_ref]

    # Host compatibility.
    host_ok = False
    host_msg = "host fingerprint unavailable"
    if host_fingerprint_path and host_fingerprint_path.is_file():
        try:
            host_doc = json.loads(host_fingerprint_path.read_text(encoding="utf-8"))
            host_ok = bool(host_doc)
            host_msg = "host fingerprint present"
        except (OSError, json.JSONDecodeError):
            host_ok = False
            host_msg = "host fingerprint unreadable"
    # When environment is not required, host gate still needs a computed value.
    # Absence is fail for mandatory host gate unless fingerprint exists.
    if not host_ok and not bool(cert_cfg.get("require_valid_environment")):
        # Soft policy: mark compatible when fingerprint intentionally absent and
        # require_valid_environment is false — still record UNAVAILABLE evidence.
        host_ok = True
        host_msg = "host check soft-pass: require_valid_environment=false and no fingerprint"
    host_ref, _ = _evidence(
        evidence_dir,
        "host",
        {"status": "pass" if host_ok else "fail", "message": host_msg},
    )
    ctx["host_compatible"] = host_ok
    ctx["host_evidence"] = [host_ref]

    # Provider registration + optional XNNPACK node-assignment evidence.
    summary = trial.get("summary") or {}
    provider_report = summary.get("provider_report") or {}
    registered = provider_report.get("registered_providers") or []
    requested = (candidate_manifest.get("session") or {}).get("provider_order") or []
    provider_ok = bool(registered) and (not requested or any(p in registered for p in requested))
    # Empty provider report must never certify a production candidate.
    if not registered:
        provider_ok = False

    require_xnnpack = bool(cert_cfg.get("require_xnnpack_assignment"))
    max_cpu_fallback = cert_cfg.get("maximum_cpu_fallback_fraction")
    xnn_fraction = provider_report.get("xnnpack_node_fraction")
    xnn_unavailable = provider_report.get("xnnpack_fraction_unavailable_reason")
    assignment_ok = True
    assignment_reason = None
    if require_xnnpack:
        if xnn_fraction is None:
            assignment_ok = False
            assignment_reason = xnn_unavailable or "UNAVAILABLE_PROVIDER_ASSIGNMENT"
            provider_ok = False
        elif float(xnn_fraction) <= 0.0:
            assignment_ok = False
            assignment_reason = "XNNPACK_ASSIGNMENT_EMPTY"
            provider_ok = False
    if max_cpu_fallback is not None:
        if xnn_fraction is None:
            assignment_ok = False
            assignment_reason = xnn_unavailable or "UNAVAILABLE_PROVIDER_ASSIGNMENT"
            provider_ok = False
        else:
            cpu_fallback = 1.0 - float(xnn_fraction)
            if cpu_fallback > float(max_cpu_fallback):
                assignment_ok = False
                assignment_reason = "CPU_FALLBACK_EXCEEDS_LIMIT"
                provider_ok = False

    provider_ref, _ = _evidence(
        evidence_dir,
        "provider",
        {
            "status": "pass" if provider_ok else "fail",
            "registered_providers": registered,
            "requested": requested,
            "warnings": provider_report.get("warnings") or [],
            "require_xnnpack_assignment": require_xnnpack,
            "maximum_cpu_fallback_fraction": max_cpu_fallback,
            "xnnpack_node_fraction": xnn_fraction,
            "assignment_ok": assignment_ok,
            "assignment_reason": assignment_reason,
            "node_assignment_fraction": {
                "xnnpack": xnn_fraction,
                "status": "pass" if assignment_ok else "fail",
                "reason": assignment_reason,
            },
        },
    )
    ctx["provider_ok"] = provider_ok
    ctx["provider_evidence"] = [provider_ref]
    ctx["provider_assignment"] = registered
    ctx["provider_threshold"] = {
        "require_xnnpack_assignment": require_xnnpack,
        "maximum_cpu_fallback_fraction": max_cpu_fallback,
    }

    # Tensor contract: inspection inputs exist.
    inputs = (model_inspection or {}).get("inputs") or []
    tensor_ok = bool(inputs) or model_valid
    tensor_ref, _ = _evidence(
        evidence_dir,
        "tensor_contract",
        {"status": "pass" if tensor_ok else "fail", "inputs": inputs},
    )
    ctx["tensor_contract_ok"] = tensor_ok
    ctx["tensor_evidence"] = [tensor_ref]

    # Equivalence / quality from evaluation document.
    equivalence_ok = bool(evaluation.get("equivalence_ok", False))
    if evaluation.get("equivalence_status") == "not_required":
        equivalence_ok = True
    equiv_ref, _ = _evidence(
        evidence_dir,
        "equivalence",
        {
            "status": "pass" if equivalence_ok else "fail",
            "equivalence_ok": equivalence_ok,
            "score": evaluation.get("equivalence_score"),
            "evidence": evaluation.get("equivalence_evidence"),
        },
    )
    ctx["equivalence_ok"] = equivalence_ok
    ctx["equivalence_evidence"] = [equiv_ref]
    ctx["equivalence_score"] = evaluation.get("equivalence_score")

    quality_ok = bool(evaluation.get("quality_ok", False))
    quality_ref, _ = _evidence(
        evidence_dir,
        "quality",
        {
            "status": "pass" if quality_ok else "fail",
            "quality_ok": quality_ok,
            "quality_value": evaluation.get("quality_value"),
            "metric": evaluation.get("quality_metric_name"),
            "unavailable_reason": evaluation.get("unavailable_reason"),
            "attestation_ref": evaluation.get("attestation_path"),
        },
    )
    ctx["quality_ok"] = quality_ok
    ctx["quality_evidence"] = [quality_ref]
    ctx["quality_value"] = evaluation.get("quality_value")

    # Peak RSS: measured or UNAVAILABLE.
    peak = trial.get("peak_rss_mb")
    memory_ref, _ = _evidence(
        evidence_dir,
        "memory",
        {
            "status": "pass"
            if peak is not None and float(peak) <= float(ctx["maximum_peak_rss_mb"])
            else "fail",
            "peak_rss_mb": peak,
            "unavailable_reason": None
            if peak is not None
            else trial.get("peak_rss_unavailable_reason") or ReasonCode.UNAVAILABLE_SENSOR,
            "limit_mb": ctx["maximum_peak_rss_mb"],
        },
    )
    ctx["peak_rss_mb"] = peak
    ctx["memory_evidence"] = [memory_ref]

    # Latency from trial stats.
    latency = trial.get("p99_ms")
    if latency is None:
        latency = trial.get("mean_ms")
    latency_ref, _ = _evidence(
        evidence_dir,
        "latency",
        {
            "status": "pass"
            if latency is not None and float(latency) <= float(ctx["deadline_ms"])
            else "fail",
            "latency_ms": latency,
            "deadline_ms": ctx["deadline_ms"],
            "stats": {
                "mean_ms": trial.get("mean_ms"),
                "p50_ms": trial.get("p50_ms"),
                "p99_ms": trial.get("p99_ms"),
                "sample_count": trial.get("sample_count"),
            },
        },
    )
    ctx["latency_ms"] = latency
    ctx["latency_evidence"] = [latency_ref]

    # Environment.
    env_status = environment_status or "invalid"
    env_ref, _ = _evidence(
        evidence_dir,
        "environment",
        {"status": env_status, "require_valid_environment": ctx["require_valid_environment"]},
    )
    ctx["environment_status"] = env_status
    ctx["environment_evidence"] = [env_ref]

    # Warmup from trial/summary.
    warmup_ok = bool(trial.get("warmup_ok", summary.get("status") == "ok"))
    warmup_ref, _ = _evidence(
        evidence_dir,
        "warmup",
        {
            "status": "pass" if warmup_ok else "fail",
            "warmup_ok": warmup_ok,
            "summary_status": summary.get("status"),
        },
    )
    ctx["warmup_ok"] = warmup_ok
    ctx["warmup_evidence"] = [warmup_ref]
    ctx["warmup_iterations_completed"] = trial.get("warmup_iterations")

    # Artifact completeness.
    trial_path = workspace_root / "trials" / f"{candidate_id}.summary.json"
    eval_path = workspace_root / "evaluation" / f"{candidate_id}.json"
    artifacts_ok = trial_path.is_file() and eval_path.is_file() and model_path.is_file()
    art_ref, _ = _evidence(
        evidence_dir,
        "artifacts",
        {
            "status": "pass" if artifacts_ok else "fail",
            "trial": trial_path.is_file(),
            "evaluation": eval_path.is_file(),
            "model": model_path.is_file(),
        },
    )
    ctx["artifacts_complete"] = artifacts_ok
    ctx["artifact_evidence"] = [art_ref]

    return ctx
