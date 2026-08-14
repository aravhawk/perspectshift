import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

type TimeMode = "utc" | "local";

type TimeContextValue = {
  mode: TimeMode;
  setMode: (mode: TimeMode) => void;
  format: (iso: string | null | undefined) => string;
};

const TimeContext = createContext<TimeContextValue | null>(null);

export function TimeProvider({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<TimeMode>("utc");
  const value = useMemo<TimeContextValue>(
    () => ({
      mode,
      setMode,
      format: (iso) => {
        if (!iso) {
          return "—";
        }
        const date = new Date(iso);
        if (Number.isNaN(date.getTime())) {
          return iso;
        }
        return mode === "utc" ? date.toISOString() : date.toLocaleString();
      },
    }),
    [mode],
  );
  return <TimeContext.Provider value={value}>{children}</TimeContext.Provider>;
}

export function useTimeFormat() {
  const ctx = useContext(TimeContext);
  if (!ctx) {
    throw new Error("useTimeFormat must be used within TimeProvider");
  }
  return ctx;
}
