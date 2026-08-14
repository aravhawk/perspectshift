"""Forge run workspace orchestration, resume, and bench worker launch."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from perceptshift_common.errors import ErrorCode, PerceptShiftError
from perceptshift_common.hashing import (
    sha256_canonical,
    sha256_file,
    write_atomic_json,
    write_atomic_text,
)
from perceptshift_common.producer import envelope_fields, producer_metadata, utc_now_rfc3339
from perceptshift_common.schema import load_config_document, validate_document
from perceptshift_common.version import get_version
from perceptshift_forge.bundle import sign_bundle
from perceptshift_forge.candidates import generate_candidates
from perceptshift_forge.certification import (
    build_certification_context,
    is_certified,
    pareto_select,
    run_certification_gates,
)
from perceptshift_forge.datasets import assert_split_isolation
from perceptshift_forge.datasets.stream import build_benchmark_stream
from perceptshift_forge.datasets.validate import validate_dataset_manifest
from perceptshift_forge.models.inspect import inspect_onnx_model
from perceptshift_forge.orchestration.environment import capture_environment
from perceptshift_forge.orchestration.evaluate import evaluate_candidate_quality
from perceptshift_forge.orchestration.quantize_step import run_quantization_variants
from perceptshift_forge.runs.storage import index_run
from perceptshift_forge.statistics import summarize_latencies

_RUN_ID_SAFE = re.compile(r"[^a-zA-Z0-9_-]+")


def make_run_id(project_name: str) -> str:
    """Sortable unique ID: UUIDv7-like time component + sanitized project label."""
    # UUIDv7-compatible: use uuid4 for uniqueness plus millisecond prefix for sortability.
    millis = int(time.time() * 1000)
    unique = uuid.uuid4().hex[:10]
    label = _RUN_ID_SAFE.sub("-", project_name.strip().lower())[:24] or "project"
    return f"{millis:013d}-{unique}-{label}"


@dataclass(slots=True)
class RunWorkspace:
    run_id: str
    root: Path
    config: dict[str, Any]
    config_hash: str


def _workspace_dirs(root: Path) -> dict[str, Path]:
    return {
        "environment": root / "environment",
        "inputs": root / "inputs",
        "models": root / "models",
        "candidates": root / "candidates",
        "trials": root / "trials",
        "evaluation": root / "evaluation",
        "certification": root / "certification",
        "bundle": root / "bundle",
        "reports": root / "reports",
        "logs": root / "logs",
    }


def create_run_workspace(config_path: Path) -> RunWorkspace:
    config = validate_document(load_config_document(config_path), "forge_config")
    project = config["project"]
    output_root = Path(project["output_root"])
    if not output_root.is_absolute():
        raise PerceptShiftError(
            code=ErrorCode.PATH_UNSAFE,
            message="project.output_root must be absolute",
        )
    run_id = make_run_id(str(project["name"]))
    root = output_root / run_id
    if root.exists():
        raise PerceptShiftError(
            code=ErrorCode.INTERNAL_INVARIANT_FAILED,
            message=f"Run workspace already exists: {root}",
        )
    root.mkdir(parents=True, mode=0o750)
    for path in _workspace_dirs(root).values():
        path.mkdir(parents=True, exist_ok=True)
    (root / "models" / "baseline").mkdir(exist_ok=True)
    (root / "models" / "optimized").mkdir(exist_ok=True)
    (root / "models" / "quantized").mkdir(exist_ok=True)
    (root / "candidates" / "manifests").mkdir(exist_ok=True)
    (root / "candidates" / "status").mkdir(exist_ok=True)

    config_hash = sha256_canonical(config)
    write_atomic_json(root / "inputs" / "config.canonical.json", config)
    run_doc = envelope_fields(document_type="perceptshift.forge_run")
    run_doc.update(
        {
            "run_id": run_id,
            "status": "created",
            "config_hash": config_hash,
            "product_version": get_version(),
            "config_path": str(config_path.resolve()),
        }
    )
    write_atomic_json(root / "run.json", run_doc)
    _acquire_lock(root)
    return RunWorkspace(run_id=run_id, root=root, config=config, config_hash=config_hash)


def _acquire_lock(root: Path) -> None:
    lock_path = root / "run.lock"
    if lock_path.exists():
        try:
            existing = json.loads(lock_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = {}
        pid = existing.get("pid")
        if isinstance(pid, int) and _pid_alive(pid):
            raise PerceptShiftError(
                code=ErrorCode.RUN_LOCK_HELD,
                message=f"Run lock held by pid {pid}",
                details={"lock": str(lock_path)},
            )
    payload = {
        "pid": os.getpid(),
        "created_at": utc_now_rfc3339(),
        "hostname_hash": sha256_canonical(os.uname().nodename)[:16],
    }
    write_atomic_json(lock_path, payload)


def _release_lock(root: Path) -> None:
    lock_path = root / "run.lock"
    if lock_path.exists():
        lock_path.unlink()


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def load_run_workspace(run_root: Path) -> RunWorkspace:
    run_json = run_root / "run.json"
    if not run_json.is_file():
        raise PerceptShiftError(
            code=ErrorCode.NOT_FOUND,
            message=f"run.json missing under {run_root}",
        )
    run_doc = json.loads(run_json.read_text(encoding="utf-8"))
    config = json.loads((run_root / "inputs" / "config.canonical.json").read_text(encoding="utf-8"))
    return RunWorkspace(
        run_id=str(run_doc["run_id"]),
        root=run_root,
        config=config,
        config_hash=str(run_doc["config_hash"]),
    )


def run_forge(config_path: Path, *, maximum_candidates: int = 256) -> dict[str, Any]:
    workspace = create_run_workspace(config_path)
    try:
        return _execute_run(workspace, maximum_candidates=maximum_candidates, resume=False)
    finally:
        _release_lock(workspace.root)


def resume_forge(run_root: Path, *, maximum_candidates: int = 256) -> dict[str, Any]:
    workspace = load_run_workspace(run_root)
    _acquire_lock(workspace.root)
    try:
        return _execute_run(workspace, maximum_candidates=maximum_candidates, resume=True)
    finally:
        _release_lock(workspace.root)


def _execute_run(
    workspace: RunWorkspace,
    *,
    maximum_candidates: int,
    resume: bool,
) -> dict[str, Any]:
    config = workspace.config
    status_path = workspace.root / "candidates" / "status" / "pipeline.json"
    status: dict[str, Any]
    if resume and status_path.is_file():
        status = json.loads(status_path.read_text(encoding="utf-8"))
        if status.get("config_hash") != workspace.config_hash:
            raise PerceptShiftError(
                code=ErrorCode.RUN_RESUME_INVALID,
                message="Config hash mismatch on resume",
            )
        if status.get("product_version") != get_version():
            raise PerceptShiftError(
                code=ErrorCode.RUN_RESUME_INVALID,
                message="Product version mismatch on resume",
                remediation="Supply an explicit incompatible-resume override in a future revision",
            )
    else:
        status = {
            "config_hash": workspace.config_hash,
            "product_version": get_version(),
            "steps": {},
        }

    def step_done(name: str) -> bool:
        return bool(status.get("steps", {}).get(name, {}).get("completed"))

    def mark(name: str, payload: dict[str, Any]) -> None:
        status.setdefault("steps", {})[name] = {
            "completed": True,
            "completed_at": utc_now_rfc3339(),
            **payload,
        }
        write_atomic_json(status_path, status)

    cert_cfg_early = config.get("certification") or {}
    if not step_done("environment"):
        env_doc = capture_environment(
            workspace_root=workspace.root,
            require_valid=bool(cert_cfg_early.get("require_valid_environment", True)),
        )
        mark("environment", {"status": env_doc.get("status")})

    # Validate datasets
    if not step_done("datasets"):
        cal = validate_dataset_manifest(Path(config["datasets"]["calibration_manifest"]))
        ev = validate_dataset_manifest(Path(config["datasets"]["evaluation_manifest"]))
        if not cal.ok or not ev.ok:
            raise PerceptShiftError(
                code=ErrorCode.DATASET_INVALID,
                message="Dataset validation failed",
                details={"calibration_errors": cal.errors, "evaluation_errors": ev.errors},
            )
        assert_split_isolation(
            cal,
            ev,
            prohibit_duplicates=bool(config["datasets"]["prohibit_cross_split_duplicates"]),
        )
        write_atomic_json(workspace.root / "inputs" / "calibration-manifest.json", cal.manifest)
        write_atomic_json(workspace.root / "inputs" / "evaluation-manifest.json", ev.manifest)
        mark(
            "datasets",
            {
                "calibration_hash": cal.manifest_hash,
                "evaluation_hash": ev.manifest_hash,
            },
        )

    # Inspect and copy baseline model
    baseline_src = Path(config["model"]["baseline_path"])
    baseline_dst = workspace.root / "models" / "baseline" / "model.onnx"
    inspection_report: dict[str, Any]
    if not step_done("model"):
        inspection = inspect_onnx_model(baseline_src)
        if not baseline_dst.exists():
            shutil.copy2(baseline_src, baseline_dst)
        write_atomic_json(workspace.root / "inputs" / "model-manifest.json", inspection.report)
        mark("model", {"model_sha256": inspection.sha256})
        inspection_report = inspection.report
    else:
        inspection_report = json.loads(
            (workspace.root / "inputs" / "model-manifest.json").read_text(encoding="utf-8")
        )

    cal_manifest = json.loads(
        (workspace.root / "inputs" / "calibration-manifest.json").read_text(encoding="utf-8")
    )
    ev_manifest = json.loads(
        (workspace.root / "inputs" / "evaluation-manifest.json").read_text(encoding="utf-8")
    )
    cal_hash = str(status.get("steps", {}).get("datasets", {}).get("calibration_hash") or "")
    ev_hash = str(status.get("steps", {}).get("datasets", {}).get("evaluation_hash") or "")

    # Materialize real dataset stream for the native worker (never synthetic-only).
    dataset_stream = workspace.root / "inputs" / "bench-stream.json"
    if not step_done("dataset_stream"):
        expected_input = dict((config.get("model") or {}).get("expected_input") or {})
        if not expected_input.get("shape") and inspection_report.get("inputs"):
            shape = inspection_report["inputs"][0].get("shape")
            if shape:
                expected_input["shape"] = [
                    int(d) if isinstance(d, int) and d > 0 else 1 for d in shape
                ]
        measured = int((config.get("benchmark") or {}).get("measured_iterations") or 1)
        build_benchmark_stream(
            workspace_root=workspace.root,
            calibration_manifest=cal_manifest,
            evaluation_manifest=ev_manifest,
            expected_input=expected_input,
            measured_iterations=measured,
        )
        stream_doc = json.loads(dataset_stream.read_text(encoding="utf-8"))
        if "synthetic_float_samples" in stream_doc and "samples" not in stream_doc:
            raise PerceptShiftError(
                code=ErrorCode.INTERNAL_INVARIANT_FAILED,
                message="Production bench stream must not be synthetic_float_samples-only",
            )
        mark("dataset_stream", {"sample_count": stream_doc.get("sample_count")})

    # Quantization variants (calibration split only).
    quantized_models: list[dict[str, Any]] = []
    if not step_done("quantization"):
        quantized_models = run_quantization_variants(
            workspace_root=workspace.root,
            config=config,
            baseline_model_path=baseline_dst,
            calibration_manifest_path=Path(config["datasets"]["calibration_manifest"]),
            stream_path=dataset_stream,
            model_inspection=inspection_report,
        )
        mark("quantization", {"count": len(quantized_models)})
    else:
        for report_path in sorted((workspace.root / "models" / "quantized").glob("*.report.json")):
            report = json.loads(report_path.read_text(encoding="utf-8"))
            label = report_path.stem.replace(".report", "")
            quantized_models.append(
                {
                    "label": label,
                    "model_path": f"models/quantized/{Path(report['output_path']).name}",
                    "model_sha256": report["model_sha256"],
                    "lineage": {"transformation": "static_qdq", "label": label},
                }
            )

    # Generate candidates including quantized artifacts.
    if not step_done("candidates"):
        specs = generate_candidates(
            config,
            baseline_model_path=baseline_dst,
            quantized_models=quantized_models,
            maximum_candidates=maximum_candidates,
            dataset_manifest=cal_manifest,
        )
        for spec in specs:
            abs_model = workspace.root / spec.manifest.get(
                "model_path", "models/baseline/model.onnx"
            )
            if not abs_model.is_file() and Path(spec.model_path).is_file():
                abs_model = Path(spec.model_path)
            manifest = dict(spec.manifest)
            manifest["model_absolute_path"] = str(abs_model.resolve())
            write_atomic_json(
                workspace.root / "candidates" / "manifests" / f"{spec.candidate_id}.json",
                manifest,
            )
            write_atomic_json(
                workspace.root / "candidates" / "status" / f"{spec.candidate_id}.json",
                {"candidate_id": spec.candidate_id, "status": "generated"},
            )
        mark("candidates", {"count": len(specs)})

    # Benchmark candidates via native worker (shell-free).
    certified_rows: list[dict[str, Any]] = []
    if not step_done("benchmarking"):
        worker = find_native_binary("perceptshift-bench-worker")
        if worker is None:
            raise PerceptShiftError(
                code=ErrorCode.BENCHMARK_WORKER_CRASHED,
                message="perceptshift-bench-worker not found on PATH or under build/",
                remediation=(
                    "Build the ORT-enabled native targets and ensure the "
                    "hyphenated binary is discoverable"
                ),
            )
        manifests_dir = workspace.root / "candidates" / "manifests"
        bench_cfg = config.get("benchmark") or {}
        timeout = float(bench_cfg.get("per_candidate_timeout_seconds") or 60)
        warmup = int(bench_cfg.get("warmup_iterations") or 1)
        measured = int(bench_cfg.get("measured_iterations") or 1)
        cold_start_trials = int(bench_cfg.get("cold_start_trials") or 0)
        max_worker_rss = bench_cfg.get("maximum_worker_rss_mb")
        randomize = bool(bench_cfg.get("randomize_candidate_order"))
        seed = int(config.get("project", {}).get("random_seed") or 0)
        require_no_throttling = bool(bench_cfg.get("require_no_throttling"))
        max_start_temp = bench_cfg.get("maximum_start_temperature_c")
        max_temp_drift = bench_cfg.get("maximum_temperature_drift_c")

        host_fp_path = workspace.root / "environment" / "host-fingerprint.json"
        host_fp = (
            json.loads(host_fp_path.read_text(encoding="utf-8")) if host_fp_path.is_file() else {}
        )
        thermal = host_fp.get("thermal") or {}
        throttling = host_fp.get("throttling") or {}
        start_temp = thermal.get("primary_celsius")
        if max_start_temp is not None:
            if start_temp is None:
                raise PerceptShiftError(
                    code=ErrorCode.BENCHMARK_ENVIRONMENT_INVALID,
                    message=(
                        "maximum_start_temperature_c configured but thermal sensor unavailable; "
                        "environment validity fails closed"
                    ),
                    details={"thermal": thermal},
                )
            if float(start_temp) > float(max_start_temp):
                raise PerceptShiftError(
                    code=ErrorCode.BENCHMARK_ENVIRONMENT_INVALID,
                    message=(
                        f"Start temperature {start_temp}C exceeds maximum_start_temperature_c "
                        f"{max_start_temp}"
                    ),
                )
        if require_no_throttling:
            if throttling.get("active") is None:
                raise PerceptShiftError(
                    code=ErrorCode.BENCHMARK_ENVIRONMENT_INVALID,
                    message=(
                        "require_no_throttling=true but throttling evidence unavailable; "
                        "do not claim not-throttled"
                    ),
                    details={"throttling": throttling},
                )
            if throttling.get("active") is True:
                raise PerceptShiftError(
                    code=ErrorCode.BENCHMARK_ENVIRONMENT_INVALID,
                    message="Host reports thermal throttling while require_no_throttling=true",
                )

        man_paths = sorted(manifests_dir.glob("*.json"))
        if randomize:
            import random

            rng = random.Random(seed)
            rng.shuffle(man_paths)
            write_atomic_json(
                workspace.root / "trials" / "candidate_order.json",
                {
                    "randomize_candidate_order": True,
                    "seed": seed,
                    "order": [p.stem for p in man_paths],
                },
            )
        else:
            write_atomic_json(
                workspace.root / "trials" / "candidate_order.json",
                {
                    "randomize_candidate_order": False,
                    "seed": seed,
                    "order": [p.stem for p in man_paths],
                },
            )

        for man_path in man_paths:
            man = json.loads(man_path.read_text(encoding="utf-8"))
            cand_id = str(man.get("candidate_id") or man_path.stem)
            stdout_path = workspace.root / "trials" / f"{cand_id}.jsonl"
            stderr_path = workspace.root / "logs" / f"{cand_id}.stderr"
            stdout_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                # Cold-start trials: independent fresh processes with zero warmup.
                for cold_idx in range(max(0, cold_start_trials)):
                    cold_stdout = workspace.root / "trials" / f"{cand_id}.cold{cold_idx}.jsonl"
                    cold_stderr = workspace.root / "logs" / f"{cand_id}.cold{cold_idx}.stderr"
                    launch_bench_worker(
                        worker_argv=[
                            str(worker),
                            "--candidate",
                            str(man_path),
                            "--dataset",
                            str(dataset_stream),
                            "--warmup",
                            "0",
                            "--measured",
                            "1",
                        ],
                        cwd=workspace.root,
                        timeout_seconds=timeout,
                        stdout_path=cold_stdout,
                        stderr_path=cold_stderr,
                    )
                worker_result = launch_bench_worker(
                    worker_argv=[
                        str(worker),
                        "--candidate",
                        str(man_path),
                        "--dataset",
                        str(dataset_stream),
                        "--warmup",
                        str(warmup),
                        "--measured",
                        str(measured),
                    ],
                    cwd=workspace.root,
                    timeout_seconds=timeout,
                    stdout_path=stdout_path,
                    stderr_path=stderr_path,
                )
                lines = [
                    json.loads(line)
                    for line in stdout_path.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]
                if not lines:
                    raise PerceptShiftError(
                        code=ErrorCode.BENCHMARK_WORKER_CRASHED,
                        message=f"Bench worker produced no JSONL for {cand_id}",
                    )
                summary = next(
                    (
                        x
                        for x in lines
                        if x.get("document_type") == "perceptshift.bench_worker_summary"
                    ),
                    None,
                )

                # Primary certification latency is complete executor path
                # (preprocess + ORT + postprocess), never inference-only.
                sample_ms: list[float] = []
                missing_executor = False
                for x in lines:
                    if not isinstance(x, dict) or "document_type" in x:
                        continue
                    if "executor_ms" in x:
                        sample_ms.append(float(x["executor_ms"]))
                    elif "inference_ms" in x:
                        missing_executor = True
                if not sample_ms and summary and isinstance(summary.get("samples"), list):
                    for s in summary["samples"]:
                        if isinstance(s, dict) and "executor_ms" in s:
                            sample_ms.append(float(s["executor_ms"]))
                        elif isinstance(s, dict) and "inference_ms" in s:
                            missing_executor = True
                if not sample_ms:
                    raise PerceptShiftError(
                        code=ErrorCode.BENCHMARK_WORKER_CRASHED,
                        message=(
                            f"Bench worker for {cand_id} did not report executor_ms; "
                            "certification fails closed rather than substituting inference_ms"
                        ),
                        details={"missing_executor_timing": missing_executor},
                    )
                stats = summarize_latencies(
                    sample_ms,
                    bootstrap_resamples=int(bench_cfg.get("bootstrap_resamples") or 100),
                    seed=int(config.get("project", {}).get("random_seed") or 0),
                )
                # Prefer worker-reported peak RSS over cumulative RUSAGE_CHILDREN.
                peak_rss_mb = None
                if summary and summary.get("peak_rss_mb") is not None:
                    peak_rss_mb = float(summary["peak_rss_mb"])
                if peak_rss_mb is None:
                    peak_rss_mb = worker_result.get("peak_rss_mb")
                trial = {
                    "candidate_id": cand_id,
                    "status": "measured",
                    "latency_definition": "profile_executor_complete",
                    "mean_ms": stats.mean,
                    "p50_ms": stats.p50,
                    "p99_ms": stats.p99,
                    "sample_count": len(sample_ms),
                    "summary": summary,
                    "warmup_ok": True,
                    "warmup_iterations": warmup,
                    "peak_rss_mb": peak_rss_mb,
                    "peak_rss_unavailable_reason": None
                    if peak_rss_mb is not None
                    else worker_result.get("peak_rss_unavailable_reason"),
                    "peak_rss_method": (
                        "worker_self_report"
                        if summary and summary.get("peak_rss_mb") is not None
                        else worker_result.get("peak_rss_method")
                    ),
                    "stats": stats.to_dict(),
                }
                write_atomic_json(workspace.root / "trials" / f"{cand_id}.summary.json", trial)
                if max_worker_rss is not None and peak_rss_mb is not None:
                    if float(peak_rss_mb) > float(max_worker_rss):
                        raise PerceptShiftError(
                            code=ErrorCode.RESOURCE_EXHAUSTED,
                            message=(
                                f"Candidate {cand_id} peak_rss_mb={peak_rss_mb} exceeds "
                                f"maximum_worker_rss_mb={max_worker_rss}"
                            ),
                            details={
                                "candidate_id": cand_id,
                                "peak_rss_mb": peak_rss_mb,
                                "maximum_worker_rss_mb": max_worker_rss,
                            },
                        )
                if max_temp_drift is not None and start_temp is not None:
                    # Re-read thermal after candidate for drift enforcement.
                    capture_environment(
                        workspace_root=workspace.root,
                        require_valid=bool(
                            (config.get("certification") or {}).get("require_valid_environment")
                        ),
                    )
                    host_fp2 = json.loads(host_fp_path.read_text(encoding="utf-8"))
                    end_temp = (host_fp2.get("thermal") or {}).get("primary_celsius")
                    if end_temp is None:
                        raise PerceptShiftError(
                            code=ErrorCode.BENCHMARK_ENVIRONMENT_INVALID,
                            message=(
                                "maximum_temperature_drift_c configured but end thermal unavailable"
                            ),
                        )
                    if abs(float(end_temp) - float(start_temp)) > float(max_temp_drift):
                        raise PerceptShiftError(
                            code=ErrorCode.BENCHMARK_ENVIRONMENT_INVALID,
                            message=(
                                f"Temperature drift {abs(float(end_temp) - float(start_temp))}C "
                                f"exceeds maximum_temperature_drift_c={max_temp_drift}"
                            ),
                        )
                # Persist production-equivalent normalized outputs for quality evaluation.
                (workspace.root / "evaluation").mkdir(parents=True, exist_ok=True)
                if summary and isinstance(summary.get("detections"), list):
                    write_atomic_json(
                        workspace.root / "evaluation" / f"{cand_id}.detections.json",
                        {
                            "candidate_id": cand_id,
                            "source": "perceptshift-bench-worker",
                            "detections": summary["detections"],
                        },
                    )
                sample_rows = []
                if summary and isinstance(summary.get("samples"), list):
                    sample_rows = summary["samples"]
                elif lines:
                    sample_rows = [
                        x
                        for x in lines
                        if isinstance(x, dict) and "sample_id" in x and "document_type" not in x
                    ]
                if sample_rows:
                    write_atomic_json(
                        workspace.root / "evaluation" / f"{cand_id}.native_outputs.json",
                        {
                            "candidate_id": cand_id,
                            "source": "perceptshift-bench-worker",
                            "samples": sample_rows,
                        },
                    )
                write_atomic_json(
                    workspace.root / "candidates" / "status" / f"{cand_id}.json",
                    {"candidate_id": cand_id, "status": "measured"},
                )
            except PerceptShiftError as exc:
                write_atomic_json(
                    workspace.root / "candidates" / "status" / f"{cand_id}.json",
                    {
                        "candidate_id": cand_id,
                        "status": "failed",
                        "error": {"code": exc.code.value, "message": exc.message},
                    },
                )
                raise
        mark("benchmarking", {"worker": str(worker)})

    if not step_done("evaluating_quality"):
        for status_file in sorted((workspace.root / "candidates" / "status").glob("*.json")):
            if status_file.name == "pipeline.json":
                continue
            st = json.loads(status_file.read_text(encoding="utf-8"))
            if st.get("status") != "measured":
                continue
            cand_id = st["candidate_id"]
            trial = json.loads(
                (workspace.root / "trials" / f"{cand_id}.summary.json").read_text(encoding="utf-8")
            )
            man = json.loads(
                (workspace.root / "candidates" / "manifests" / f"{cand_id}.json").read_text(
                    encoding="utf-8"
                )
            )
            eval_doc = evaluate_candidate_quality(
                workspace_root=workspace.root,
                config=config,
                candidate_id=cand_id,
                candidate_manifest=man,
                baseline_model_path=baseline_dst,
                evaluation_manifest=ev_manifest,
                evaluation_manifest_hash=ev_hash or sha256_canonical(ev_manifest),
                stream_path=dataset_stream,
            )
            write_atomic_json(workspace.root / "evaluation" / f"{cand_id}.json", eval_doc)
            trial["quality_ok"] = eval_doc.get("quality_ok")
            trial["quality_value"] = eval_doc.get("quality_value")
            trial["equivalence_ok"] = eval_doc.get("equivalence_ok")
            write_atomic_json(workspace.root / "trials" / f"{cand_id}.summary.json", trial)
        mark("evaluating_quality", {})

    if not step_done("certifying"):
        cert_cfg = config.get("certification") or {}
        env_path = workspace.root / "environment" / "status.json"
        environment_status = "valid"
        if env_path.is_file():
            environment_status = str(
                json.loads(env_path.read_text(encoding="utf-8")).get("status") or "invalid"
            )
        elif bool(cert_cfg.get("require_valid_environment")):
            environment_status = "invalid"
        else:
            environment_status = "valid_with_warnings"
            write_atomic_json(
                env_path,
                {
                    "status": environment_status,
                    "message": (
                        "No environment snapshot; soft-pass because require_valid_environment=false"
                    ),
                },
            )
        host_fp = workspace.root / "environment" / "host-fingerprint.json"
        for trial_path in sorted((workspace.root / "trials").glob("*.summary.json")):
            trial = json.loads(trial_path.read_text(encoding="utf-8"))
            cand_id = trial["candidate_id"]
            eval_doc = json.loads(
                (workspace.root / "evaluation" / f"{cand_id}.json").read_text(encoding="utf-8")
            )
            man = json.loads(
                (workspace.root / "candidates" / "manifests" / f"{cand_id}.json").read_text(
                    encoding="utf-8"
                )
            )
            ctx = build_certification_context(
                workspace_root=workspace.root,
                candidate_id=cand_id,
                candidate_manifest=man,
                trial=trial,
                evaluation=eval_doc,
                model_inspection=inspection_report,
                cert_cfg=cert_cfg,
                environment_status=environment_status,
                host_fingerprint_path=host_fp if host_fp.is_file() else None,
            )
            results = run_certification_gates(ctx)
            certified = is_certified(results)
            quality_for_pareto = eval_doc.get("quality_value")
            if quality_for_pareto is None and eval_doc.get("quality_status") == "not_applicable":
                quality_for_pareto = eval_doc.get("equivalence_score")
            row = {
                "candidate_id": cand_id,
                "certified": certified,
                "quality": quality_for_pareto,
                "p99_latency_ms": trial.get("p99_ms"),
                "peak_rss_mb": trial.get("peak_rss_mb"),
                "gates": [r.to_dict() for r in results],
                "evidence_root": f"certification/evidence/{cand_id}",
            }
            write_atomic_json(workspace.root / "certification" / f"{cand_id}.json", row)
            certified_rows.append(row)
        mark("certifying", {"count": len(certified_rows)})
    else:
        for path in sorted((workspace.root / "certification").glob("*.json")):
            if path.name == "frontier.json":
                continue
            if path.is_dir():
                continue
            certified_rows.append(json.loads(path.read_text(encoding="utf-8")))

    if not step_done("selecting_frontier"):
        frontier = pareto_select(certified_rows)
        write_atomic_json(
            workspace.root / "certification" / "frontier.json",
            {"frontier": frontier, "count": len(frontier)},
        )
        mark("selecting_frontier", {"count": len(frontier)})
    else:
        frontier = json.loads(
            (workspace.root / "certification" / "frontier.json").read_text(encoding="utf-8")
        ).get("frontier", [])

    if not step_done("building_bundle"):
        if not frontier:
            raise PerceptShiftError(
                code=ErrorCode.QUALITY_GATE_FAILED,
                message="No certified candidates available for bundle creation",
            )
        bundle_root = workspace.root / "bundle" / "profile-bundle"
        bundle_root.mkdir(parents=True, exist_ok=True)
        (bundle_root / "models").mkdir(exist_ok=True)
        (bundle_root / "profiles").mkdir(exist_ok=True)
        (bundle_root / "attestations").mkdir(exist_ok=True)
        files: list[dict[str, Any]] = []
        profiles: list[dict[str, Any]] = []

        def _inventory(rel: str) -> None:
            target = bundle_root / rel
            if Path(rel).is_absolute() or ".." in Path(rel).parts:
                raise PerceptShiftError(
                    code=ErrorCode.PATH_UNSAFE,
                    message=f"Bundle inventory path must be relative: {rel}",
                )
            files.append(
                {
                    "path": rel,
                    "sha256": sha256_file(target),
                    "size_bytes": target.stat().st_size,
                }
            )

        for item in frontier:
            cand_id = str(item["candidate_id"])
            man = json.loads(
                (workspace.root / "candidates" / "manifests" / f"{cand_id}.json").read_text(
                    encoding="utf-8"
                )
            )
            src = Path(man["model_absolute_path"])
            rel_model = f"models/{cand_id}.onnx"
            dst = bundle_root / rel_model
            shutil.copy2(src, dst)
            model_hash = sha256_file(dst)
            attestation_src = workspace.root / "evaluation" / f"{cand_id}.attestation.json"
            quality_attestation_ref = None
            if attestation_src.is_file():
                rel_att = f"attestations/{cand_id}.quality.json"
                shutil.copy2(attestation_src, bundle_root / rel_att)
                quality_attestation_ref = rel_att
                _inventory(rel_att)
            cert_src = workspace.root / "certification" / f"{cand_id}.json"
            if cert_src.is_file():
                rel_cert = f"attestations/{cand_id}.certification.json"
                shutil.copy2(cert_src, bundle_root / rel_cert)
                _inventory(rel_cert)
            profile = {
                "profile_id": cand_id,
                "label": man.get("label", cand_id),
                "model_sha256": model_hash,
                "model_relative_path": rel_model,
                "model_size_bytes": dst.stat().st_size,
                "status": "certified",
                "session": man.get("session")
                or {"provider_order": ["CPUExecutionProvider"], "intra_op_threads": 1},
                "adapter": man.get("adapter") or {"name": config["model"]["adapter"]},
                "preprocess": man.get("preprocess") or {"backend": "scalar"},
                "latency_summary": {
                    "p99_ms": item.get("p99_latency_ms"),
                },
                "peak_rss_summary": {
                    "peak_rss_mb": item.get("peak_rss_mb"),
                },
            }
            if quality_attestation_ref:
                profile["quality_attestation_ref"] = quality_attestation_ref
            write_atomic_json(bundle_root / "profiles" / f"{cand_id}.json", profile)
            profiles.append(profile)
            _inventory(rel_model)
            _inventory(f"profiles/{cand_id}.json")
        write_atomic_text(bundle_root / "NOTICE", "PerceptShift certified profile bundle\n")
        _inventory("NOTICE")
        quality_metric = (config.get("quality") or {}).get("metric_name")
        if (config.get("model") or {}).get("adapter") == "raw_tensor":
            quality_metric = "numeric_equivalence"
        manifest = envelope_fields(document_type="perceptshift.profile_bundle")
        manifest.update(
            {
                "bundle_id": f"bundle-{workspace.run_id}",
                "product_version": get_version(),
                "minimum_compatible_runtime_version": "0.1.0",
                "producer": producer_metadata(),
                "created_at": utc_now_rfc3339(),
                "adapter": {"name": config["model"]["adapter"]},
                "quality_metric_name": quality_metric,
                "quality_direction": (config.get("quality") or {}).get("direction")
                or "higher_is_better",
                "calibration_dataset_hash": cal_hash or None,
                "evaluation_dataset_hash": ev_hash or None,
                "profiles": profiles,
                "files": files,
            }
        )
        write_atomic_json(bundle_root / "manifest.json", manifest)
        write_atomic_text(
            bundle_root / "manifest.sha256",
            sha256_file(bundle_root / "manifest.json") + "\n",
        )
        cert_cfg = config.get("certification") or {}
        if cert_cfg.get("sign_bundle") and cert_cfg.get("signing_key_path"):
            sign_bundle(bundle_root, key_path=Path(str(cert_cfg["signing_key_path"])))
        mark("building_bundle", {"bundle_root": str(bundle_root), "profiles": len(profiles)})

    run_doc = json.loads((workspace.root / "run.json").read_text(encoding="utf-8"))
    run_doc["status"] = "completed"
    run_doc["updated_at"] = utc_now_rfc3339()
    write_atomic_json(workspace.root / "run.json", run_doc)
    index_run(workspace.root, run_doc)

    return {
        "run_id": workspace.run_id,
        "root": str(workspace.root),
        "status": run_doc["status"],
        "steps": status.get("steps", {}),
    }


def launch_bench_worker(
    *,
    worker_argv: list[str],
    cwd: Path,
    timeout_seconds: float,
    env: dict[str, str] | None = None,
    stdout_path: Path | None = None,
    stderr_path: Path | None = None,
) -> dict[str, Any]:
    """Launch a bench worker without a shell; enforce timeout."""
    if not worker_argv:
        raise PerceptShiftError(
            code=ErrorCode.CONFIG_INVALID,
            message="worker_argv must be non-empty",
        )
    if any("\n" in part or "\x00" in part for part in worker_argv):
        raise PerceptShiftError(
            code=ErrorCode.CONFIG_INVALID,
            message="worker argv contains unsafe characters",
        )

    clean_env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "LC_ALL": os.environ.get("LC_ALL", os.environ.get("LANG", "C.UTF-8")),
        "PERCEPTSHIFT_GIT_COMMIT": os.environ.get("PERCEPTSHIFT_GIT_COMMIT", ""),
    }
    # Library/root paths are required to load the ORT-linked native worker.
    # Do not copy the full process environment (secrets, extra tokens).
    for key in (
        "LD_LIBRARY_PATH",
        "DYLD_LIBRARY_PATH",
        "PERCEPTSHIFT_ORT_ROOT",
        "ORT_PREFIX",
        "PERCEPTSHIFT_ROOT",
        "TMPDIR",
        "TMP",
        "TEMP",
    ):
        value = os.environ.get(key)
        if value:
            clean_env[key] = value
    ort_root = clean_env.get("PERCEPTSHIFT_ORT_ROOT") or clean_env.get("ORT_PREFIX")
    if ort_root:
        ort_lib = str(Path(ort_root) / "lib")
        current = clean_env.get("LD_LIBRARY_PATH", "")
        parts = [part for part in current.split(":") if part]
        if ort_lib not in parts:
            clean_env["LD_LIBRARY_PATH"] = ":".join([ort_lib, *parts]) if parts else ort_lib
    if env:
        clean_env.update(env)

    stdout_file = open(stdout_path, "wb") if stdout_path else None
    stderr_file = open(stderr_path, "wb") if stderr_path else None
    started = time.monotonic()
    try:
        proc = subprocess.Popen(
            worker_argv,
            cwd=str(cwd),
            env=clean_env,
            stdout=stdout_file if stdout_file is not None else subprocess.PIPE,
            stderr=stderr_file if stderr_file is not None else subprocess.PIPE,
            shell=False,
            start_new_session=True,
        )
        try:
            stdout, stderr = proc.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
            raise PerceptShiftError(
                code=ErrorCode.BENCHMARK_TIMEOUT,
                message=f"Bench worker timed out after {timeout_seconds}s",
                details={"argv": worker_argv},
                cause=exc,
            ) from exc
    finally:
        if stdout_file is not None:
            stdout_file.close()
        if stderr_file is not None:
            stderr_file.close()

    elapsed = time.monotonic() - started
    # Prefer per-worker self-reported peak RSS from the worker stdout summary when
    # available. Do not treat cumulative RUSAGE_CHILDREN as authoritative candidate peak.
    peak_rss_mb: float | None = None
    peak_rss_unavailable_reason: str | None = None
    peak_rss_method: str | None = None
    if stdout_path is not None and stdout_path.is_file():
        try:
            for line in stdout_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                if (
                    isinstance(row, dict)
                    and row.get("document_type") == "perceptshift.bench_worker_summary"
                    and row.get("peak_rss_mb") is not None
                ):
                    peak_rss_mb = float(row["peak_rss_mb"])
                    peak_rss_method = str(row.get("peak_rss_method") or "worker_self_report")
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass
    if peak_rss_mb is None:
        peak_rss_unavailable_reason = "unavailable.sensor"

    result: dict[str, Any] = {
        "returncode": proc.returncode,
        "elapsed_seconds": elapsed,
        "argv": worker_argv,
        "peak_rss_mb": peak_rss_mb,
        "peak_rss_unavailable_reason": peak_rss_unavailable_reason,
        "peak_rss_method": peak_rss_method,
    }
    if stdout_path is None:
        result["stdout"] = (stdout or b"").decode("utf-8", errors="replace")
    if stderr_path is None:
        result["stderr"] = (stderr or b"").decode("utf-8", errors="replace")
    if proc.returncode != 0:
        stderr_text = str(result.get("stderr") or "")
        if not stderr_text and stderr_path is not None and stderr_path.is_file():
            try:
                stderr_text = stderr_path.read_text(encoding="utf-8", errors="replace")
                result["stderr"] = stderr_text[-8000:]
            except OSError:
                stderr_text = ""
        snippet = " ".join(stderr_text.split())[-800:]
        raise PerceptShiftError(
            code=ErrorCode.BENCHMARK_WORKER_CRASHED,
            message=(
                f"Bench worker exited with code {proc.returncode}"
                + (f": {snippet}" if snippet else "")
            ),
            details=result,
        )
    return result


def _native_binary_roots() -> list[Path]:
    roots: list[Path] = []
    for env_name in ("PERCEPTSHIFT_ROOT", "GITHUB_WORKSPACE"):
        value = os.environ.get(env_name)
        if value:
            roots.append(Path(value))
    roots.append(Path.cwd())
    # python/perceptshift_forge/src/perceptshift_forge/orchestration/__init__.py
    source_file = Path(__file__).resolve()
    if len(source_file.parents) > 5:
        roots.append(source_file.parents[5])
    unique: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        resolved = root.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(resolved)
    return unique


def find_native_binary(name: str) -> Path | None:
    """Resolve canonical hyphenated native binaries from build tree or PATH."""
    rels = [
        Path("build") / "default" / "cpp" / name,
        Path("build") / "dev-arm64" / "cpp" / name,
        Path("build") / "release-arm64" / "cpp" / name,
        Path("build") / "dev-x64" / "cpp" / name,
        Path("build") / "release-x64" / "cpp" / name,
        Path("build") / "release" / "cpp" / name,
        Path("build-clang") / "cpp" / name,
        Path("build") / "cpp" / name,
        Path("build") / "apps" / name,
        Path("cpp") / "build" / "apps" / name,
    ]
    candidates: list[Path] = []
    for root in _native_binary_roots():
        candidates.extend(root / rel for rel in rels)
    which = shutil.which(name)
    if which:
        candidates.append(Path(which))
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    for root in _native_binary_roots():
        for match in sorted(root.glob(f"build/**/{name}")):
            if match.is_file() and os.access(match, os.X_OK):
                return match
    return None
