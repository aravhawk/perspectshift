import { useRuns } from "@/api/queries";
import { EmptyState } from "@/components/EmptyState";
import { ErrorPanel } from "@/components/ErrorPanel";
import { StatusBadge } from "@/components/StatusBadge";
import { useTimeFormat } from "@/hooks/useTimeFormat";

export function BenchmarkRunsPage() {
  const runs = useRuns();
  const { format } = useTimeFormat();

  return (
    <div>
      <header className="page-header">
        <h1>Benchmark runs</h1>
        <p>Indexed forge/benchmark runs from the local artifact store.</p>
      </header>

      {runs.isError ? <ErrorPanel error={runs.error} /> : null}

      {runs.isSuccess && runs.data.length === 0 ? (
        <EmptyState title="No indexed runs">
          <p>The run index is empty. This console does not ship sample runs.</p>
          <ol>
            <li>Execute a real forge/benchmark workflow against your model and data.</li>
            <li>Import or index the run workspace into the API artifact store.</li>
            <li>Refresh this page to inspect validity, hashes, and summaries.</li>
          </ol>
        </EmptyState>
      ) : null}

      {runs.isSuccess && runs.data.length > 0 ? (
        <div className="panel" style={{ overflowX: "auto" }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Run</th>
                <th>Valid</th>
                <th>Host</th>
                <th>Model hash</th>
                <th>Data hash</th>
                <th>Candidates</th>
                <th>Quality</th>
                <th>Latency</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {runs.data.map((run) => (
                <tr key={run.run_id}>
                  <td className="mono">{run.run_id}</td>
                  <td>
                    <StatusBadge
                      tone={run.valid ? "ok" : "bad"}
                      label={run.valid ? "valid" : "invalid"}
                    />
                  </td>
                  <td>{run.host ?? "—"}</td>
                  <td className="mono">{run.model_hash?.slice(0, 12) ?? "—"}</td>
                  <td className="mono">{run.data_hash?.slice(0, 12) ?? "—"}</td>
                  <td className="mono">{run.candidate_count}</td>
                  <td>{run.quality_summary ?? "—"}</td>
                  <td>{run.latency_summary ?? "—"}</td>
                  <td className="mono">{format(run.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
