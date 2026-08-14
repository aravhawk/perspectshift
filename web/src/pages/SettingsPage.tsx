import { useCapabilities } from "@/api/queries";
import { useApiConfig } from "@/api/ApiConfigProvider";
import { EmptyState } from "@/components/EmptyState";
import { ErrorPanel } from "@/components/ErrorPanel";
import { useSessionToken } from "@/hooks/useSessionToken";

export function SettingsPage() {
  const caps = useCapabilities();
  const { baseUrl, setBaseUrl } = useApiConfig();
  const { token, setToken } = useSessionToken();
  return (
    <div>
      <header className="page-header">
        <h1>Settings</h1>
        <p>Read-only effective API settings by default. Mutation token stays in session memory.</p>
      </header>
      <section className="panel">
        <h2>API connection</h2>
        <label htmlFor="api-base">API base URL</label>
        <input
          id="api-base"
          value={baseUrl}
          onChange={(e) => setBaseUrl(e.target.value)}
          autoComplete="off"
        />
        <label htmlFor="api-token">Mutation token (session only)</label>
        <input
          id="api-token"
          type="password"
          value={token ?? ""}
          onChange={(e) => setToken(e.target.value || null)}
          autoComplete="off"
          placeholder="empty = read-only"
        />
      </section>
      {caps.isError ? (
        <EmptyState title="Capabilities unavailable">
          <ErrorPanel error={caps.error} />
        </EmptyState>
      ) : caps.data ? (
        <section className="panel">
          <h2>Effective capabilities</h2>
          <pre>{JSON.stringify(caps.data, null, 2)}</pre>
        </section>
      ) : (
        <p role="status">Loading capabilities…</p>
      )}
    </div>
  );
}
