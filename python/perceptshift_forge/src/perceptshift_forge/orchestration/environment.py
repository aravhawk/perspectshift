"""Capture schema-backed Forge environment evidence before certification."""

from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path
from typing import Any

from perceptshift_common.hashing import write_atomic_json
from perceptshift_common.producer import envelope_fields, producer_metadata, utc_now_rfc3339
from perceptshift_common.reason_codes import ReasonCode
from perceptshift_common.version import get_version


def _unavailable(field: str, reason: str) -> dict[str, Any]:
    return {"field": field, "reason_code": reason, "message": reason}


def capture_environment(*, workspace_root: Path, require_valid: bool) -> dict[str, Any]:
    """Write environment/status.json and environment/host-fingerprint.json."""
    env_dir = workspace_root / "environment"
    env_dir.mkdir(parents=True, exist_ok=True)
    unavailable: list[dict[str, Any]] = []

    arch = platform.machine()
    os_name = platform.system()
    os_release = platform.release()
    os_version = platform.version()
    distro: dict[str, Any] = {"name": os_name, "release": os_release, "version": os_version}
    os_release_path = Path("/etc/os-release")
    if os_release_path.is_file():
        for line in os_release_path.read_text(encoding="utf-8").splitlines():
            if "=" in line:
                key, _, value = line.partition("=")
                distro[key.lower()] = value.strip().strip('"')

    cpu: dict[str, Any] = {
        "model": platform.processor() or None,
        "logical_cores": os.cpu_count(),
    }
    if not cpu["model"]:
        unavailable.append(_unavailable("cpu.model", str(ReasonCode.UNAVAILABLE_DATA)))

    memory: dict[str, Any] = {}
    try:
        if Path("/proc/meminfo").is_file():
            for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
                if line.startswith("MemAvailable:"):
                    memory["available_kb"] = int(line.split()[1])
                if line.startswith("MemTotal:"):
                    memory["total_kb"] = int(line.split()[1])
        else:
            unavailable.append(_unavailable("memory", str(ReasonCode.UNAVAILABLE_DATA)))
            memory = {
                "available_kb": None,
                "total_kb": None,
                "unavailable_reason": str(ReasonCode.UNAVAILABLE_DATA),
            }
    except OSError:
        unavailable.append(_unavailable("memory", str(ReasonCode.UNAVAILABLE_DATA)))
        memory = {
            "available_kb": None,
            "total_kb": None,
            "unavailable_reason": str(ReasonCode.UNAVAILABLE_DATA),
        }

    thermal: dict[str, Any] = {
        "primary_celsius": None,
        "unavailable_reason": str(ReasonCode.UNAVAILABLE_THERMAL),
    }
    thermal_zone = Path("/sys/class/thermal/thermal_zone0/temp")
    if thermal_zone.is_file():
        try:
            milli = int(thermal_zone.read_text(encoding="utf-8").strip())
            thermal = {"primary_celsius": milli / 1000.0, "source": str(thermal_zone)}
        except (OSError, ValueError):
            unavailable.append(_unavailable("thermal", str(ReasonCode.UNAVAILABLE_THERMAL)))
    else:
        unavailable.append(_unavailable("thermal", str(ReasonCode.UNAVAILABLE_THERMAL)))

    throttling: dict[str, Any] = {
        "active": None,
        "unavailable_reason": str(ReasonCode.UNAVAILABLE_PERF),
    }
    # Linux thermal throttling evidence via CPU freq / RAPL is platform-specific.
    throttle_paths = [
        Path("/sys/devices/system/cpu/cpu0/thermal_throttle/core_throttle_count"),
        Path("/sys/devices/system/cpu/cpu0/thermal_throttle/package_throttle_count"),
    ]
    throttle_counts: list[int] = []
    for path in throttle_paths:
        if path.is_file():
            try:
                throttle_counts.append(int(path.read_text(encoding="utf-8").strip()))
            except (OSError, ValueError):
                pass
    if throttle_counts:
        throttling = {
            "active": any(c > 0 for c in throttle_counts),
            "counts": throttle_counts,
            "source": "sysfs_thermal_throttle",
        }
    else:
        unavailable.append(_unavailable("throttling", str(ReasonCode.UNAVAILABLE_PERF)))

    ort_info: dict[str, Any] = {"version": None, "providers": []}
    try:
        import onnxruntime as ort

        ort_info["version"] = getattr(ort, "__version__", None)
        ort_info["providers"] = list(ort.get_available_providers())
    except Exception:
        unavailable.append(_unavailable("onnxruntime", str(ReasonCode.UNAVAILABLE_DEPENDENCY)))
        ort_info["unavailable_reason"] = str(ReasonCode.UNAVAILABLE_DEPENDENCY)

    git_commit = "unknown"
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            cwd=str(workspace_root),
        )
        if proc.returncode == 0:
            git_commit = proc.stdout.strip() or "unknown"
        else:
            unavailable.append(_unavailable("git_commit", str(ReasonCode.UNAVAILABLE_DATA)))
    except OSError:
        unavailable.append(_unavailable("git_commit", str(ReasonCode.UNAVAILABLE_DATA)))

    fingerprint = envelope_fields(document_type="perceptshift.host_fingerprint")
    fingerprint.update(
        {
            "architecture": arch,
            "os": distro,
            "hostname_hash": None,
            "machine_id_hash": None,
            "container": {
                "in_container": Path("/.dockerenv").exists(),
            },
            "cpu": cpu,
            "memory": memory,
            "frequency": {
                "unavailable_reason": str(ReasonCode.UNAVAILABLE_PERF),
            },
            "thermal": thermal,
            "throttling": throttling,
            "onnxruntime": ort_info,
            "ros": None,
            "build": {
                "product_version": get_version(),
                "git_commit": git_commit,
            },
            "unavailable": unavailable,
            "producer": producer_metadata(),
            "created_at": utc_now_rfc3339(),
        }
    )
    write_atomic_json(env_dir / "host-fingerprint.json", fingerprint)

    # Validity: architecture present + ORT providers when required.
    valid = bool(arch) and bool(ort_info.get("providers"))
    status = "valid" if valid else "invalid"
    if not valid and not require_valid:
        status = "valid_with_warnings"
    status_doc = {
        "schema_version": "1.0",
        "document_type": "perceptshift.environment_status",
        "status": status,
        "require_valid_environment": require_valid,
        "timestamp": utc_now_rfc3339(),
        "product_version": get_version(),
        "architecture": arch,
        "onnxruntime_providers": ort_info.get("providers") or [],
        "valid_for_certification_policy": valid or (not require_valid),
        "unavailable": unavailable,
        "active_performance_env": {
            k: os.environ.get(k)
            for k in (
                "OMP_NUM_THREADS",
                "ORT_NUM_THREADS",
                "PERCEPTSHIFT_ORT_INTRA_OP_THREADS",
            )
            if os.environ.get(k) is not None
        },
    }
    write_atomic_json(env_dir / "status.json", status_doc)
    return status_doc
