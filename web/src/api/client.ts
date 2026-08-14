import type { ApiErrorBody } from "@/types/api";

export const DEFAULT_API_BASE_URL = "";

export class ApiClientError extends Error {
  readonly code: string;
  readonly correlationId: string;
  readonly retryable: boolean;
  readonly remediation: string | null;
  readonly status: number;

  constructor(status: number, body: ApiErrorBody) {
    super(body.error.message);
    this.name = "ApiClientError";
    this.status = status;
    this.code = body.error.code;
    this.correlationId = body.error.correlation_id;
    this.retryable = body.error.retryable;
    this.remediation = body.error.remediation;
  }
}

export type ApiClientOptions = {
  baseUrl?: string;
  getToken?: () => string | null;
};

function redactSecrets(text: string): string {
  return text.replace(/(bearer\s+)[^\s]+/gi, "$1[redacted]");
}

export function createApiClient(options: ApiClientOptions = {}) {
  const baseUrl = (options.baseUrl ?? DEFAULT_API_BASE_URL).replace(/\/$/, "");

  async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const headers = new Headers(init.headers);
    if (!headers.has("Accept")) {
      headers.set("Accept", "application/json");
    }
    const token = options.getToken?.();
    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }
    let response: Response;
    try {
      response = await fetch(`${baseUrl}${path}`, { ...init, headers });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Network error";
      throw new ApiClientError(0, {
        error: {
          code: "API_UNREACHABLE",
          message: redactSecrets(message),
          correlation_id: "client",
          retryable: true,
          details: {},
          remediation: `Start perceptshift-api and ensure the console API base URL is reachable (${baseUrl || DEFAULT_API_BASE_URL})`,
        },
      });
    }

    if (!response.ok) {
      let body: ApiErrorBody;
      try {
        body = (await response.json()) as ApiErrorBody;
      } catch {
        body = {
          error: {
            code: "HTTP_ERROR",
            message: `HTTP ${response.status}`,
            correlation_id: "client",
            retryable: response.status >= 500,
            details: {},
            remediation: null,
          },
        };
      }
      throw new ApiClientError(response.status, body);
    }

    if (response.status === 204) {
      return undefined as T;
    }
    return (await response.json()) as T;
  }

  return {
    baseUrl,
    get: <T>(path: string) => request<T>(path),
    patch: <T>(path: string, body: unknown) =>
      request<T>(path, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }),
    post: <T>(path: string, body: unknown) =>
      request<T>(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }),
    delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
  };
}

export type ApiClient = ReturnType<typeof createApiClient>;
