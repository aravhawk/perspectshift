import { defineConfig, devices } from "@playwright/test";

/**
 * Default webServer runs the API in artifact-store mode (enable_ros=false).
 * Canonical ROS+runtime acceptance is gated separately:
 *   PERCEPTSHIFT_REAL_STACK_E2E=1 ./scripts/run-real-stack-e2e.sh
 * which runs tests/e2e/real-stack.spec.ts against a live stack (no API mocks).
 */
const apiCmd =
  "PERCEPTSHIFT_API_ENABLE_ROS=false PERCEPTSHIFT_API_HOST=127.0.0.1 PERCEPTSHIFT_API_PORT=8741 " +
  "uv run --directory .. python -m perceptshift_api --host 127.0.0.1 --port 8741";

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  use: {
    baseURL: process.env.PERCEPTSHIFT_CONSOLE_URL ?? "http://127.0.0.1:5173",
    trace: "on-first-retry",
  },
  webServer: process.env.PERCEPTSHIFT_REAL_STACK_E2E === "1"
    ? undefined
    : [
        {
          command: apiCmd,
          url: "http://127.0.0.1:8741/api/v1/healthz",
          reuseExistingServer: !process.env.CI,
          timeout: 120_000,
        },
        {
          command: "pnpm vite --host 127.0.0.1 --port 5173",
          url: "http://127.0.0.1:5173",
          reuseExistingServer: !process.env.CI,
          timeout: 120_000,
        },
      ],
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
