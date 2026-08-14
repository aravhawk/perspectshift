#!/usr/bin/env bash
# Ubuntu 24.04 arm64 clean-room: source-only export → build → test → package → install → purge.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLATFORM="${DOCKER_PLATFORM:-linux/arm64}"
MODE="${1:-full}" # full | final
OUT_DIR="${DIST_DIR:-$ROOT/dist}"
EVIDENCE_DIR="${PERCEPTSHIFT_CLEANROOM_EVIDENCE:-$ROOT/build/verification/artifacts/clean-room}"
mkdir -p "$OUT_DIR" "$EVIDENCE_DIR"

arch="$(docker run --rm --platform "$PLATFORM" ubuntu:24.04 uname -m)"
[[ "$arch" == "aarch64" ]] || { echo "expected aarch64" >&2; exit 1; }

EXPORT_DIR="$OUT_DIR/clean-room-export"
rm -rf "$EXPORT_DIR"
mkdir -p "$EXPORT_DIR"
SOURCE_EXPORT_DIR="$EXPORT_DIR" bash "$ROOT/scripts/export-source.sh"
ARCHIVE="$(ls -1t "$EXPORT_DIR"/perceptshift-source-*.tar.gz | head -1)"
[[ -s "$ARCHIVE" ]] || { echo "export archive missing" >&2; exit 1; }
cp -v "$ARCHIVE" "$EVIDENCE_DIR/"
cp -v "${ARCHIVE}.json" "$EVIDENCE_DIR/" 2>/dev/null || true

