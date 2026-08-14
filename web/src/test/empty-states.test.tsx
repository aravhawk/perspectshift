import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { OverviewPage } from "@/pages/OverviewPage";

vi.mock("@/api/queries", () => ({
  useHealthz: () => ({ isError: true, error: new Error("unreachable"), isSuccess: false }),
  useReadyz: () => ({ data: undefined }),
  useRuntimeStatus: () => ({ data: undefined }),
  useRuntimeHealth: () => ({ data: undefined }),
  useTelemetryMetrics: () => ({ data: undefined }),
  useCapabilities: () => ({ data: undefined }),
}));

describe("Overview empty/disconnected", () => {
  it("explains how to connect without fake metrics", () => {
    const client = new QueryClient();
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <OverviewPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(screen.getByText(/API disconnected/i)).toBeInTheDocument();
    expect(screen.getByText(/No sample metrics are shown/i)).toBeInTheDocument();
  });
});
