import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

type SessionTokenValue = {
  token: string | null;
  setToken: (value: string | null) => void;
  clearToken: () => void;
  hasToken: boolean;
};

const SessionTokenContext = createContext<SessionTokenValue | null>(null);

/**
 * Mutation token kept in session memory only (not localStorage by default).
 */
export function SessionTokenProvider({ children }: { children: ReactNode }) {
  const [token, setTokenState] = useState<string | null>(null);

  const setToken = useCallback((value: string | null) => {
    setTokenState(value && value.trim() ? value.trim() : null);
  }, []);

  const clearToken = useCallback(() => setTokenState(null), []);

  const value = useMemo(
    () => ({
      token,
      setToken,
      clearToken,
      hasToken: Boolean(token),
    }),
    [token, setToken, clearToken],
  );

  return (
    <SessionTokenContext.Provider value={value}>{children}</SessionTokenContext.Provider>
  );
}

export function useSessionToken(): SessionTokenValue {
  const ctx = useContext(SessionTokenContext);
  if (!ctx) {
    throw new Error("useSessionToken must be used within SessionTokenProvider");
  }
  return ctx;
}
