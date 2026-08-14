import { useProfiles } from "@/api/queries";
import { EmptyState } from "@/components/EmptyState";
import { ErrorPanel } from "@/components/ErrorPanel";
import { StatusBadge } from "@/components/StatusBadge";

export function ProfilesPage() {
  const profiles = useProfiles();

  return (
    <div>
      <header className="page-header">
        <h1>Profiles</h1>
        <p>Certified profiles from the runtime or artifact index.</p>
      </header>

      {profiles.isError ? <ErrorPanel error={profiles.error} /> : null}

      {profiles.isSuccess && profiles.data.length === 0 ? (
        <EmptyState title="No profiles loaded">
          <p>There are no indexed or live profiles to display.</p>
          <ol>
            <li>Package a certified profile bundle with forge/CLI.</li>
            <li>
              Place it under a registered artifact root or load it into the
              runtime.
            </li>
            <li>Refresh this page after the API indexes the bundle.</li>
          </ol>
        </EmptyState>
      ) : null}

      {profiles.isSuccess && profiles.data.length > 0 ? (
        <div className="panel" style={{ overflowX: "auto" }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Profile</th>
                <th>Model</th>
                <th>State</th>
                <th>Eligible</th>
                <th>Quality</th>
                <th>Cert p99</th>
                <th>Online p99</th>
                <th>RSS</th>
                <th>Provider</th>
                <th>Flags</th>
              </tr>
            </thead>
            <tbody>
              {profiles.data.map((p) => (
                <tr key={p.profile_id}>
                  <td>
                    <div className="mono">{p.profile_id}</div>
                    <div>{p.label ?? "—"}</div>
                  </td>
                  <td className="mono">{p.model_hash_prefix ?? "—"}</td>
                  <td>{p.state}</td>
                  <td>
                    <StatusBadge
                      tone={p.eligible ? "ok" : "warn"}
                      label={p.eligible ? "eligible" : "ineligible"}
                    />
                    {p.rejection_reasons.length > 0 ? (
                      <ul>
                        {p.rejection_reasons.map((r) => (
                          <li key={r} className="mono">
                            {r}
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </td>
                  <td className="mono">
                    {p.certified_quality != null ? p.certified_quality : "—"}
                  </td>
                  <td className="mono">
                    {p.certified_p99_ms != null
                      ? `${p.certified_p99_ms} ms`
                      : "—"}
                  </td>
                  <td className="mono">
                    {p.online_p99_ms != null ? `${p.online_p99_ms} ms` : "—"}
                  </td>
                  <td className="mono">
                    {p.peak_rss_bytes != null ? `${p.peak_rss_bytes} B` : "—"}
                  </td>
                  <td>{p.provider ?? "—"}</td>
                  <td>
                    {p.active ? "active " : ""}
                    {p.pinned ? "pinned" : ""}
                    {!p.active && !p.pinned ? "—" : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {profiles.isLoading ? <p>Loading profiles…</p> : null}
    </div>
  );
}
