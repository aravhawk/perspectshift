"""Typed error taxonomy for PerceptShift Python components."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    CONFIG_INVALID = "CONFIG_INVALID"
    SCHEMA_UNSUPPORTED = "SCHEMA_UNSUPPORTED"
    PATH_UNSAFE = "PATH_UNSAFE"
    FILE_INTEGRITY_FAILED = "FILE_INTEGRITY_FAILED"
    SIGNATURE_REQUIRED = "SIGNATURE_REQUIRED"
    SIGNATURE_INVALID = "SIGNATURE_INVALID"
    MODEL_INVALID = "MODEL_INVALID"
    MODEL_RESOURCE_LIMIT = "MODEL_RESOURCE_LIMIT"
    MODEL_TENSOR_MISMATCH = "MODEL_TENSOR_MISMATCH"
    MODEL_PROVIDER_UNAVAILABLE = "MODEL_PROVIDER_UNAVAILABLE"
    MODEL_PROVIDER_FALLBACK_EXCESSIVE = "MODEL_PROVIDER_FALLBACK_EXCESSIVE"
    DATASET_INVALID = "DATASET_INVALID"
    DATASET_LEAKAGE = "DATASET_LEAKAGE"
    QUANTIZATION_FAILED = "QUANTIZATION_FAILED"
    QUANTIZATION_UNAVAILABLE = "QUANTIZATION_UNAVAILABLE"
    QUALITY_GATE_FAILED = "QUALITY_GATE_FAILED"
    EQUIVALENCE_GATE_FAILED = "EQUIVALENCE_GATE_FAILED"
    BENCHMARK_ENVIRONMENT_INVALID = "BENCHMARK_ENVIRONMENT_INVALID"
    BENCHMARK_WORKER_CRASHED = "BENCHMARK_WORKER_CRASHED"
    BENCHMARK_TIMEOUT = "BENCHMARK_TIMEOUT"
    PROFILE_INCOMPATIBLE = "PROFILE_INCOMPATIBLE"
    PROFILE_WARMUP_FAILED = "PROFILE_WARMUP_FAILED"
    NO_ELIGIBLE_PROFILE = "NO_ELIGIBLE_PROFILE"
    INPUT_STALE = "INPUT_STALE"
    INPUT_UNSUPPORTED = "INPUT_UNSUPPORTED"
    INFERENCE_FAILED = "INFERENCE_FAILED"
    POSTPROCESS_FAILED = "POSTPROCESS_FAILED"
    RESOURCE_EXHAUSTED = "RESOURCE_EXHAUSTED"
    TELEMETRY_UNAVAILABLE = "TELEMETRY_UNAVAILABLE"
    ROS_LIFECYCLE_ERROR = "ROS_LIFECYCLE_ERROR"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    AUTH_INVALID = "AUTH_INVALID"
    DATABASE_ERROR = "DATABASE_ERROR"
    INTERNAL_INVARIANT_FAILED = "INTERNAL_INVARIANT_FAILED"
    DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"
    RUN_LOCK_HELD = "RUN_LOCK_HELD"
    RUN_RESUME_INVALID = "RUN_RESUME_INVALID"
    BUNDLE_INVALID = "BUNDLE_INVALID"
    NOT_FOUND = "NOT_FOUND"


@dataclass(slots=True)
class PerceptShiftError(Exception):
    """Structured product error with stable machine-readable code."""

    code: ErrorCode
    message: str
    remediation: str | None = None
    retryable: bool = False
    correlation_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    cause: BaseException | None = None

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": str(self.code),
            "message": self.message,
            "retryable": self.retryable,
            "details": self.details,
        }
        if self.remediation is not None:
            payload["remediation"] = self.remediation
        if self.correlation_id is not None:
            payload["correlation_id"] = self.correlation_id
        if self.cause is not None:
            payload["cause"] = f"{type(self.cause).__name__}: {self.cause}"
        return payload
