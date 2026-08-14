import { useSwitchHistory } from "@/api/queries";
import { EmptyState } from "@/components/EmptyState";
import { ErrorPanel } from "@/components/ErrorPanel";
import { useTimeFormat } from "@/hooks/useTimeFormat";

export function SwitchHistoryPage() {
  const switches = useSwitchHistory();
  const { format } = useTimeFormat();

  return (
    <div>
      <header className="page-header">
        <h1>Switch history</h1>
        <p>Profile transitions with reason codes and evidence.</p>
      </header>

      {switches.isError ? <ErrorPanel error={switches.error} /> : null}

      {switches.isSuccess && switches.data.length === 0 ? (
        <EmptyState title="No switch events">
          <p>
            Switch history stays empty until the runtime emits switch_event
            telemetry or events are persisted in the API index.
          </p>
        </EmptyState>
      ) : null}

      {switches.isSuccess && switches.data.length > 0 ? (
        <div className="panel" style={{ overflowX: "auto" }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Time</th>
                <th>From</th>
                <th>To</th>
                <th>Reason</th>
                <th>Seq</th>
                <th>Mode</th>
              </tr>
            </thead>
            <tbody>
              {switches.data.map((evt) => (
                <tr key={`${evt.sequence}-${evt.timestamp}`}>
                  <td className="mono">{format(evt.timestamp)}</td>
                  <td className="mono">{evt.from_profile ?? "—"}</td>
                  <td className="mono">{evt.to_profile ?? "—"}</td>
                  <td>{evt.reason ?? "—"}</td>
                  <td className="mono">{evt.sequence}</td>
                  <td>{evt.manual ? "manual" : "automatic"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
