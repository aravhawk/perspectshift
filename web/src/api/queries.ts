import { useQuery } from "@tanstack/react-query";
import { useApi } from "@/api/ApiProvider";
import type {
  BundleInfo,
  Capabilities,
  ProfileSummary,
  Readyz,
  RunSummary,
  RuntimeHealth,
  RuntimePolicy,
  RuntimeStatus,
  SwitchEvent,
  TelemetryMetrics,
  TelemetryRecent,
  VersionInfo,
} from "@/types/api";

export function useHealthz() {
  const api = useApi();
  return useQuery({
    queryKey: ["healthz"],
    queryFn: () => api.get<{ status: string }>("/api/v1/healthz"),
    retry: 1,
    refetchInterval: 5000,
  });
}

export function useReadyz() {
  const api = useApi();
  return useQuery({
    queryKey: ["readyz"],
    queryFn: () => api.get<Readyz>("/api/v1/readyz"),
    retry: 1,
    refetchInterval: 5000,
  });
}

export function useVersion() {
  const api = useApi();
  return useQuery({
    queryKey: ["version"],
    queryFn: () => api.get<VersionInfo>("/api/v1/version"),
  });
}

export function useCapabilities() {
  const api = useApi();
  return useQuery({
    queryKey: ["capabilities"],
    queryFn: () => api.get<Capabilities>("/api/v1/capabilities"),
  });
}

export function useRuntimeStatus() {
  const api = useApi();
  return useQuery({
    queryKey: ["runtime", "status"],
    queryFn: () => api.get<RuntimeStatus>("/api/v1/runtime/status"),
    refetchInterval: 2000,
  });
}

export function useRuntimeHealth() {
  const api = useApi();
  return useQuery({
    queryKey: ["runtime", "health"],
    queryFn: () => api.get<RuntimeHealth>("/api/v1/runtime/health"),
    refetchInterval: 2000,
  });
}

export function useRuntimePolicy() {
  const api = useApi();
  return useQuery({
    queryKey: ["runtime", "policy"],
    queryFn: () => api.get<RuntimePolicy>("/api/v1/runtime/policy"),
  });
}

export function useProfiles() {
  const api = useApi();
  return useQuery({
    queryKey: ["profiles"],
    queryFn: () => api.get<ProfileSummary[]>("/api/v1/profiles"),
  });
}

export function useTelemetryRecent() {
  const api = useApi();
  return useQuery({
    queryKey: ["telemetry", "recent"],
    queryFn: () => api.get<TelemetryRecent>("/api/v1/telemetry/recent"),
    refetchInterval: 3000,
  });
}

export function useTelemetryMetrics() {
  const api = useApi();
  return useQuery({
    queryKey: ["telemetry", "metrics"],
    queryFn: () => api.get<TelemetryMetrics>("/api/v1/telemetry/metrics"),
    refetchInterval: 3000,
  });
}

export function useSwitchHistory() {
  const api = useApi();
  return useQuery({
    queryKey: ["telemetry", "switches"],
    queryFn: () => api.get<SwitchEvent[]>("/api/v1/telemetry/switches"),
  });
}

export function useCurrentBundle() {
  const api = useApi();
  return useQuery({
    queryKey: ["bundles", "current"],
    queryFn: () => api.get<BundleInfo>("/api/v1/bundles/current"),
  });
}

export function useRuns() {
  const api = useApi();
  return useQuery({
    queryKey: ["runs"],
    queryFn: () => api.get<RunSummary[]>("/api/v1/runs"),
  });
}
