import { useCurrentBundle } from "@/api/queries";
import { EmptyState } from "@/components/EmptyState";
import { ErrorPanel } from "@/components/ErrorPanel";
import { StatusBadge } from "@/components/StatusBadge";

export function BundleInspectorPage() {
  const bundle = useCurrentBundle();

  const unavailable = bundle.data?.unavailable?.bundle;

  return (
    <div>
      <header className="page-header">
        <h1>Bundle inspector</h1>
        <p>Integrity and provenance for the current profile bundle.</p>
      </header>

      {bundle.isError ? <ErrorPanel error={bundle.error} /> : null}

      {unavailable ? (
        <EmptyState title="No current bundle">
          <p>
            <code>{unavailable.reason_code}</code>: {unavailable.message}
          </p>
          <ol>
            <li>Certify and package a profile bundle.</li>
            <li>
              Install it under a registered artifact root (for example{" "}
              <code>$XDG_DATA_HOME/perceptshift/bundles/current/</code>).
            </li>
            <li>Re-open this page — raw filesystem browsing is not exposed.</li>
          </ol>
        </EmptyState>
      ) : null}

      {bundle.isSuccess && !unavailable ? (
        <section className="panel">
          <div className="panel-grid">
            <div>
              <div className="metric-label">Bundle ID</div>
              <div className="mono">{bundle.data.bundle_id ?? "—"}</div>
            </div>
            <div>
              <div className="metric-label">Schema</div>
              <div className="mono">{bundle.data.schema_version ?? "—"}</div>
            </div>
            <div>
              <div className="metric-label">Integrity</div>
              <StatusBadge tone="ok" label={bundle.data.integrity_status} />
            </div>
            <div>
              <div className="metric-label">Signature</div>
              <StatusBadge tone="warn" label={bundle.data.signature_status} />
            </div>
          </div>
          <p style={{ marginTop: "1rem" }} className="mono">
            path={bundle.data.path_display ?? "—"}
          </p>
          <h2 style={{ marginTop: "1rem", fontSize: "1rem" }}>Profiles</h2>
          <ul>
            {bundle.data.profiles.map((id) => (
              <li key={id} className="mono">
                {id}
              </li>
            ))}
          </ul>
          <h2 style={{ marginTop: "1rem", fontSize: "1rem" }}>File hashes</h2>
          <ul>
            {Object.entries(bundle.data.file_hashes).map(([name, hash]) => (
              <li key={name} className="mono">
                {name}: {hash}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
