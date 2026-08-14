import { useState } from "react";
import { useCapabilities, useRuntimeHealth, useRuntimeStatus } from "@/api/queries";
import { useApi } from "@/api/ApiProvider";
import { EmptyState } from "@/components/EmptyState";
import { ErrorPanel } from "@/components/ErrorPanel";
import { StatusBadge } from "@/components/StatusBadge";
import { useSessionToken } from "@/hooks/useSessionToken";

export function HealthPage() {
  const health = useRuntimeHealth();
  const status = useRuntimeStatus();
  const caps = useCapabilities();
  const api = useApi();
  const { hasToken } = useSessionToken();
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<unknown>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);

  const controlHold = health.data?.control_hold || status.data?.control_hold;

  async function clearHold() {
    setBusy(true);
    setActionError(null);
    try {
      await api.post("/api/v1/runtime/recovery", {
        action: "clear_control_hold",
        confirm: true,
      });
      await health.refetch();
      await status.refetch();
      setConfirmOpen(false);
    } catch (err) {
      setActionError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <header className="page-header">
        <h1>Health</h1>
        <p>Runtime health state, reason codes, and recovery controls.</p>
      </header>

      {health.isError ? <ErrorPanel error={health.error} /> : null}

      {!status.data?.connected ? (
        <EmptyState title="Runtime disconnected">
          <p>
            Health history and resource telemetry require a connected runtime.
            Reason:{" "}
            <code>
              {status.data?.unavailable.runtime?.reason_code ?? "RUNTIME_DISCONNECTED"}
            </code>
          </p>
        </EmptyState>
      ) : null}

      <section className="panel" style={{ marginTop: "1rem" }}>
        <div className="metric-label">Current state</div>
        <p>
          <StatusBadge
            tone={
              health.data?.state === "healthy"
                ? "ok"
                : health.data?.state === "unavailable"
                  ? "warn"
                  : "bad"
            }
            label={health.data?.state ?? "unknown"}
          />
        </p>
        <ul>
          {(health.data?.reason_codes ?? []).map((code) => (
            <li key={code} className="mono">
              {code}
            </li>
          ))}
        </ul>
        <p style={{ marginTop: "0.75rem" }}>
          Control hold:{" "}
          <StatusBadge
            tone={controlHold ? "bad" : "ok"}
            label={controlHold ? "asserted" : "clear"}
          />
        </p>
        <p className="mono">
          memory=
          {health.data?.memory_headroom_bytes != null
            ? `${health.data.memory_headroom_bytes} B`
            : "unavailable"}{" "}
          · temp=
          {health.data?.temperature_c != null
            ? `${health.data.temperature_c} °C`
            : "unavailable"}{" "}
          · throttling=
          {health.data?.throttling == null
            ? "unavailable"
            : String(health.data.throttling)}
        </p>
      </section>

      <section className="panel">
        <div className="metric-label">Recovery</div>
        {!caps.data?.mutations_enabled || !hasToken ? (
          <p>
            Recovery actions are hidden until mutation mode is enabled on the API
            and a session token is entered under Settings.
          </p>
        ) : (
          <>
            <button
              type="button"
              className="btn btn-danger"
              disabled={busy || !controlHold}
              onClick={() => setConfirmOpen(true)}
            >
              Clear control hold
            </button>
            {confirmOpen ? (
              <div className="banner banner-warn" style={{ marginTop: "0.75rem" }}>
                <p>Confirm clear control-hold request?</p>
                <button type="button" className="btn" disabled={busy} onClick={clearHold}>
                  Confirm
                </button>{" "}
                <button
                  type="button"
                  className="btn"
                  disabled={busy}
                  onClick={() => setConfirmOpen(false)}
                >
                  Cancel
                </button>
              </div>
            ) : null}
          </>
        )}
        {actionError ? <ErrorPanel error={actionError} /> : null}
      </section>
    </div>
  );
}