BUILDER="ps-cleanroom-build-$$"
INSTALLER="ps-cleanroom-install-$$"
cleanup() {
  docker rm -f "$BUILDER" "$INSTALLER" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "==> Clean-room build + package from source-only archive"
docker run -d --name "$BUILDER" --platform "$PLATFORM" \
  -v "$ARCHIVE:/export/source.tar.gz:ro" \
  -v "$ROOT/.cache:/cache:ro" \
  -v "$OUT_DIR:/dist" \
  -v "$EVIDENCE_DIR:/evidence" \
  ros:jazzy-ros-base sleep infinity >/dev/null

docker exec "$BUILDER" bash -lc '
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
set +u; source /opt/ros/jazzy/setup.bash; set -u
# Retry apt under flaky Colima DNS.
ok=0
for _ in 1 2 3 4 5 6 7 8; do
  if apt-get update -qq && apt-get install -y -qq rsync cmake ninja-build g++ git curl ca-certificates pkg-config \
    python3 python3-venv python3-pip python3-setuptools python3-colcon-common-extensions \
    dpkg-dev file binutils nlohmann-json3-dev \
    ros-jazzy-rclcpp-lifecycle ros-jazzy-rclcpp-components ros-jazzy-sensor-msgs \
    ros-jazzy-diagnostic-updater ros-jazzy-launch-ros ros-jazzy-lifecycle-msgs \
    ros-jazzy-rclpy ros-jazzy-image-transport ros-jazzy-cv-bridge \
    ros-jazzy-ament-cmake-gtest >/dev/null; then
    ok=1
    break
  fi
  sleep 8
done
[[ "$ok" == "1" ]] || { echo "apt install failed after retries" >&2; exit 100; }
rm -rf /tmp/ps
mkdir -p /tmp/ps
tar -xzf /export/source.tar.gz -C /tmp/ps
cd /tmp/ps
# Hygiene
./scripts/verify-repository.sh
# Native build + tests
mkdir -p /tmp/ort
cp -a /cache/onnxruntime-linux-aarch64-1.28.0 /tmp/ort/
export PERCEPTSHIFT_ORT_ROOT=/tmp/ort/onnxruntime-linux-aarch64-1.28.0
cmake -S . -B build/clean \
  -DCMAKE_BUILD_TYPE=Release \
  -DPERCEPTSHIFT_ORT_ROOT="$PERCEPTSHIFT_ORT_ROOT" \
  -DPERCEPTSHIFT_BUILD_TESTS=ON
cmake --build build/clean -j2
ctest --test-dir build/clean --output-on-failure
# Python/contract suites (ephemeral venv for tests only — not used after package install)
python3 -m venv /tmp/ps-venv
/tmp/ps-venv/bin/pip install -q --upgrade pip setuptools wheel
/tmp/ps-venv/bin/pip install -q -e python/perceptshift_common -e python/perceptshift_cli \
  -e python/perceptshift_forge -e python/perceptshift_api "pytest>=8" pytest-asyncio ruff \
  jsonschema referencing pydantic pyyaml numpy pillow onnx onnxruntime==1.28.0 cryptography
/tmp/ps-venv/bin/ruff check python
# ROS setup.bash puts launch_testing on sys.path; disable plugin autoload for product tests.
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
/tmp/ps-venv/bin/python -m pytest -c /dev/null python/perceptshift_common python/perceptshift_cli tests/contract -q --tb=line
# ROS build + fixture inference
export CMAKE_PREFIX_PATH=/tmp/ps/build/clean/install:${CMAKE_PREFIX_PATH:-}
cmake --install build/clean --prefix /opt/perceptshift
export CMAKE_PREFIX_PATH=/opt/perceptshift:${CMAKE_PREFIX_PATH:-}
export LD_LIBRARY_PATH=$PERCEPTSHIFT_ORT_ROOT/lib:/opt/perceptshift/lib/perceptshift:/opt/perceptshift/lib:${LD_LIBRARY_PATH:-}
cd /tmp/ps/ros2_ws
colcon build --symlink-install --cmake-args -DCMAKE_BUILD_TYPE=Release
set +u; source /opt/ros/jazzy/setup.bash; source install/setup.bash; set -u
export PERCEPTSHIFT_ROS_E2E_REQUIRED=1
/tmp/ps-venv/bin/pip install -q pytest onnx protobuf
/tmp/ps-venv/bin/python -m pytest -c /dev/null /tmp/ps/tests/e2e/test_ros_native_inference.py -rs -q --tb=line
# Build functional Debian artifact from THIS clean-room tree (not outer /src/build)
cd /tmp/ps
# Do not leak the clean-room ROS workspace overlay into the package prefix chain.
set +u
unset AMENT_PREFIX_PATH COLCON_PREFIX_PATH CMAKE_PREFIX_PATH || true
source /opt/ros/jazzy/setup.bash
set -u
export PERCEPTSHIFT_ORT_ROOT=/tmp/ort/onnxruntime-linux-aarch64-1.28.0
export DIST_DIR=/dist/clean-room
export PERCEPTSHIFT_DEB_BUILD=/tmp/ps/build/deb-release
mkdir -p "$DIST_DIR"
chmod +x scripts/build-release-deb.sh scripts/package-deb.sh
./scripts/package-deb.sh
DEB="$(ls -1t /dist/clean-room/perceptshift_*.deb | head -1)"
cp -v "$DEB" /evidence/
dpkg-deb -I "$DEB" | tee /evidence/cleanroom-dpkg-I.txt
sha256sum "$DEB" | tee /evidence/cleanroom-deb.sha256
echo "CLEANROOM_DEB=$(basename "$DEB")"
'

DEB="$(ls -1t "$OUT_DIR"/clean-room/perceptshift_*.deb 2>/dev/null | head -1 || true)"
[[ -n "$DEB" && -s "$DEB" ]] || { echo "clean-room deb missing" >&2; exit 1; }
DEB_BASE="$(basename "$DEB")"
DEB_SHA="$(sha256sum "$DEB" | awk '{print $1}')"

echo "==> Fresh install stage using clean-room-produced artifact only"
docker run -d --name "$INSTALLER" --platform "$PLATFORM" \
  -v "$OUT_DIR/clean-room:/dist:ro" \
  -v "$ROOT/tests:/tests:ro" \
  -v "$EVIDENCE_DIR:/evidence" \
  ros:jazzy-ros-base sleep infinity >/dev/null

docker exec -e DEB_BASE="$DEB_BASE" -e DEB_SHA="$DEB_SHA" "$INSTALLER" bash -lc '
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
set +u; source /opt/ros/jazzy/setup.bash; set -u
apt-get update -qq
apt-get install -y -qq dpkg curl ca-certificates python3 adduser passwd \
  ros-jazzy-rclcpp-lifecycle ros-jazzy-sensor-msgs ros-jazzy-launch-ros \
  ros-jazzy-lifecycle-msgs ros-jazzy-rclpy ros-jazzy-diagnostic-updater >/dev/null
# Must NOT use outer build tree or .venv
test ! -e /src/build
test ! -e /src/.venv
DEB="/dist/${DEB_BASE}"
test -s "$DEB"
[[ "$(sha256sum "$DEB" | awk "{print \$1}")" == "$DEB_SHA" ]]
dpkg -i "$DEB" || apt-get install -y -f -qq
dpkg -i "$DEB"
perceptshift --help >/dev/null
perceptshift --json version | python3 -c "import sys,json; json.load(sys.stdin)"
perceptshift-api --help >/dev/null
API_PORT=18755
perceptshift-api --host 127.0.0.1 --port "$API_PORT" >/tmp/api.log 2>&1 &
API_PID=$!
ok=0
for _ in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:${API_PORT}/api/v1/healthz" >/dev/null; then ok=1; break; fi
  kill -0 "$API_PID" 2>/dev/null || { tail -50 /tmp/api.log; exit 1; }
  sleep 0.5
done
[[ "$ok" == 1 ]]
kill "$API_PID" 2>/dev/null || true
set +u; source /usr/share/perceptshift/ros/setup.bash; set -u
ros2 pkg prefix perceptshift_bringup
test -f /usr/lib/systemd/system/perceptshift-runtime.service
getent passwd perceptshift >/dev/null
getent passwd perceptshift-api >/dev/null
getent group perceptshift >/dev/null
test -d /var/lib/perceptshift
test -d /var/log/perceptshift
if ! compgen -G '/usr/lib/perceptshift/libonnxruntime.so*' >/dev/null; then
  echo "packaged libonnxruntime missing" >&2
  exit 1
fi
# Fixture inference via installed artifacts only (no outer build/.cache/.venv)
python3 - <<PY
from pathlib import Path
import sys
sys.path.insert(0, "/tests/e2e")
from bundle_fixture import write_classification_bundle
write_classification_bundle(Path("/tmp/ps-cr-bundle"))
PY
export LD_LIBRARY_PATH=/usr/lib/perceptshift:${LD_LIBRARY_PATH:-}
/usr/lib/perceptshift/bin/perceptshift-ros-runtime --bundle /tmp/ps-cr-bundle \
  --task image_classification \
  deadline_ms:=500.0 maximum_source_age_ms:=5000.0 telemetry_period_ms:=200 \
  >/tmp/ros.log 2>&1 &
RPID=$!
# Wait until lifecycle get_state is advertised (avoid fixed sleep races).
python3 - <<PY
import time, subprocess, sys
deadline = time.time() + 60
while time.time() < deadline:
    if subprocess.run(
        ["bash", "-lc", "ros2 service list 2>/dev/null | grep -q /perceptshift_runtime/get_state"],
        check=False,
    ).returncode == 0:
        print("runtime_services_ready")
        sys.exit(0)
    if subprocess.run(["kill", "-0", str($RPID)], check=False).returncode != 0:
        print("ros runtime exited early", file=sys.stderr)
        subprocess.run(["bash", "-lc", "tail -200 /tmp/ros.log"], check=False)
        sys.exit(1)
    time.sleep(1)
print("timeout waiting for get_state", file=sys.stderr)
subprocess.run(["bash", "-lc", "tail -200 /tmp/ros.log; ros2 node list; ros2 service list | head -40"], check=False)
sys.exit(1)
PY
python3 - <<PY
import time
import rclpy
from rclpy.node import Node
from lifecycle_msgs.srv import ChangeState, GetState
from lifecycle_msgs.msg import Transition
from sensor_msgs.msg import Image
from perceptshift_msgs.msg import ClassificationArray

rclpy.init()
node = Node("ps_cr_infer")
try:
    state_cli = node.create_client(GetState, "/perceptshift_runtime/get_state")
    change_cli = node.create_client(ChangeState, "/perceptshift_runtime/change_state")
    assert state_cli.wait_for_service(timeout_sec=45.0), "get_state unavailable"
    def label():
        fut = state_cli.call_async(GetState.Request())
        rclpy.spin_until_future_complete(node, fut, timeout_sec=5.0)
        return fut.result().current_state.label if fut.result() else ""
    lab = label()
    if lab in ("unconfigured", "unknown", ""):
        change_cli.wait_for_service(timeout_sec=10)
        req = ChangeState.Request(); req.transition.id = Transition.TRANSITION_CONFIGURE; req.transition.label = "configure"
        fut = change_cli.call_async(req); rclpy.spin_until_future_complete(node, fut, timeout_sec=60)
        assert fut.result() and fut.result().success, f"configure failed: {fut.result()}"
    if label() == "inactive":
        req = ChangeState.Request(); req.transition.id = Transition.TRANSITION_ACTIVATE; req.transition.label = "activate"
        fut = change_cli.call_async(req); rclpy.spin_until_future_complete(node, fut, timeout_sec=60)
        assert fut.result() and fut.result().success, f"activate failed: {fut.result()}"
    for _ in range(60):
        if label() == "active":
            break
        time.sleep(0.5)
    assert label() == "active", f"expected active, got {label()}"
    classes = []
    node.create_subscription(ClassificationArray, "/perceptshift_runtime/classifications", lambda m: classes.append(m), 10)
    pub = node.create_publisher(Image, "/camera/image_raw", 10)
    time.sleep(0.5)
    w = h = 8
    img = Image(); img.height=h; img.width=w; img.encoding="rgb8"; img.is_bigendian=0; img.step=w*3
    img.data = bytes([7,8,9]*(w*h)); img.header.frame_id="camera"
    end = time.time()+45
    while time.time() < end and not classes:
        img.header.stamp = node.get_clock().now().to_msg()
        pub.publish(img)
        rclpy.spin_once(node, timeout_sec=0.2)
    assert classes and classes[0].predictions, "no ClassificationArray from installed runtime"
    print("cleanroom_installed_inference_ok")
finally:
    node.destroy_node(); rclpy.shutdown()
PY
kill "$RPID" 2>/dev/null || true
dpkg --purge perceptshift
if [[ -e /usr/bin/perceptshift ]] || [[ -e /usr/bin/perceptshift-api ]]; then
  echo "executables remain after purge" >&2
  exit 1
fi
cat > /evidence/cleanroom-acceptance.json <<JSON
{"status":"PASS","deb":"$DEB_BASE","sha256":"$DEB_SHA","mode":"installed-from-cleanroom-artifact"}
JSON
'

echo "STATUS=PASS gate=ubuntu_noble_clean_room mode=$MODE deb=$DEB_BASE sha256=$DEB_SHA"
