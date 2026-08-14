import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { DEFAULT_API_BASE_URL } from "@/api/client";

const STORAGE_KEY = "perceptshift.console.apiBaseUrl";

type ApiConfigValue = {
  baseUrl: string;
  setBaseUrl: (url: string) => void;
  resetBaseUrl: () => void;
};

const ApiConfigContext = createContext<ApiConfigValue | null>(null);

function readStoredBaseUrl(): string {
  try {
    const stored = sessionStorage.getItem(STORAGE_KEY);
    if (stored && stored.trim()) {
      return stored.trim().replace(/\/$/, "");
    }
  } catch {
    // sessionStorage may be unavailable
  }
  return DEFAULT_API_BASE_URL;
}

export function ApiConfigProvider({ children }: { children: ReactNode }) {
  const [baseUrl, setBaseUrlState] = useState(readStoredBaseUrl);

  const setBaseUrl = useCallback((url: string) => {
    const next = url.trim().replace(/\/$/, "") || DEFAULT_API_BASE_URL;
    setBaseUrlState(next);
    try {
      sessionStorage.setItem(STORAGE_KEY, next);
    } catch {
      // ignore
    }
  }, []);

  const resetBaseUrl = useCallback(() => {
    setBaseUrlState(DEFAULT_API_BASE_URL);
    try {
      sessionStorage.removeItem(STORAGE_KEY);
    } catch {
      // ignore
    }
  }, []);

  const value = useMemo(
    () => ({ baseUrl, setBaseUrl, resetBaseUrl }),
    [baseUrl, setBaseUrl, resetBaseUrl],
  );

  return <ApiConfigContext.Provider value={value}>{children}</ApiConfigContext.Provider>;
}

export function useApiConfig(): ApiConfigValue {
  const ctx = useContext(ApiConfigContext);
  if (!ctx) {
    throw new Error("useApiConfig must be used within ApiConfigProvider");
  }
  return ctx;
}
