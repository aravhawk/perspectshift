import {
  useCapabilities,
  useHealthz,
  useReadyz,
  useRuntimeHealth,
  useRuntimeStatus,
  useTelemetryMetrics,
} from "@/api/queries";
import { EmptyState } from "@/components/EmptyState";
import { ErrorPanel } from "@/components/ErrorPanel";
import { Metric } from "@/components/Metric";
import { StatusBadge } from "@/components/StatusBadge";

export function OverviewPage() {
  const healthz = useHealthz();
  const readyz = useReadyz();
  const status = useRuntimeStatus();
  const health = useRuntimeHealth();
  const metrics = useTelemetryMetrics();
  const caps = useCapabilities();

  if (healthz.isError) {
    return (
      <div>
        <header className="page-header">
          <h1>Overview</h1>
          <p>Local operational view of API, runtime, and recent latency.</p>
        </header>
        <EmptyState title="API disconnected">
          <p>
            The console could not reach the local PerceptShift API. No sample
            metrics are shown.
          </p>
          <ol>
            <li>
              Start the API:{" "}
              <code>uv run --package perceptshift-api perceptshift-api</code>
            </li>
            <li>
              Confirm it binds to <code>127.0.0.1:8741</code>
            </li>
            <li>
              Run the console with <code>pnpm --dir web dev</code> (proxies{" "}
              <code>/api</code>)
            </li>
          </ol>
          <ErrorPanel error={healthz.error} />
        </EmptyState>
      </div>
    );
  }

  const runtimeConnected = status.data?.connected ?? false;
  const controlHold = status.data?.control_hold ?? health.data?.control_hold ?? false;

  return (
    <div>
      <header className="page-header">
        <h1>Overview</h1>
        <p>Live connection and runtime posture. Empty fields stay unavailable.</p>
      </header>

      <div className="panel-grid">
        <Metric
          label="API"
          value={healthz.isSuccess ? "connected" : "checking"}
        />
        <Metric
          label="Runtime"
          value={runtimeConnected ? "connected" : "disconnected"}
          unavailable={
            runtimeConnected
              ? undefined
              : status.data?.unavailable.runtime?.reason_code ?? "RUNTIME_DISCONNECTED"
          }
        />
        <Metric
          label="Health state"
          value={health.data?.state ?? "unknown"}
          unavailable={health.data?.unavailable.health?.reason_code}
        />
        <Metric
          label="Control hold"
          value={controlHold ? "asserted" : "clear"}
        />
        <Metric
          label="Active profile"
          value={status.data?.active_profile_id ?? "—"}
          unavailable={
            status.data?.active_profile_id
              ? undefined
              : "NO_ACTIVE_PROFILE"
          }
        />
        <Metric
          label="Deadline"
          value={
            status.data?.deadline_ms != null
              ? String(status.data.deadline_ms)
              : "—"
          }
          unit="ms"
          unavailable={
            status.data?.deadline_ms == null ? "DEADLINE_UNAVAILABLE" : undefined
          }
        />
        <Metric
          label="Recent p99"
          value={metrics.data?.p99_ms != null ? metrics.data.p99_ms.toFixed(2) : "—"}
          unit="ms"
          unavailable={
            metrics.data?.unavailable.metrics?.reason_code ??
            (metrics.data?.sample_count ? undefined : "TELEMETRY_EMPTY")
          }
        />
        <Metric
          label="Memory headroom"
          value={
            health.data?.memory_headroom_bytes != null
              ? String(health.data.memory_headroom_bytes)
              : "—"
          }
          unit="B"
          unavailable={
            health.data?.memory_headroom_bytes == null
              ? "MEMORY_UNAVAILABLE"
              : undefined
          }
        />
        <Metric
          label="Temperature"
          value={
            health.data?.temperature_c != null
              ? health.data.temperature_c.toFixed(1)
              : "—"
          }
          unit="°C"
          unavailable={
            health.data?.temperature_c == null ? "TEMP_UNAVAILABLE" : undefined
          }
        />
      </div>

      <section className="panel" style={{ marginTop: "1rem" }}>
        <div className="metric-label">Connection summary</div>
        <p>
          <StatusBadge
            tone={healthz.isSuccess ? "ok" : "bad"}
            label={healthz.isSuccess ? "API up" : "API down"}
          />{" "}
          <StatusBadge
            tone={runtimeConnected ? "ok" : "warn"}
            label={
              runtimeConnected
                ? "Runtime connected"
                : `Runtime: ${status.data?.unavailable.runtime?.reason_code ?? "disconnected"}`
            }
          />{" "}
          <StatusBadge
            tone={controlHold ? "bad" : "ok"}
            label={controlHold ? "Control hold asserted" : "Control hold clear"}
          />
        </p>
        {readyz.data && !readyz.data.ready ? (
          <p style={{ marginTop: "0.75rem" }}>
            Readiness reasons: {readyz.data.reasons.join(", ") || "none"}
          </p>
        ) : null}
        {caps.data ? (
          <p style={{ marginTop: "0.75rem" }} className="mono">
            mutations={String(caps.data.mutations_enabled)} · bind=
            {caps.data.bind_host} · mode={status.data?.mode ?? "unknown"}
          </p>
        ) : null}
      </section>

      {!runtimeConnected ? (
        <div style={{ marginTop: "1rem" }}>
          <EmptyState title="Runtime not connected">
            <p>
              Artifact-store mode can still inspect indexed runs and bundles.
              To attach live telemetry, start the ROS-backed runtime and enable
              the API ROS bridge.
            </p>
          </EmptyState>
        </div>
      ) : null}
    </div>
  );
}
