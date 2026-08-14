import { useSwitchHistory } from "@/api/queries";
import { EmptyState } from "@/components/EmptyState";
import { ErrorPanel } from "@/components/ErrorPanel";
import { useTimeFormat } from "@/hooks/useTimeFormat";

export function SwitchesPage() {
  const q = useSwitchHistory();
  const { format } = useTimeFormat();
  if (q.isError) {
    return (
      <div>
        <header className="page-header">
          <h1>Switch history</h1>
          <p>Automatic and manual profile switches with reasons.</p>
        </header>
        <EmptyState title="API disconnected">
          <ErrorPanel error={q.error} />
        </EmptyState>
      </div>
    );
  }
  const items = q.data ?? [];
  if (!q.isLoading && items.length === 0) {
    return (
      <div>
        <header className="page-header">
          <h1>Switch history</h1>
          <p>Automatic and manual profile switches with reasons.</p>
        </header>
        <EmptyState title="No switches recorded">
          <p>Switch events appear when a connected runtime changes profiles.</p>
        </EmptyState>
      </div>
    );
  }
  return (
    <div>
      <header className="page-header">
        <h1>Switch history</h1>
        <p>Automatic and manual profile switches with reasons.</p>
      </header>
      {q.isLoading ? (
        <p role="status">Loading…</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th scope="col">Time</th>
              <th scope="col">From</th>
              <th scope="col">To</th>
              <th scope="col">Reason</th>
              <th scope="col">Mode</th>
            </tr>
          </thead>
          <tbody>
            {items.map((s) => (
              <tr key={`${s.timestamp}-${s.sequence}`}>
                <td>{format(s.timestamp)}</td>
                <td>{s.from_profile ?? "—"}</td>
                <td>{s.to_profile ?? "—"}</td>
                <td>{s.reason ?? "—"}</td>
                <td>{s.manual ? "manual" : "automatic"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
