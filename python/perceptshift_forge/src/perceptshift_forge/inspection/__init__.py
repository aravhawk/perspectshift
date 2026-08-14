"""Host doctor orchestration calling native inspect when present."""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from perceptshift_common.paths import path_inventory
from perceptshift_common.producer import envelope_fields
from perceptshift_common.reason_codes import ReasonCode
from perceptshift_common.version import get_version
from perceptshift_forge.orchestration import find_native_binary


def run_doctor() -> dict[str, Any]:
    report = envelope_fields(document_type="perceptshift.doctor_report")
    report.update(
        {
            "product_version": get_version(),
            "python": {
                "version": sys.version,
                "executable": sys.executable,
                "platform": platform.platform(),
                "machine": platform.machine(),
            },
            "paths": path_inventory(),
            "dependencies": _dependency_probe(),
            "native": _native_inspect(),
        }
    )
    return report


_DIST_NAMES = {
    "onnx": "onnx",
    "onnxruntime": "onnxruntime",
    "numpy": "numpy",
    "PIL": "pillow",
    "jsonschema": "jsonschema",
    "yaml": "PyYAML",
    "pydantic": "pydantic",
}


def _package_version(dist_name: str, module: object) -> str | None:
    try:
        return version(dist_name)
    except PackageNotFoundError:
        if dist_name == "jsonschema":
            return None
        raw = getattr(module, "__version__", None)
        return str(raw) if raw is not None else None


def _dependency_probe() -> dict[str, Any]:
    deps: dict[str, Any] = {}
    for name in ("onnx", "onnxruntime", "numpy", "PIL", "jsonschema", "yaml", "pydantic"):
        try:
            module = __import__(name if name != "PIL" else "PIL")
            deps[name] = {
                "available": True,
                "version": _package_version(_DIST_NAMES[name], module),
            }
        except ImportError as exc:
            deps[name] = {
                "available": False,
                "reason_code": ReasonCode.UNAVAILABLE_DEPENDENCY,
                "message": str(exc),
            }
    try:
        import onnxruntime as ort

        deps["onnxruntime"]["providers"] = list(ort.get_available_providers())
    except Exception:
        pass
    return deps


def _native_inspect() -> dict[str, Any]:
    binary = find_native_binary("perceptshift_inspect") or find_native_binary("inspect_worker")
    if binary is None:
        which = shutil.which("perceptshift-inspect")
        binary = Path(which) if which else None
    if binary is None:
        return {
            "available": False,
            "reason_code": ReasonCode.UNAVAILABLE_NATIVE_BINARY,
            "message": "Native inspect binary not found",
        }
    try:
        completed = subprocess.run(
            [str(binary), "--json"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
            shell=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "available": False,
            "reason_code": ReasonCode.UNAVAILABLE_NATIVE_BINARY,
            "message": f"Failed to execute native inspect: {exc}",
            "binary": str(binary),
        }
    payload: dict[str, Any] = {
        "available": completed.returncode == 0,
        "binary": str(binary),
        "returncode": completed.returncode,
    }
    if completed.returncode != 0:
        payload["reason_code"] = ReasonCode.UNAVAILABLE_NATIVE_BINARY
        payload["stderr"] = completed.stderr.strip()
        return payload
    try:
        payload["report"] = json.loads(completed.stdout)
    except json.JSONDecodeError:
        payload["stdout"] = completed.stdout
    return payload
