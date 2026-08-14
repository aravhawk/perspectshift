"""Machine-readable reason codes for unavailable measurements and gate failures."""

from __future__ import annotations

from enum import StrEnum


class ReasonCode(StrEnum):
    """Stable reason codes. Prefer these over silent omission."""

    UNAVAILABLE_PROVIDER = "unavailable.provider"
    UNAVAILABLE_SENSOR = "unavailable.sensor"
    UNAVAILABLE_DEPENDENCY = "unavailable.dependency"
    UNAVAILABLE_NATIVE_BINARY = "unavailable.native_binary"
    UNAVAILABLE_PLATFORM = "unavailable.platform"
    UNAVAILABLE_PERMISSION = "unavailable.permission"
    UNAVAILABLE_DATA = "unavailable.data"
    UNAVAILABLE_POWER = "unavailable.power"
    UNAVAILABLE_THERMAL = "unavailable.thermal"
    UNAVAILABLE_PERF = "unavailable.perf"
    UNAVAILABLE_COCO_TOOLS = "unavailable.pycocotools"
    UNAVAILABLE_QUANTIZATION_API = "unavailable.quantization_api"
    UNAVAILABLE_RUNTIME_STATUS = "unavailable.runtime_status"

    GATE_SCHEMA = "gate.schema"
    GATE_INTEGRITY = "gate.integrity"
    GATE_MODEL_VALIDATION = "gate.model_validation"
    GATE_HOST_COMPATIBILITY = "gate.host_compatibility"
    GATE_PROVIDER = "gate.provider"
    GATE_TENSOR_CONTRACT = "gate.tensor_contract"
    GATE_SEMANTIC_EQUIVALENCE = "gate.semantic_equivalence"
    GATE_QUALITY = "gate.quality"
    GATE_MEMORY = "gate.memory"
    GATE_LATENCY = "gate.latency"
    GATE_ENVIRONMENT = "gate.environment"
    GATE_WARMUP = "gate.warmup"
    GATE_ARTIFACT_COMPLETENESS = "gate.artifact_completeness"

    DATASET_PATH_ESCAPE = "dataset.path_escape"
    DATASET_SYMLINK_REJECTED = "dataset.symlink_rejected"
    DATASET_MISSING_FILE = "dataset.missing_file"
    DATASET_DUPLICATE = "dataset.duplicate"
    DATASET_CROSS_SPLIT_LEAKAGE = "dataset.cross_split_leakage"
    DATASET_DECODE_FAILED = "dataset.decode_failed"

    TRIAL_THROTTLING = "trial.throttling"
    TRIAL_TEMPERATURE = "trial.temperature"
    TRIAL_INCOMPLETE = "trial.incomplete"
    TRIAL_WORKER_CRASH = "trial.worker_crash"
    TRIAL_TIMEOUT = "trial.timeout"
    TRIAL_RESOURCE_LIMIT = "trial.resource_limit"
