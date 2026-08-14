import { useRuns } from "@/api/queries";
import { EmptyState } from "@/components/EmptyState";
import { ErrorPanel } from "@/components/ErrorPanel";
import { useTimeFormat } from "@/hooks/useTimeFormat";

export function RunsPage() {
  const q = useRuns();
  const { format } = useTimeFormat();
  if (q.isError) {
    return (
      <div>
        <header className="page-header">
          <h1>Benchmark runs</h1>
          <p>Indexed forge runs available on this host.</p>
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
          <h1>Benchmark runs</h1>
          <p>Indexed forge runs available on this host.</p>
        </header>
        <EmptyState title="No indexed runs">
          <p>
            Run <code>perceptshift forge run</code> with your model and datasets, then
            index the run for inspection.
          </p>
        </EmptyState>
      </div>
    );
  }
  return (
    <div>
      <header className="page-header">
        <h1>Benchmark runs</h1>
        <p>Indexed forge runs available on this host.</p>
      </header>
      {q.isLoading ? (
        <p role="status">Loading…</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th scope="col">Run ID</th>
              <th scope="col">Valid</th>
              <th scope="col">Candidates</th>
              <th scope="col">Created</th>
            </tr>
          </thead>
          <tbody>
            {items.map((r) => (
              <tr key={r.run_id}>
                <td>
                  <code>{r.run_id}</code>
                </td>
                <td>{r.valid ? "yes" : "no"}</td>
                <td>{r.candidate_count}</td>
                <td>{format(r.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
