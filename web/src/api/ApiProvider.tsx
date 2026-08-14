import { createContext, useContext, useMemo, type ReactNode } from "react";
import { useApiConfig } from "@/api/ApiConfigProvider";
import { createApiClient, type ApiClient } from "@/api/client";
import { useSessionToken } from "@/hooks/useSessionToken";

const ApiContext = createContext<ApiClient | null>(null);

export function ApiProvider({ children }: { children: ReactNode }) {
  const { token } = useSessionToken();
  const { baseUrl } = useApiConfig();
  const client = useMemo(
    () =>
      createApiClient({
        baseUrl,
        getToken: () => token,
      }),
    [token, baseUrl],
  );
  return <ApiContext.Provider value={client}>{children}</ApiContext.Provider>;
}

export function useApi(): ApiClient {
  const ctx = useContext(ApiContext);
  if (!ctx) {
    throw new Error("useApi must be used within ApiProvider");
  }
  return ctx;
}
