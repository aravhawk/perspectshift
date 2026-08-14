# perceptshift-api

Local operational API for PerceptShift.

Binds to `127.0.0.1` by default. Mutations are disabled unless a token is
resolved from, in order, `PERCEPTSHIFT_API_MUTATION_TOKEN`,
`PERCEPTSHIFT_API_MUTATION_TOKEN_FILE`, or systemd
`$CREDENTIALS_DIRECTORY/perceptshift-api-token`. Artifact-store-only mode works
without ROS; the ROS bridge reports graceful unavailability when rclpy or
the graph is absent.

When `PERCEPTSHIFT_API_ENABLE_ROS=true` and `rclpy` + `perceptshift_msgs`
are importable, the bridge creates a real rclpy node, subscribes to
`/perceptshift_runtime/{health,profiles,switches,traces,control_hold_request}`,
and calls mutation services only after ROS responses succeed.

## Run

```bash
uv run --directory python/perceptshift_api perceptshift-api
```

## Test

```bash
# Unit + API tests (ROS graph tests skip with UNAVAILABLE unless ROS_DISTRO=jazzy)
uv run --directory python/perceptshift_api --extra dev pytest

# Real ROS graph tests only (Jazzy + sourced workspace)
ROS_DISTRO=jazzy uv run --directory python/perceptshift_api --extra dev \
  pytest tests/test_ros_bridge_graph.py -v
```

## Console E2E gates

| Suite | Gate | Meaning |
|-------|------|---------|
| `web/tests/e2e/real-api.spec.ts` | always (Playwright webServer) | Artifact-store smoke; **no** API route mocks |
| `web/tests/e2e/real-stack.spec.ts` | `PERCEPTSHIFT_REAL_STACK_E2E=1` | **Canonical** ROS+runtime console acceptance |

```bash
# Baseline (artifact-store, no ROS)
pnpm --dir web test:e2e -- tests/e2e/real-api.spec.ts

# Canonical real-stack (Colab / Jazzy with runtime up)
./scripts/run-real-stack-e2e.sh
```
