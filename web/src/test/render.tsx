import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";
import { ApiConfigProvider } from "@/api/ApiConfigProvider";
import { ApiProvider } from "@/api/ApiProvider";
import { SessionTokenProvider } from "@/hooks/useSessionToken";
import { TimeProvider } from "@/hooks/useTimeFormat";

export function renderWithProviders(ui: ReactNode, { route = "/" } = {}) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <ApiConfigProvider>
        <SessionTokenProvider>
          <ApiProvider>
            <TimeProvider>
              <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
            </TimeProvider>
          </ApiProvider>
        </SessionTokenProvider>
      </ApiConfigProvider>
    </QueryClientProvider>,
  );
}
