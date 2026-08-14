#!/usr/bin/env bash
# Browser real-stack E2E: ROS+API in arm64 Docker, Playwright on host against published API/console.
# Proves a real sensor_msgs/Image → RuntimeEngine → ORT inference transaction.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLATFORM="${DOCKER_PLATFORM:-linux/arm64}"
API_PORT="${PERCEPTSHIFT_API_PORT:-8741}"
CONSOLE_PORT="${PERCEPTSHIFT_CONSOLE_PORT:-5173}"
MUTATION_TOKEN="${PERCEPTSHIFT_API_MUTATION_TOKEN:-real-stack-e2e-token}"
CONTAINER_NAME="ps-real-stack-$$"
API_BASE="http://127.0.0.1:${API_PORT}"
CONSOLE_URL="http://127.0.0.1:${CONSOLE_PORT}"
SKIP_PUBLISH="${PERCEPTSHIFT_SKIP_FRAME_PUBLISH:-0}"

cleanup() {
  docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
  if [[ -n "${CONSOLE_PID:-}" ]]; then
    kill "$CONSOLE_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

docker ps -aq --filter 'name=ps-real-stack-' | xargs -r docker rm -f >/dev/null 2>&1 || true

arch=""
for _ in 1 2 3 4 5; do
  if arch="$(docker run --rm --platform "$PLATFORM" ubuntu:24.04 uname -m 2>/dev/null)"; then
    break
  fi
  sleep 2
done
[[ "$arch" == "aarch64" ]] || { echo "expected aarch64 (docker networking/runtime unavailable)" >&2; exit 1; }

docker_run_ok=0
for _ in 1 2 3 4 5; do
  if docker run -d --name "$CONTAINER_NAME" --platform "$PLATFORM" \
    -p "${API_PORT}:8741" \
    -v "$ROOT:/src" \
    -v "$ROOT/.cache:/cache" \
    ros:jazzy-ros-base sleep infinity >/dev/null; then
    docker_run_ok=1
    break
  fi
  docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
  sleep 3
done
[[ "$docker_run_ok" -eq 1 ]] || { echo "failed to start real-stack container" >&2; exit 125; }
docker exec "$CONTAINER_NAME" bash -lc '
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
set +u; source /opt/ros/jazzy/setup.bash; set -u
apt-get update -qq
apt-get install -y -qq build-essential cmake ninja-build git python3-pip python3-venv \
  python3-colcon-common-extensions ros-jazzy-rclcpp-lifecycle \
  ros-jazzy-rclcpp-components ros-jazzy-sensor-msgs ros-jazzy-diagnostic-updater \
  ros-jazzy-launch-ros ros-jazzy-lifecycle-msgs ros-jazzy-rclpy \
  ros-jazzy-image-transport ros-jazzy-cv-bridge \
  python3-numpy python3-pil libssl-dev zlib1g-dev curl >/dev/null
python3 -m venv --system-site-packages /tmp/ps-e2e-venv
/tmp/ps-e2e-venv/bin/pip install -q --upgrade pip
# Retry pip installs under flaky Colima DNS.
for _ in 1 2 3 4 5; do
  if /tmp/ps-e2e-venv/bin/pip install -q "pytest>=8" onnx protobuf httpx fastapi uvicorn \
    numpy pillow pyyaml \
    -e /src/python/perceptshift_common -e /src/python/perceptshift_api; then
    break
  fi
  sleep 5
done
/tmp/ps-e2e-venv/bin/python -c "import fastapi, perceptshift_api" 
cd /src
cmake -S . -B build/ros-core \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX=/opt/perceptshift \
  -DPERCEPTSHIFT_ORT_ROOT=/cache/onnxruntime-linux-aarch64-1.28.0 \
  -DPERCEPTSHIFT_BUILD_TESTS=OFF
cmake --build build/ros-core -j2
cmake --install build/ros-core
export CMAKE_PREFIX_PATH=/opt/perceptshift:${CMAKE_PREFIX_PATH:-}
export LD_LIBRARY_PATH=/cache/onnxruntime-linux-aarch64-1.28.0/lib:/opt/perceptshift/lib/perceptshift:/opt/perceptshift/lib:${LD_LIBRARY_PATH:-}
cd /src/ros2_ws
colcon build --symlink-install --cmake-args -DCMAKE_BUILD_TYPE=Release
'

docker exec -d "$CONTAINER_NAME" bash -lc '
set -euo pipefail
set +u; source /opt/ros/jazzy/setup.bash; source /src/ros2_ws/install/setup.bash; set -u
export LD_LIBRARY_PATH=/cache/onnxruntime-linux-aarch64-1.28.0/lib:/opt/perceptshift/lib/perceptshift:/opt/perceptshift/lib:${LD_LIBRARY_PATH:-}
export CMAKE_PREFIX_PATH=/opt/perceptshift:${CMAKE_PREFIX_PATH:-}
export PATH=/tmp/ps-e2e-venv/bin:$PATH
/tmp/ps-e2e-venv/bin/python - <<PY
from pathlib import Path
import sys
sys.path.insert(0, "/src/tests/e2e")
from bundle_fixture import write_classification_bundle
write_classification_bundle(Path("/tmp/ps-browser-bundle"))
print("bundle_ok")
PY
ros2 run perceptshift_ros perceptshift_runtime_node --ros-args \
  -p bundle_path:=/tmp/ps-browser-bundle \
  -p image_topic:=/camera/image_raw \
  -p task:=image_classification \
  -p deadline_ms:=500.0 \
  -p require_signature:=false \
  -p enable_mutation_services:=true \
  -p maximum_source_age_ms:=5000.0 \
  -p telemetry_period_ms:=200 \
  >/tmp/ps-runtime.log 2>&1 &
sleep 3
ros2 lifecycle set /perceptshift_runtime configure
ros2 lifecycle set /perceptshift_runtime activate
PERCEPTSHIFT_API_ENABLE_ROS=true \
PERCEPTSHIFT_API_MUTATION_TOKEN='"$MUTATION_TOKEN"' \
/tmp/ps-e2e-venv/bin/python -m perceptshift_api --host 0.0.0.0 --port 8741 >/tmp/ps-api.log 2>&1 &
'

for _ in $(seq 1 120); do
  if curl -fsS "${API_BASE}/api/v1/runtime/status" 2>/dev/null | grep -q '"connected":true'; then
    break
  fi
  sleep 1
done
curl -fsS "${API_BASE}/api/v1/runtime/status" | grep -q '"connected":true' \
  || {
    echo "API not connected; dumping container logs" >&2
    docker exec "$CONTAINER_NAME" bash -lc 'tail -100 /tmp/ps-api.log /tmp/ps-runtime.log 2>/dev/null || true' >&2 || true
    exit 1
  }

count_traces() {
  local json="$1"
  CUR="$json" python3 - <<'PY'
import json, os
events = json.loads(os.environ["CUR"]).get("events") or []
traces = [e for e in events if e.get("event_type") == "inference_trace_summary"]
seqs = [int((e.get("payload") or {}).get("sequence_id") or 0) for e in traces]
print(f"{len(traces)} {max(seqs) if seqs else 0}")
PY
}

has_post_baseline() {
  local json="$1" base_count="$2" base_seq="$3"
  CUR="$json" BASE_COUNT="$base_count" BASE_SEQ="$base_seq" python3 - <<'PY'
import json, os, sys
events = json.loads(os.environ["CUR"]).get("events") or []
traces = [e for e in events if e.get("event_type") == "inference_trace_summary"]
base_seq = int(os.environ["BASE_SEQ"])
base_count = int(os.environ["BASE_COUNT"])
ok = any(int((e.get("payload") or {}).get("sequence_id") or 0) > base_seq for e in traces)
ok = ok or (len(traces) > base_count)
sys.exit(0 if ok else 1)
PY
}

BASELINE_JSON="$(curl -fsS "${API_BASE}/api/v1/telemetry/recent?limit=200")"
read -r BASELINE_TRACE_COUNT BASELINE_SEQ <<<"$(count_traces "$BASELINE_JSON")"
echo "baseline_inference_seq=$BASELINE_SEQ baseline_trace_count=$BASELINE_TRACE_COUNT"

# Negative regression: without a published frame, inference evidence must NOT appear.
# Health/profile heartbeats alone must not satisfy the inference gate.
echo "Negative check: confirming no inference without frame publish"
sleep 3
NEG_JSON="$(curl -fsS "${API_BASE}/api/v1/telemetry/recent?limit=200")"
if has_post_baseline "$NEG_JSON" "$BASELINE_TRACE_COUNT" "$BASELINE_SEQ"; then
  echo "NEGATIVE CHECK FAILED: inference_trace_summary appeared without frame publish" >&2
  echo "$NEG_JSON" | head -c 2000 >&2
  exit 1
fi
echo "negative_no_publish_ok"

if [[ "$SKIP_PUBLISH" == "1" ]]; then
  echo "SKIP_PUBLISH=1 — stopping after negative proof (inference assert would fail)"
  echo "STATUS=PASS gate=browser_real_stack_negative_no_publish"
  exit 0
fi

echo "Publishing sensor_msgs/Image onto /camera/image_raw"
docker exec "$CONTAINER_NAME" bash -lc '
set -euo pipefail
set +u; source /opt/ros/jazzy/setup.bash; source /src/ros2_ws/install/setup.bash; set -u
python3 - <<PY
import time
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image

rclpy.init()
node = Node("ps_browser_frame_pub")
pub = node.create_publisher(Image, "/camera/image_raw", 10)
time.sleep(0.5)
w = h = 8
img = Image()
img.height = h
img.width = w
img.encoding = "rgb8"
img.is_bigendian = 0
img.step = w * 3
img.data = bytes([40, 80, 120] * (w * h))
img.header.frame_id = "camera"
for _ in range(20):
    img.header.stamp = node.get_clock().now().to_msg()
    pub.publish(img)
    rclpy.spin_once(node, timeout_sec=0.05)
    time.sleep(0.05)
node.destroy_node()
rclpy.shutdown()
print("frame_published")
PY
'

saw=0
for _ in $(seq 1 90); do
  cur="$(curl -fsS "${API_BASE}/api/v1/telemetry/recent?limit=200")"
  if has_post_baseline "$cur" "$BASELINE_TRACE_COUNT" "$BASELINE_SEQ"; then
    saw=1
    break
  fi
  sleep 0.5
done
[[ "$saw" == "1" ]] || {
  echo "no post-frame inference_trace_summary observed via API" >&2
  curl -fsS "${API_BASE}/api/v1/telemetry/recent?limit=50" >&2 || true
  docker exec "$CONTAINER_NAME" bash -lc 'tail -80 /tmp/ps-runtime.log' >&2 || true
  exit 1
}
echo "post_frame_inference_ok"

(
  cd "$ROOT/web"
  pnpm install
  pnpm exec playwright install chromium
)

if ! curl -fsS "${CONSOLE_URL}" >/dev/null 2>&1; then
  echo "Starting web console on ${CONSOLE_URL}"
  (cd "$ROOT/web" && pnpm exec vite --host 127.0.0.1 --port "${CONSOLE_PORT}") >/tmp/ps-console.log 2>&1 &
  CONSOLE_PID=$!
  for _ in $(seq 1 90); do
    if curl -fsS "${CONSOLE_URL}" >/dev/null 2>&1; then
      break
    fi
    sleep 0.5
  done
fi
if ! curl -fsS "${CONSOLE_URL}" >/dev/null 2>&1; then
  echo "console failed to start" >&2
  tail -80 /tmp/ps-console.log >&2 || true
  exit 1
fi

export PERCEPTSHIFT_REAL_STACK_E2E=1
export PERCEPTSHIFT_API_BASE="${API_BASE}"
export PERCEPTSHIFT_API_MUTATION_TOKEN="${MUTATION_TOKEN}"
export PERCEPTSHIFT_BASELINE_INFERENCE_SEQ="${BASELINE_SEQ}"
export PERCEPTSHIFT_BASELINE_TRACE_COUNT="${BASELINE_TRACE_COUNT}"
export PERCEPTSHIFT_REQUIRE_INFERENCE=1
(
  cd "$ROOT/web"
  pnpm exec playwright test tests/e2e/real-stack.spec.ts --project=chromium
)
echo "STATUS=PASS gate=browser_real_stack_e2e"
