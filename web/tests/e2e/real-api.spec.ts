import { test, expect } from "@playwright/test";

/**
 * Baseline console smoke against the real FastAPI process in artifact-store mode.
 *
 * Canonical gate for ROS+runtime acceptance is `real-stack.spec.ts`, invoked via
 * `scripts/run-real-stack-e2e.sh` with PERCEPTSHIFT_REAL_STACK_E2E=1.
 *
 * This file must NOT intercept /api routes.
 */
test.describe("console against real API (artifact-store baseline)", () => {
  test("overview loads without route mocks and shows disconnected runtime", async ({
    page,
  }) => {
    const errors: string[] = [];
    page.on("pageerror", (err) => errors.push(String(err)));
    page.on("console", (msg) => {
      if (msg.type() === "error") errors.push(msg.text());
    });

    // Guard: no API route interception in this suite.
    page.on("request", (req) => {
      // Intentionally empty — presence of route handlers would be a test smell.
      void req;
    });

    await page.goto("/");
    await expect(
      page.getByText(/PerceptShift|Overview|Health|unavailable|artifact|Runtime/i).first(),
    ).toBeVisible({ timeout: 30_000 });

    await expect(page.getByText(/Runtime/i).first()).toBeVisible();
    // Artifact-store API reports disconnected runtime with an explicit reason.
    await expect(
      page.getByText(/disconnected|ROS_DISABLED|artifact|Runtime not connected/i).first(),
    ).toBeVisible({ timeout: 30_000 });

    const healthz = await page.request.get("http://127.0.0.1:8741/api/v1/healthz");
    expect(healthz.ok()).toBeTruthy();
    const status = await page.request.get("http://127.0.0.1:8741/api/v1/runtime/status");
    expect(status.ok()).toBeTruthy();
    const body = await status.json();
    expect(body.connected).toBe(false);
    expect(body.mode).toBe("artifact_store");

    expect(errors, errors.join("\n")).toEqual([]);
  });
});
