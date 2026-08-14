import { useCurrentBundle } from "@/api/queries";
import { EmptyState } from "@/components/EmptyState";
import { ErrorPanel } from "@/components/ErrorPanel";

export function BundlePage() {
  const q = useCurrentBundle();
  if (q.isError) {
    return (
      <div>
        <header className="page-header">
          <h1>Bundle inspector</h1>
          <p>Integrity and provenance for the active local profile bundle.</p>
        </header>
        <EmptyState title="API disconnected">
          <ErrorPanel error={q.error} />
        </EmptyState>
      </div>
    );
  }
  if (q.isLoading) {
    return (
      <div>
        <header className="page-header">
          <h1>Bundle inspector</h1>
          <p>Integrity and provenance for the active local profile bundle.</p>
        </header>
        <p role="status">Loading…</p>
      </div>
    );
  }
  const b = q.data;
  if (!b || !b.bundle_id) {
    return (
      <div>
        <header className="page-header">
          <h1>Bundle inspector</h1>
          <p>Integrity and provenance for the active local profile bundle.</p>
        </header>
        <EmptyState title="No bundle loaded">
          <p>Import or point the runtime at a verified profile bundle directory.</p>
        </EmptyState>
      </div>
    );
  }
  return (
    <div>
      <header className="page-header">
        <h1>Bundle inspector</h1>
        <p>Integrity and provenance for the active local profile bundle.</p>
      </header>
      <dl className="metric-grid">
        <div className="metric">
          <div className="metric-label">Bundle ID</div>
          <div className="metric-value">{b.bundle_id}</div>
        </div>
        <div className="metric">
          <div className="metric-label">Schema</div>
          <div className="metric-value">{b.schema_version ?? "—"}</div>
        </div>
        <div className="metric">
          <div className="metric-label">Integrity</div>
          <div className="metric-value">{b.integrity_status}</div>
        </div>
        <div className="metric">
          <div className="metric-label">Signature</div>
          <div className="metric-value">{b.signature_status}</div>
        </div>
        <div className="metric">
          <div className="metric-label">Profiles</div>
          <div className="metric-value">{b.profiles.length}</div>
        </div>
      </dl>
    </div>
  );
}
