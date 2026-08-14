#!/usr/bin/env bash
# Canonical real-stack browser E2E harness (API + ROS runtime + console).
#
# This is the CANONICAL gate for Workstream D console acceptance against a live
# ROS graph. The artifact-store Playwright smoke (web/tests/e2e/real-api.spec.ts)
# is a continuous baseline only and does not satisfy ROS connectivity.
#
# Usage (Colab / Jazzy host after Workstream C brings up the runtime):
#   ./scripts/run-real-stack-e2e.sh
#
# Environment:
#   PERCEPTSHIFT_REAL_STACK_E2E=1   set automatically by this script
#   PERCEPTSHIFT_API_MUTATION_TOKEN mutation token for policy/pin steps
#   PERCEPTSHIFT_BUNDLE_PATH        optional; if set, attempts to launch runtime
#   PERCEPTSHIFT_API_BASE           default http://127.0.0.1:8741
#   PERCEPTSHIFT_CONSOLE_URL        default http://127.0.0.1:5173
#
# Exit behaviour:
#   --probe (default): STATUS=UNAVAILABLE ... exit 0 when prerequisites missing
#   --required:        unavailable prerequisites => nonzero failure (release gate)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MODE="probe"
for arg in "$@"; do
  case "$arg" in
    --required) MODE="required" ;;
    --probe) MODE="probe" ;;
  esac
done

API_BASE="${PERCEPTSHIFT_API_BASE:-http://127.0.0.1:8741}"
CONSOLE_URL="${PERCEPTSHIFT_CONSOLE_URL:-http://127.0.0.1:5173}"
API_HOST="127.0.0.1"
API_PORT="8741"
MUTATION_TOKEN="${PERCEPTSHIFT_API_MUTATION_TOKEN:-real-stack-e2e-token}"
STARTED_API=0
STARTED_CONSOLE=0
API_PID=""
CONSOLE_PID=""

cleanup() {
  if [[ "$STARTED_CONSOLE" -eq 1 && -n "$CONSOLE_PID" ]]; then
    kill "$CONSOLE_PID" 2>/dev/null || true
  fi
  if [[ "$STARTED_API" -eq 1 && -n "$API_PID" ]]; then
    kill "$API_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

unavailable() {
  echo "STATUS=UNAVAILABLE reason=$1 mode=$MODE"
  if [[ "$MODE" == "required" ]]; then
    exit 1
  fi
  exit 0
}

fail() {
  echo "STATUS=FAIL reason=$1"
  exit 1
}

if [[ "${ROS_DISTRO:-}" != "jazzy" ]]; then
  unavailable "ROS_DISTRO_NOT_JAZZY"
fi

if ! python3 -c 'import rclpy' 2>/dev/null; then
  unavailable "RCLPY_MISSING"
fi

if ! python3 -c 'from perceptshift_msgs.msg import RuntimeHealth' 2>/dev/null; then
  unavailable "PERCEPTSHIFT_MSGS_MISSING"
fi

# Require a discoverable runtime status service (Workstream C ownership).
if ! timeout 5 ros2 service list 2>/dev/null | grep -q 'get_runtime_status'; then
  if [[ -n "${PERCEPTSHIFT_BUNDLE_PATH:-}" ]]; then
    echo "Runtime status service absent; attempting launch with bundle ${PERCEPTSHIFT_BUNDLE_PATH}"
    if command -v ros2 >/dev/null 2>&1; then
      ros2 launch perceptshift_bringup runtime.launch.py \
        "bundle_path:=${PERCEPTSHIFT_BUNDLE_PATH}" \
        enable_mutation_services:=true \
        >/tmp/perceptshift-real-stack-runtime.log 2>&1 &
      # Give DDS + lifecycle a moment; connection is still verified below.
      sleep 5
    fi
  fi
fi

if ! timeout 5 ros2 service list 2>/dev/null | grep -q 'get_runtime_status'; then
  unavailable "RUNTIME_STATUS_SERVICE_ABSENT"
fi

# Start API in ROS mode if healthz is not already up.
if ! curl -fsS "${API_BASE}/api/v1/healthz" >/dev/null 2>&1; then
  echo "Starting FastAPI in ROS bridge mode on ${API_HOST}:${API_PORT}"
  PERCEPTSHIFT_API_ENABLE_ROS=true \
  PERCEPTSHIFT_API_HOST="${API_HOST}" \
  PERCEPTSHIFT_API_PORT="${API_PORT}" \
  PERCEPTSHIFT_API_MUTATION_TOKEN="${MUTATION_TOKEN}" \
  uv run --directory python/perceptshift_api python -m perceptshift_api \
    --host "${API_HOST}" --port "${API_PORT}" \
    >/tmp/perceptshift-real-stack-api.log 2>&1 &
  API_PID=$!
  STARTED_API=1
  for _ in $(seq 1 60); do
    if curl -fsS "${API_BASE}/api/v1/healthz" >/dev/null 2>&1; then
      break
    fi
    sleep 0.5
  done
  curl -fsS "${API_BASE}/api/v1/healthz" >/dev/null || fail "API_START_FAILED"
fi

# Wait until bridge reports connected (or time out as UNAVAILABLE).
CONNECTED=0
for _ in $(seq 1 60); do
  BODY="$(curl -fsS "${API_BASE}/api/v1/runtime/status" || true)"
  if echo "$BODY" | grep -q '"connected":true'; then
    CONNECTED=1
    break
  fi
  sleep 0.5
done
if [[ "$CONNECTED" -ne 1 ]]; then
  unavailable "API_ROS_BRIDGE_NOT_CONNECTED"
fi

# Start console if needed.
if ! curl -fsS "${CONSOLE_URL}" >/dev/null 2>&1; then
  echo "Starting web console on ${CONSOLE_URL}"
  (cd web && pnpm vite --host 127.0.0.1 --port 5173) >/tmp/perceptshift-real-stack-console.log 2>&1 &
  CONSOLE_PID=$!
  STARTED_CONSOLE=1
  for _ in $(seq 1 60); do
    if curl -fsS "${CONSOLE_URL}" >/dev/null 2>&1; then
      break
    fi
    sleep 0.5
  done
  curl -fsS "${CONSOLE_URL}" >/dev/null || fail "CONSOLE_START_FAILED"
fi

export PERCEPTSHIFT_REAL_STACK_E2E=1
export PERCEPTSHIFT_API_BASE="${API_BASE}"
export PERCEPTSHIFT_API_MUTATION_TOKEN="${MUTATION_TOKEN}"

echo "Running canonical Playwright real-stack suite (no API mocks)"
(
  cd web
  pnpm exec playwright test tests/e2e/real-stack.spec.ts --project=chromium
) || fail "PLAYWRIGHT_REAL_STACK_FAILED"

echo "STATUS=PASS gate=canonical_real_stack_e2e"
exit 0
