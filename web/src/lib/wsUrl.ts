/** Derive WebSocket telemetry URL from an HTTP API base. */
export function telemetryWsUrl(apiBaseUrl: string): string {
  const trimmed = apiBaseUrl.replace(/\/$/, "");
  if (!trimmed) {
    const proto = typeof location !== "undefined" && location.protocol === "https:" ? "wss" : "ws";
    const host = typeof location !== "undefined" ? location.host : "127.0.0.1:8741";
    return `${proto}://${host}/api/v1/telemetry/stream`;
  }
  try {
    const url = new URL(trimmed);
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
    url.pathname = "/api/v1/telemetry/stream";
    url.search = "";
    url.hash = "";
    return url.toString();
  } catch {
    return "ws://127.0.0.1:8741/api/v1/telemetry/stream";
  }
}
