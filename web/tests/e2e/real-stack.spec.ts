import { test, expect } from "@playwright/test";

/**
 * CANONICAL real-stack browser E2E (no API route interception / mocking).
 *
 * Gate: PERCEPTSHIFT_REAL_STACK_E2E=1
 * Harness: scripts/browser-real-stack-acceptance.sh
 *
 * Requires a live ROS runtime graph + FastAPI with enable_ros + built console.
 * Asserts a real frame → ORT inference transaction (not mere health heartbeats).
 */

const enabled = process.env.PERCEPTSHIFT_REAL_STACK_E2E === "1";
const apiBase = process.env.PERCEPTSHIFT_API_BASE ?? "http://127.0.0.1:8741";
const mutationToken = process.env.PERCEPTSHIFT_API_MUTATION_TOKEN ?? "";
const baselineSeq = Number(process.env.PERCEPTSHIFT_BASELINE_INFERENCE_SEQ ?? "0");
const baselineTraceCount = Number(process.env.PERCEPTSHIFT_BASELINE_TRACE_COUNT ?? "0");
const requireInference = process.env.PERCEPTSHIFT_REQUIRE_INFERENCE !== "0";

type TelemetryEvent = {
  event_type?: string;
  sequence_number?: number;
  payload?: {
    sequence_id?: number;
    profile_id?: string;
    total_ms?: number | null;
  };
  timestamp?: string;
};

async function fetchRecent(page: { request: { get: (url: string) => Promise<{ ok: () => boolean; json: () => Promise<{ events?: TelemetryEvent[] }> }> } }) {
  const recent = await page.request.get(`${apiBase}/api/v1/telemetry/recent?limit=200`);
  expect(recent.ok()).toBeTruthy();
  const body = await recent.json();
  return (body.events ?? []) as TelemetryEvent[];
}

function inferenceTraces(events: TelemetryEvent[]): TelemetryEvent[] {
  return events.filter((e) => e.event_type === "inference_trace_summary");
}

test.describe("canonical real-stack console E2E", () => {
  test.beforeEach(() => {
    test.skip(
      !enabled,
      "UNAVAILABLE: set PERCEPTSHIFT_REAL_STACK_E2E=1 and use scripts/browser-real-stack-acceptance.sh",
    );
  });

  test("connected runtime health, real ORT inference, policy, and pin via live API", async ({
    page,
  }) => {
    const errors: string[] = [];
    page.on("pageerror", (err) => errors.push(String(err)));

    await page.goto("/");
    await expect(page.getByText(/Overview/i).first()).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText(/Runtime connected|connected/i).first()).toBeVisible({
      timeout: 60_000,
    });

    const statusResp = await page.request.get(`${apiBase}/api/v1/runtime/status`);
    expect(statusResp.ok()).toBeTruthy();
    const status = await statusResp.json();
    expect(status.connected).toBe(true);
    expect(status.mode).toBe("ros");

    const healthResp = await page.request.get(`${apiBase}/api/v1/runtime/health`);
    expect(healthResp.ok()).toBeTruthy();
    const health = await healthResp.json();
    expect(health.state).toBeTruthy();

    // Post-frame ORT inference evidence (causally after harness-injected Image).
    let postInference: TelemetryEvent | undefined;
    const deadline = Date.now() + 60_000;
    while (Date.now() < deadline) {
      const events = await fetchRecent(page);
      const traces = inferenceTraces(events);
      postInference = traces.find((e) => {
        const seq = Number(e.payload?.sequence_id ?? 0);
        return seq > baselineSeq || traces.length > baselineTraceCount;
      });
      if (postInference) break;
      await page.waitForTimeout(400);
    }

    if (requireInference) {
      expect(
        postInference,
        "expected inference_trace_summary after injected frame (not health/profile heartbeat alone)",
      ).toBeTruthy();
      const seq = Number(postInference!.payload?.sequence_id ?? 0);
      expect(seq, "sequence_id must advance past baseline").toBeGreaterThan(baselineSeq);
      expect(String(postInference!.payload?.profile_id ?? ""), "executed profile id").not.toEqual("");
    } else {
      // Negative harness mode: publisher disabled — inference assertion must fail.
      expect(
        postInference,
        "negative check: without publisher, inference evidence must be absent",
      ).toBeFalsy();
    }

    test.skip(
      !mutationToken,
      "UNAVAILABLE: PERCEPTSHIFT_API_MUTATION_TOKEN required for mutation steps",
    );

    const headers = {
      Authorization: `Bearer ${mutationToken}`,
      "Content-Type": "application/json",
    };
    const policyPatch = await page.request.patch(`${apiBase}/api/v1/runtime/policy`, {
      headers,
      data: { deadline_ms: 42.0 },
    });
    expect(policyPatch.ok()).toBeTruthy();
    const policy = await policyPatch.json();
    expect(policy.deadline_ms).toBe(42.0);

    const profilesResp = await page.request.get(`${apiBase}/api/v1/profiles`);
    expect(profilesResp.ok()).toBeTruthy();
    const profiles = await profilesResp.json();
    if (Array.isArray(profiles) && profiles.length > 0) {
      const profileId = profiles[0].profile_id as string;
      const pin = await page.request.post(`${apiBase}/api/v1/profiles/${profileId}/pin`, {
        headers,
        data: { confirm: true },
      });
      expect(
        pin.ok(),
        `pin failed: status=${pin.status()} body=${await pin.text()}`,
      ).toBeTruthy();
      const clear = await page.request.delete(`${apiBase}/api/v1/profiles/pin`, { headers });
      expect(
        clear.ok(),
        `clear pin failed: status=${clear.status()} body=${await clear.text()}`,
      ).toBeTruthy();
    }

    const status2 = await (await page.request.get(`${apiBase}/api/v1/runtime/status`)).json();
    expect(status2.connected).toBe(true);
    expect(errors, errors.join("\n")).toEqual([]);
  });
});
