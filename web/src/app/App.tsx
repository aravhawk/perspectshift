import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { ApiConfigProvider } from "@/api/ApiConfigProvider";
import { ApiProvider } from "@/api/ApiProvider";
import { AppLayout } from "@/components/Layout";
import { SessionTokenProvider } from "@/hooks/useSessionToken";
import { TimeProvider } from "@/hooks/useTimeFormat";
import { BundleInspectorPage } from "@/pages/BundleInspectorPage";
import { HealthPage } from "@/pages/HealthPage";
import { LatencyPage } from "@/pages/LatencyPage";
import { OverviewPage } from "@/pages/OverviewPage";
import { ProfilesPage } from "@/pages/ProfilesPage";
import { BenchmarkRunsPage } from "@/pages/BenchmarkRunsPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { SwitchHistoryPage } from "@/pages/SwitchHistoryPage";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000,
      refetchOnWindowFocus: false,
    },
  },
});

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ApiConfigProvider>
          <SessionTokenProvider>
            <ApiProvider>
              <TimeProvider>
                <Routes>
                  <Route element={<AppLayout />}>
                    <Route index element={<OverviewPage />} />
                    <Route path="profiles" element={<ProfilesPage />} />
                    <Route path="latency" element={<LatencyPage />} />
                    <Route path="health" element={<HealthPage />} />
                    <Route path="switches" element={<SwitchHistoryPage />} />
                    <Route path="bundle" element={<BundleInspectorPage />} />
                    <Route path="runs" element={<BenchmarkRunsPage />} />
                    <Route path="settings" element={<SettingsPage />} />
                    <Route path="*" element={<Navigate to="/" replace />} />
                  </Route>
                </Routes>
              </TimeProvider>
            </ApiProvider>
          </SessionTokenProvider>
        </ApiConfigProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
