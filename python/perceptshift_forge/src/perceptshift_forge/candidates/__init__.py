"""Candidate manifest generation from forge configuration."""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from perceptshift_common.errors import ErrorCode, PerceptShiftError
from perceptshift_common.hashing import sha256_canonical, sha256_file
from perceptshift_common.producer import envelope_fields, utc_now_rfc3339
from perceptshift_common.schema import validate_document
from perceptshift_forge.preprocess import build_canonical_preprocess


@dataclass(slots=True)
class CandidateSpec:
    candidate_id: str
    label: str
    model_path: str
    model_sha256: str
    manifest: dict[str, Any]


def _semantic_payload(
    *,
    model_sha256: str,
    adapter: dict[str, Any],
    preprocess: dict[str, Any],
    session: dict[str, Any],
    lineage: dict[str, Any],
) -> dict[str, Any]:
    return {
        "model_sha256": model_sha256,
        "adapter": adapter,
        "preprocess": preprocess,
        "session": session,
        "lineage": lineage,
    }


def generate_candidates(
    forge_config: dict[str, Any],
    *,
    baseline_model_path: Path,
    quantized_models: list[dict[str, Any]] | None = None,
    maximum_candidates: int = 256,
    dataset_manifest: dict[str, Any] | None = None,
) -> list[CandidateSpec]:
    if not baseline_model_path.is_file():
        raise PerceptShiftError(
            code=ErrorCode.MODEL_INVALID,
            message=f"Baseline model missing: {baseline_model_path}",
        )
    baseline_hash = sha256_file(baseline_model_path)
    cfg = forge_config.get("candidates") or {}
    model_cfg = forge_config.get("model") or {}
    adapter = {
        "name": model_cfg.get("adapter"),
        "config": model_cfg.get("adapter_config") or {},
        "config_hash": sha256_canonical(model_cfg.get("adapter_config") or {}),
    }

    models: list[dict[str, Any]] = []
    if cfg.get("include_baseline", True):
        models.append(
            {
                "label": "baseline",
                "model_path": "models/baseline/model.onnx",
                "model_sha256": baseline_hash,
                "lineage": {"transformation": "baseline", "parent_sha256": baseline_hash},
            }
        )
    for variant in cfg.get("user_model_variants") or []:
        models.append(
            {
                "label": str(variant.get("label", "user_variant")),
                "model_path": str(variant.get("model_path")),
                "model_sha256": str(variant.get("model_sha256", "")),
                "lineage": {
                    "transformation": "user_variant",
                    "parent_sha256": baseline_hash,
                    "variant": variant,
                },
            }
        )
    for quantized in quantized_models or []:
        models.append(quantized)

    providers = cfg.get("execution_providers") or [
        {
            "name": "cpu",
            "provider_order": ["CPUExecutionProvider"],
        }
    ]
    xnnpack_threads = cfg.get("xnnpack_thread_counts") or [None]
    intra = cfg.get("ort_intra_op_thread_counts") or [1]
    inter = cfg.get("ort_inter_op_thread_counts") or [1]
    spinning = cfg.get("allow_intra_op_spinning") or [False]
    graph_levels = cfg.get("graph_optimization_levels") or ["all"]
    backends = cfg.get("preprocess_backends") or ["scalar"]
    input_variants = cfg.get("input_variants") or [{}]

    cartesian = list(
        itertools.product(
            models,
            providers,
            xnnpack_threads,
            intra,
            inter,
            spinning,
            graph_levels,
            backends,
            input_variants,
        )
    )
    if len(cartesian) > maximum_candidates:
        raise PerceptShiftError(
            code=ErrorCode.CONFIG_INVALID,
            message=(
                f"Candidate cartesian product size {len(cartesian)} exceeds "
                f"maximum_candidates={maximum_candidates}"
            ),
            remediation="Narrow candidate dimensions or raise the override deliberately",
            details={"estimated_candidates": len(cartesian)},
        )

    specs: list[CandidateSpec] = []
    seen: set[str] = set()
    for (
        model,
        provider,
        xnn_threads,
        intra_n,
        inter_n,
        spin,
        graph_level,
        backend,
        input_variant,
    ) in cartesian:
        session = {
            "provider_order": list(provider.get("provider_order") or []),
            "provider_name": provider.get("name"),
            "intra_op_threads": int(intra_n),
            "inter_op_threads": int(inter_n),
            "allow_intra_op_spinning": bool(spin),
            "graph_optimization_level": graph_level,
            "xnnpack_threads": xnn_threads,
        }
        variant = input_variant if isinstance(input_variant, dict) else {}
        preprocess = build_canonical_preprocess(
            forge_config=forge_config,
            dataset_manifest=dataset_manifest,
            backend=str(backend),
            input_variant=variant,
        )
        semantic = _semantic_payload(
            model_sha256=str(model["model_sha256"]),
            adapter=adapter,
            preprocess=preprocess,
            session=session,
            lineage=model.get("lineage") or {},
        )
        candidate_id = sha256_canonical(semantic)[:32]
        if candidate_id in seen:
            continue
        seen.add(candidate_id)
        manifest = envelope_fields(document_type="perceptshift.candidate_manifest")
        manifest.update(
            {
                "candidate_id": candidate_id,
                "label": f"{model['label']}/{provider.get('name')}/{backend}",
                "model_path": model["model_path"],
                "model_sha256": model["model_sha256"],
                "adapter": adapter,
                "preprocess": preprocess,
                "session": {
                    "provider_order": session["provider_order"],
                    "intra_op_threads": session["intra_op_threads"],
                    "inter_op_threads": session["inter_op_threads"],
                    "allow_intra_op_spinning": session["allow_intra_op_spinning"],
                    "graph_optimization_level": session["graph_optimization_level"],
                    "xnnpack_threads": session["xnnpack_threads"],
                },
                "provenance": {
                    "parent_baseline_model_hash": baseline_hash,
                    "lineage": model.get("lineage") or {},
                    "created_at": utc_now_rfc3339(),
                },
            }
        )
        validate_document(manifest, "candidate_manifest")
        specs.append(
            CandidateSpec(
                candidate_id=candidate_id,
                label=str(manifest["label"]),
                model_path=str(manifest["model_path"]),
                model_sha256=str(manifest["model_sha256"]),
                manifest=manifest,
            )
        )
    return specs
