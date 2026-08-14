# API reference

The local API (`perceptshift_api`) defaults to loopback bind.

Modes:

- **artifact** — read run artifacts without live ROS
- **ros_bridge** — bridge live runtime state when ROS is available

The ROS bridge creates a real `rclpy` node when enabled. It subscribes to
`/perceptshift_runtime/health`, `profiles`, `switches`, `traces`, and
`control_hold_request`, and calls `GetRuntimeStatus`, `UpdateRuntimePolicy`,
`PinProfile`, `ClearProfilePin`, and `RequestRecovery` services. Local state
is updated only after successful service responses. Timeouts and rejections
map to typed API errors (`ROS_TIMEOUT`, `ROS_SERVICE_REJECTED`, …).

Mutations require a bearer token from a protected credential file. CORS/origin policy is strict. WebSocket clients and queues are bounded.

Generate OpenAPI from the running service or package entrypoint; do not hand-maintain divergent copies.

## Console E2E

- Baseline (no ROS): `pnpm --dir web test:e2e -- tests/e2e/real-api.spec.ts`
- **Canonical** real-stack gate: `./scripts/run-real-stack-e2e.sh`
  (`PERCEPTSHIFT_REAL_STACK_E2E=1`, no API route interception)
