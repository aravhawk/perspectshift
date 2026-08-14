import { NavLink, Outlet } from "react-router-dom";
import { useHealthz } from "@/api/queries";
import { StatusBadge } from "@/components/StatusBadge";
import { useTimeFormat } from "@/hooks/useTimeFormat";

const links = [
  { to: "/", label: "Overview", end: true },
  { to: "/profiles", label: "Profiles" },
  { to: "/latency", label: "Latency" },
  { to: "/health", label: "Health" },
  { to: "/switches", label: "Switch history" },
  { to: "/bundle", label: "Bundle inspector" },
  { to: "/runs", label: "Benchmark runs" },
  { to: "/settings", label: "Settings" },
];

export function AppLayout() {
  const health = useHealthz();
  const { mode, setMode } = useTimeFormat();
  const apiTone =
    health.isSuccess ? "ok" : health.isError ? "bad" : "unknown";
  const apiLabel = health.isSuccess
    ? "API connected"
    : health.isError
      ? "API disconnected"
      : "API checking";

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">PerceptShift</div>
          <div className="brand-sub">operational console</div>
        </div>
        <nav className="nav" aria-label="Primary">
          {links.map((link) => (
            <NavLink key={link.to} to={link.to} end={link.end}>
              {link.label}
            </NavLink>
          ))}
        </nav>
        <div>
          <StatusBadge tone={apiTone} label={apiLabel} />
          <div style={{ marginTop: "0.75rem" }}>
            <label htmlFor="tz-mode" className="metric-label">
              Timestamps
            </label>
            <select
              id="tz-mode"
              value={mode}
              onChange={(e) => setMode(e.target.value as "utc" | "local")}
            >
              <option value="utc">UTC</option>
              <option value="local">Local</option>
            </select>
          </div>
        </div>
      </aside>
      <main className="main">
        <Outlet />
      </main>
    </div>
  );
}
