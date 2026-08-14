import { useMemo } from "react";
import { useTelemetryMetrics, useTelemetryRecent } from "@/api/queries";
import { EmptyState } from "@/components/EmptyState";
import { ErrorPanel } from "@/components/ErrorPanel";
import { useTelemetrySocket } from "@/hooks/useTelemetrySocket";

function LatencySpark({
  points,
  deadlineMs,
}: {
  points: { t: number; y: number; profile?: string }[];
  deadlineMs: number | null;
}) {
  if (points.length < 2) {
    return (
      <div className="chart-placeholder" role="img" aria-label="No latency samples">
        awaiting samples
      </div>
    );
  }
  const ys = points.map((p) => p.y);
  const minY = 0;
  const maxY = Math.max(...ys, deadlineMs ?? 0, 1);
  const w = 640;
  const h = 200;
  const path = points
    .map((p, i) => {
      const x = (i / (points.length - 1)) * (w - 20) + 10;
      const y = h - 20 - ((p.y - minY) / (maxY - minY)) * (h - 40);
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const deadlineY =
    deadlineMs != null
      ? h - 20 - ((deadlineMs - minY) / (maxY - minY)) * (h - 40)
      : null;

  const summary = `Latency series with ${points.length} points; latest ${points[points.length - 1].y.toFixed(2)} ms.`;

  return (
    <div className="latency-chart">
      <p className="sr-only">{summary}</p>
      <svg viewBox={`0 0 ${w} ${h}`} role="img" aria-label={summary}>
        <rect x="0" y="0" width={w} height={h} fill="transparent" />
        {deadlineY != null ? (
          <line
            x1="10"
            x2={w - 10}
            y1={deadlineY}
            y2={deadlineY}
            stroke="#e8b84a"
            strokeDasharray="4 4"
          />
        ) : null}
        <path d={path} fill="none" stroke="#3ecf8e" strokeWidth="2" />
      </svg>
    </div>
  );
}

export function LatencyPage() {
  const recent = useTelemetryRecent();
  const metrics = useTelemetryMetrics();
  const socket = useTelemetrySocket({ enabled: true });

  const points = useMemo(() => {
    const source =
      socket.events.length > 0
        ? socket.events
        : recent.data?.events ?? [];
    return source
      .filter((e) => e.event_type === "inference_trace_summary")
      .map((e, idx) => ({
        t: idx,
        y: Number(e.payload.total_ms ?? NaN),
        profile:
          typeof e.payload.profile_id === "string"
            ? e.payload.profile_id
            : undefined,
      }))
      .filter((p) => Number.isFinite(p.y));
  }, [socket.events, recent.data]);

  return (
    <div>
      <header className="page-header">
        <h1>Latency</h1>
        <p>Streamed inference durations. Missing samples are not interpolated.</p>
      </header>

      {recent.isError ? <ErrorPanel error={recent.error} /> : null}

      <section className="panel">
        <div className="metric-label">Stream</div>
        <p className="mono">
          ws={socket.connected ? "connected" : "disconnected"} · gaps=
          {socket.sequenceGaps} · dropped=
          {socket.droppedEventCount || metrics.data?.dropped_event_count || 0} ·
          samples={points.length}
        </p>
        <LatencySpark
          points={points}
          deadlineMs={null}
        />
      </section>

      {points.length === 0 ? (
        <div style={{ marginTop: "1rem" }}>
          <EmptyState title="No latency telemetry">
            <p>
              Charts stay empty until real inference_trace_summary events arrive
              from the runtime bridge.
            </p>
            <ul>
              <li>Connect a live runtime publishing telemetry.</li>
              <li>
                Or inspect historical runs under Benchmark runs — this page does
                not invent series data.
              </li>
            </ul>
          </EmptyState>
        </div>
      ) : null}
    </div>
  );
}
