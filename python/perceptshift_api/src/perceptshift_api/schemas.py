"""Pydantic response and request schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class UnavailableField(BaseModel):
    available: Literal[False] = False
    reason_code: str
    message: str


class VersionInfo(BaseModel):
    product: str = "perceptshift"
    api_version: str
    schema_version: str = "1.0"


class Capabilities(BaseModel):
    mutations_enabled: bool
    ros_bridge: str
    artifact_store: bool = True
    websocket_telemetry: bool = True
    cors_origins: list[str]
    bind_host: str
    max_request_bytes: int


class Healthz(BaseModel):
    status: Literal["ok"] = "ok"


class Readyz(BaseModel):
    ready: bool
    database: bool
    ros: str
    reasons: list[str] = Field(default_factory=list)


class RuntimeStatus(BaseModel):
    connected: bool
    mode: Literal["ros", "artifact_store"]
    active_profile_id: str | None = None
    control_hold: bool = False
    deadline_ms: float | None = None
    source_freshness: str | None = None
    unavailable: dict[str, UnavailableField] = Field(default_factory=dict)


class RuntimeHealth(BaseModel):
    state: str
    reason_codes: list[str] = Field(default_factory=list)
    memory_headroom_bytes: int | None = None
    temperature_c: float | None = None
    throttling: bool | None = None
    control_hold: bool = False
    updated_at: datetime | None = None
    unavailable: dict[str, UnavailableField] = Field(default_factory=dict)


class RuntimePolicy(BaseModel):
    deadline_ms: float | None = None
    pinned_profile_id: str | None = None
    auto_switch_enabled: bool = True
    recovery_enabled: bool = True
    source: Literal["default", "runtime", "operator"] = "default"


class RuntimePolicyPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deadline_ms: float | None = None
    auto_switch_enabled: bool | None = None
    recovery_enabled: bool | None = None


class RecoveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["clear_control_hold", "reload_profiles"] = "clear_control_hold"
    confirm: Literal[True]


class ProfileSummary(BaseModel):
    profile_id: str
    label: str | None = None
    model_hash_prefix: str | None = None
    state: str
    eligible: bool
    rejection_reasons: list[str] = Field(default_factory=list)
    certified_quality: float | None = None
    certified_p99_ms: float | None = None
    online_p99_ms: float | None = None
    online_bound_ms: float | None = None
    peak_rss_bytes: int | None = None
    provider: str | None = None
    active: bool = False
    pinned: bool = False


class ProfileDetail(ProfileSummary):
    provenance: dict[str, Any] = Field(default_factory=dict)
    attestations: dict[str, Any] = Field(default_factory=dict)


class PinRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirm: Literal[True] = True


class TelemetryRecent(BaseModel):
    events: list[dict[str, Any]]
    dropped_event_count: int = 0


class SwitchEvent(BaseModel):
    timestamp: datetime
    from_profile: str | None
    to_profile: str | None
    reason: str | None
    sequence: int
    evidence: dict[str, Any] = Field(default_factory=dict)
    manual: bool = False


class TelemetryMetrics(BaseModel):
    sample_count: int = 0
    p50_ms: float | None = None
    p99_ms: float | None = None
    deadline_misses: int = 0
    dropped_event_count: int = 0
    unavailable: dict[str, UnavailableField] = Field(default_factory=dict)


class BundleInfo(BaseModel):
    bundle_id: str | None = None
    schema_version: str | None = None
    product_version: str | None = None
    integrity_status: str
    signature_status: str
    path_display: str | None = None
    profiles: list[str] = Field(default_factory=list)
    file_hashes: dict[str, str] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)
    unavailable: dict[str, UnavailableField] = Field(default_factory=dict)


class BundleVerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str


class BundleVerifyResult(BaseModel):
    path_display: str
    integrity_status: str
    signature_status: str
    details: dict[str, Any] = Field(default_factory=dict)


class RunSummary(BaseModel):
    run_id: str
    valid: bool
    host: str | None = None
    model_hash: str | None = None
    data_hash: str | None = None
    candidate_count: int = 0
    quality_summary: str | None = None
    latency_summary: str | None = None
    import_status: str
    pinned: bool = False
    created_at: datetime | None = None


class RunDetail(RunSummary):
    workspace_display: str | None = None


class CandidateSummary(BaseModel):
    candidate_id: str
    profile_id: str | None = None
    valid: bool
    quality_value: float | None = None
    latency_p99_ms: float | None = None
    summary: dict[str, Any] = Field(default_factory=dict)


class SettingsView(BaseModel):
    host: str
    port: int
    mutations_enabled: bool
    cors_origins: list[str]
    artifact_roots_display: list[str]
    enable_ros: bool
    websocket_queue_size: int
    max_request_bytes: int
    data_dir_display: str
    state_dir_display: str
