import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiClientError } from "@/api/client";
import { ApiConfigProvider } from "@/api/ApiConfigProvider";
import { ApiProvider } from "@/api/ApiProvider";
import { SessionTokenProvider } from "@/hooks/useSessionToken";
import { TimeProvider } from "@/hooks/useTimeFormat";

const unreachable = new ApiClientError(0, {
  error: {
    code: "API_UNREACHABLE",
    message: "Failed to fetch",
    correlation_id: "client",
    retryable: true,
    details: {},
    remediation: "Start perceptshift-api",
  },
});

const mocks = vi.hoisted(() => ({
  useHealthz: vi.fn(),
  useReadyz: vi.fn(),
  useRuntimeStatus: vi.fn(),
  useRuntimeHealth: vi.fn(),
  useTelemetryMetrics: vi.fn(),
  useCapabilities: vi.fn(),
  useProfiles: vi.fn(),
}));

vi.mock("@/api/queries", () => mocks);

import { OverviewPage } from "@/pages/OverviewPage";
import { ProfilesPage } from "@/pages/ProfilesPage";
import { HealthPage } from "@/pages/HealthPage";

function wrap(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ApiConfigProvider>
        <SessionTokenProvider>
          <ApiProvider>
            <TimeProvider>
              <MemoryRouter>{ui}</MemoryRouter>
            </TimeProvider>
          </ApiProvider>
        </SessionTokenProvider>
      </ApiConfigProvider>
    </QueryClientProvider>,
  );
}

describe("empty / error / disconnected states", () => {
  beforeEach(() => {
    mocks.useHealthz.mockReset();
    mocks.useReadyz.mockReset();
    mocks.useRuntimeStatus.mockReset();
    mocks.useRuntimeHealth.mockReset();
    mocks.useTelemetryMetrics.mockReset();
    mocks.useCapabilities.mockReset();
    mocks.useProfiles.mockReset();
  });

  it("overview explains API disconnect without fake metrics", () => {
    mocks.useHealthz.mockReturnValue({
      isError: true,
      isSuccess: false,
      error: unreachable,
    });
    mocks.useReadyz.mockReturnValue({ data: undefined });
    mocks.useRuntimeStatus.mockReturnValue({ data: undefined });
    mocks.useRuntimeHealth.mockReturnValue({ data: undefined });
    mocks.useTelemetryMetrics.mockReturnValue({ data: undefined });
    mocks.useCapabilities.mockReturnValue({ data: undefined });

    wrap(<OverviewPage />);
    expect(screen.getByText(/API disconnected/i)).toBeInTheDocument();
    expect(screen.getByText(/No sample metrics are shown/i)).toBeInTheDocument();
    expect(screen.queryByText(/seeded/i)).not.toBeInTheDocument();
  });

  it("profiles shows API error state", () => {
    mocks.useProfiles.mockReturnValue({
      isError: true,
      isSuccess: false,
      isLoading: false,
      data: undefined,
      error: unreachable,
    });
    wrap(<ProfilesPage />);
    expect(screen.getAllByRole("alert").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/API_UNREACHABLE/i).length).toBeGreaterThan(0);
  });

  it("health shows runtime disconnected reason code", () => {
    mocks.useRuntimeHealth.mockReturnValue({
      isError: false,
      data: {
        state: "unavailable",
        reason_codes: ["ROS_DISABLED"],
        control_hold: false,
        unavailable: {},
      },
      refetch: vi.fn(),
    });
    mocks.useRuntimeStatus.mockReturnValue({
      data: {
        connected: false,
        mode: "artifact_store",
        unavailable: {
          runtime: {
            available: false,
            reason_code: "ROS_DISABLED",
            message: "ROS bridge disabled",
          },
        },
      },
      refetch: vi.fn(),
    });
    mocks.useCapabilities.mockReturnValue({
      data: { mutations_enabled: false },
    });

    wrap(<HealthPage />);
    expect(screen.getByText(/Runtime disconnected/i)).toBeInTheDocument();
    expect(screen.getAllByText("ROS_DISABLED").length).toBeGreaterThan(0);
  });
});
