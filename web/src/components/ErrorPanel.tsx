import { ApiClientError } from "@/api/client";

export function ErrorPanel({ error }: { error: unknown }) {
  if (error instanceof ApiClientError) {
    return (
      <div className="banner banner-bad" role="alert">
        <strong>{error.code}</strong>
        <p>{error.message}</p>
        {error.remediation ? <p>{error.remediation}</p> : null}
        <p className="mono">correlation: {error.correlationId}</p>
      </div>
    );
  }
  const message = error instanceof Error ? error.message : "Unexpected error";
  return (
    <div className="banner banner-bad" role="alert">
      <p>{message}</p>
    </div>
  );
}
