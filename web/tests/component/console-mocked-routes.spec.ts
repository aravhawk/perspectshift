import { test, expect } from "@playwright/test";

test.describe("console smoke against mocked API", () => {
  test.beforeEach(async ({ page }) => {
    await page.route("**/api/v1/**", async (route) => {
      const url = route.request().url();
      const json = (body: unknown) =>
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(body),
        });

      if (url.includes("/healthz")) {
        await json({ status: "ok" });
        return;
      }
      if (url.includes("/runtime/status")) {
        await json({
          connected: false,
          mode: "artifact_store",
          active_profile_id: null,
          control_hold: false,
          deadline_ms: null,
          source_freshness: null,
          unavailable: {
            runtime: {
              available: false,
              reason_code: "ROS_DISABLED",
              message: "ROS bridge disabled",
            },
          },
        });
        return;
      }
      if (url.includes("/runtime/health")) {
        await json({
          state: "artifact_store",
          reason_codes: ["ROS_DISABLED"],
          control_hold: false,
          unavailable: {},
        });
        return;
      }
      if (url.includes("/profiles")) {
        await json([]);
        return;
      }
      if (url.includes("/runs")) {
        await json([]);
        return;
      }
      if (url.includes("/telemetry/")) {
        await json({
          events: [],
          dropped_event_count: 0,
          sample_count: 0,
          p50_ms: null,
          p99_ms: null,
          deadline_misses: 0,
          unavailable: {
            metrics: {
              available: false,
              reason_code: "TELEMETRY_EMPTY",
              message: "No inference telemetry",
            },
          },
        });
        return;
      }
      if (url.includes("/bundles/current")) {
        await json({
          integrity_status: "unavailable",
          signature_status: "unavailable",
          profiles: [],
          file_hashes: {},
          provenance: {},
          unavailable: {
            bundle: {
              available: false,
              reason_code: "BUNDLE_NOT_FOUND",
              message: "No current profile bundle",
            },
          },
        });
        return;
      }
      if (
        url.includes("/capabilities") ||
        url.includes("/version") ||
        url.includes("/readyz") ||
        url.includes("/policy")
      ) {
        await json({
          product: "perceptshift",
          api_version: "0.1.0",
          schema_version: "1.0",
          ready: true,
          database: true,
          ros: "ROS_DISABLED",
          reasons: [],
          mutations_enabled: false,
          ros_bridge: "ROS_DISABLED",
          artifact_store: true,
          websocket_telemetry: true,
          cors_origins: [],
          bind_host: "127.0.0.1",
          max_request_bytes: 1048576,
          deadline_ms: null,
          pinned_profile_id: null,
          auto_switch_enabled: true,
          recovery_enabled: true,
          source: "default",
        });
        return;
      }
      await route.fulfill({ status: 404, body: "missing mock" });
    });
  });

  test("overview shows brand and disconnected runtime without fake charts", async ({
    page,
  }) => {
    await page.goto("/");
    await expect(page.getByText("PerceptShift").first()).toBeVisible();
    await expect(page.getByRole("heading", { name: "Overview", exact: true })).toBeVisible();
    await expect(
      page.getByText(/Runtime not connected|ROS_DISABLED|RUNTIME_DISCONNECTED/i).first(),
    ).toBeVisible();
    await expect(page.getByText(/sample profile|fake p99/i)).toHaveCount(0);
  });

  test("profiles empty state explains how to connect", async ({ page }) => {
    await page.goto("/profiles");
    await expect(page.getByRole("heading", { name: "Profiles", exact: true })).toBeVisible();
    await expect(page.getByText(/No profiles loaded/i)).toBeVisible();
  });
});
