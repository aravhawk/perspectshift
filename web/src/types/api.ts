/** API types aligned with perceptshift_api schemas. */

export type UnavailableField = {
  available: false;
  reason_code: string;
  message: string;
};

export type ApiErrorBody = {
  error: {
    code: string;
    message: string;
    correlation_id: string;
    retryable: boolean;
    details: Record<string, unknown>;
    remediation: string | null;
  };
};

export type Healthz = { status: "ok" };

export type Readyz = {
  ready: boolean;
  database: boolean;
  ros: string;
  reasons: string[];
};

export type VersionInfo = {
  product: string;
  api_version: string;
  schema_version: string;
};

export type Capabilities = {
  mutations_enabled: boolean;
  ros_bridge: string;
  artifact_store: boolean;
  websocket_telemetry: boolean;
  cors_origins: string[];
  bind_host: string;
  max_request_bytes: number;
};

export type RuntimeStatus = {
  connected: boolean;
  mode: "ros" | "artifact_store";
  active_profile_id: string | null;
  control_hold: boolean;
  deadline_ms: number | null;
  source_freshness: string | null;
  unavailable: Record<string, UnavailableField>;
};

export type RuntimeHealth = {
  state: string;
  reason_codes: string[];
  memory_headroom_bytes: number | null;
  temperature_c: number | null;
  throttling: boolean | null;
  control_hold: boolean;
  updated_at: string | null;
  unavailable: Record<string, UnavailableField>;
};

export type RuntimePolicy = {
  deadline_ms: number | null;
  pinned_profile_id: string | null;
  auto_switch_enabled: boolean;
  recovery_enabled: boolean;
  source: "default" | "runtime" | "operator";
};

export type RuntimePolicyPatch = {
  deadline_ms?: number | null;
  auto_switch_enabled?: boolean;
  recovery_enabled?: boolean;
};

export type ProfileSummary = {
  profile_id: string;
  label: string | null;
  model_hash_prefix: string | null;
  state: string;
  eligible: boolean;
  rejection_reasons: string[];
  certified_quality: number | null;
  certified_p99_ms: number | null;
  online_p99_ms: number | null;
  online_bound_ms: number | null;
  peak_rss_bytes: number | null;
  provider: string | null;
  active: boolean;
  pinned: boolean;
};

export type ProfileDetail = ProfileSummary & {
  provenance: Record<string, unknown>;
  attestations: Record<string, unknown>;
};

export type TelemetryEvent = {
  schema_version: string;
  document_type: string;
  event_type: string;
  sequence_number: number;
  server_timestamp: string;
  trace_id: string | null;
  payload: Record<string, unknown>;
  dropped_event_count?: number;
};

export type TelemetryRecent = {
  events: TelemetryEvent[];
  dropped_event_count: number;
};

export type TelemetryMetrics = {
  sample_count: number;
  p50_ms: number | null;
  p99_ms: number | null;
  deadline_misses: number;
  dropped_event_count: number;
  unavailable: Record<string, UnavailableField>;
};

export type SwitchEvent = {
  timestamp: string;
  from_profile: string | null;
  to_profile: string | null;
  reason: string | null;
  sequence: number;
  evidence: Record<string, unknown>;
  manual: boolean;
};

export type BundleInfo = {
  bundle_id: string | null;
  schema_version: string | null;
  product_version: string | null;
  integrity_status: string;
  signature_status: string;
  path_display: string | null;
  profiles: string[];
  file_hashes: Record<string, string>;
  provenance: Record<string, unknown>;
  unavailable: Record<string, UnavailableField>;
};

export type BundleVerifyResult = {
  path_display: string;
  integrity_status: string;
  signature_status: string;
  details: Record<string, unknown>;
};

export type RunSummary = {
  run_id: string;
  valid: boolean;
  host: string | null;
  model_hash: string | null;
  data_hash: string | null;
  candidate_count: number;
  quality_summary: string | null;
  latency_summary: string | null;
  import_status: string;
  pinned: boolean;
  created_at: string | null;
};

export type RunDetail = RunSummary & {
  workspace_display: string | null;
};

export type CandidateSummary = {
  candidate_id: string;
  profile_id: string | null;
  valid: boolean;
  quality_value: number | null;
  latency_p99_ms: number | null;
  summary: Record<string, unknown>;
};

export type RecoveryAction = "clear_control_hold" | "reload_profiles";
