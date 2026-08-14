#!/usr/bin/env bash
# ROS 2 Jazzy build/test/integration acceptance via Docker arm64.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLATFORM="${DOCKER_PLATFORM:-linux/arm64}"
MODE="all"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --build-test-only) MODE=build_test; shift ;;
    --integration) MODE=integration; shift ;;
    --api) MODE=api; shift ;;
    *) echo "unknown: $1" >&2; exit 2 ;;
  esac
done

arch="$(docker run --rm --platform "$PLATFORM" ubuntu:24.04 uname -m)"
[[ "$arch" == "aarch64" ]] || { echo "expected aarch64" >&2; exit 1; }

ORT_LINUX="$ROOT/.cache/onnxruntime-linux-aarch64-1.28.0"
IMAGE="ros:jazzy-ros-base"

docker run --rm --platform "$PLATFORM" \
  -v "$ROOT:/src" \
  -v "$ROOT/.cache:/cache" \
  "$IMAGE" bash -lc "
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
# ROS setup.bash references optional unset vars under set -u.
set +u
source /opt/ros/jazzy/setup.bash
set -u
apt-get update -qq
apt-get install -y -qq build-essential cmake ninja-build git python3-pip python3-venv \
  python3-colcon-common-extensions ros-jazzy-rclcpp-lifecycle \
  ros-jazzy-rclcpp-components ros-jazzy-sensor-msgs ros-jazzy-diagnostic-updater \
  ros-jazzy-launch-ros ros-jazzy-image-transport ros-jazzy-cv-bridge \
  ros-jazzy-ament-cmake-gtest ros-jazzy-ament-cmake-pytest \
  ros-jazzy-lifecycle-msgs ros-jazzy-rclpy \
  python3-pytest python3-numpy python3-pil \
  libssl-dev zlib1g-dev >/dev/null
python3 -m venv --system-site-packages /tmp/ps-e2e-venv
/tmp/ps-e2e-venv/bin/pip install -q --upgrade pip
/tmp/ps-e2e-venv/bin/pip install -q 'pytest>=8' onnx protobuf httpx fastapi uvicorn \
  numpy pillow pyyaml
# Prefer venv for E2E later. Colcon ament pytest must not load ROS launch_testing
# (incompatible with pytest 8) and must not inherit repo-root asyncio_* options.
export PATH=/tmp/ps-e2e-venv/bin:\$PATH
/tmp/ps-e2e-venv/bin/python -c 'import onnx, pytest, rclpy; print(pytest.__version__, onnx.__version__)'
cd /src
# Build native core with ORT
cmake -S . -B build/ros-core \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX=/opt/perceptshift \
  -DPERCEPTSHIFT_ORT_ROOT=/cache/onnxruntime-linux-aarch64-1.28.0 \
  -DPERCEPTSHIFT_BUILD_TESTS=ON
cmake --build build/ros-core -j2
cmake --install build/ros-core
export CMAKE_PREFIX_PATH=/opt/perceptshift:\${CMAKE_PREFIX_PATH:-}
export LD_LIBRARY_PATH=/cache/onnxruntime-linux-aarch64-1.28.0/lib:/opt/perceptshift/lib/perceptshift:/opt/perceptshift/lib:\${LD_LIBRARY_PATH:-}
cd /src/ros2_ws
colcon build --symlink-install --cmake-args -DCMAKE_BUILD_TYPE=Release
if [[ \"$MODE\" == \"build_test\" || \"$MODE\" == \"all\" ]]; then
  export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
  export PYTEST_ADDOPTS='-c /dev/null'
  colcon test --event-handlers console_direct+
  colcon test-result --verbose
  unset PYTEST_ADDOPTS
  python3 - <<'PY'
import pathlib, sys, xml.etree.ElementTree as ET
roots = list(pathlib.Path('build').rglob('*.xml')) + list(pathlib.Path('log').rglob('*.xml'))
usable = []
failures = 0
tests = 0
for path in roots:
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        continue
    tag = root.tag.lower()
    if 'testsuite' not in tag and 'testsuites' not in tag:
        continue
    usable.append(path)
    if tag.endswith('testsuites'):
        suites = list(root)
    else:
        suites = [root]
    for suite in suites:
        tests += int(suite.attrib.get('tests', 0) or 0)
        failures += int(suite.attrib.get('failures', 0) or 0) + int(suite.attrib.get('errors', 0) or 0)
print(f'result files {len(usable)} tests {tests} failures {failures}')
sys.exit(0 if usable and tests > 0 and failures == 0 else 1)
PY
fi
if [[ \"$MODE\" == \"integration\" || \"$MODE\" == \"all\" ]]; then
  set +u
  source install/setup.bash
  set -u
  pkgs=\"\$(ros2 pkg list || true)\"
  echo \"\$pkgs\" | grep -q perceptshift_ros
  echo \"\$pkgs\" | grep -q perceptshift_msgs
  if [[ ! -f /src/tests/e2e/test_ros_native_inference.py ]]; then
    echo 'missing /src/tests/e2e/test_ros_native_inference.py' >&2
    exit 1
  fi
  export PERCEPTSHIFT_ROS_E2E_REQUIRED=1
  export PATH=/tmp/ps-e2e-venv/bin:\$PATH
  export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
  /tmp/ps-e2e-venv/bin/python -m pytest -c /dev/null /src/tests/e2e/test_ros_native_inference.py -rs -vv --tb=short
fi
if [[ \"$MODE\" == \"api\" || \"$MODE\" == \"all\" ]]; then
  set +u
  source install/setup.bash
  set -u
  if [[ ! -f /src/tests/e2e/test_api_ros_integration.py ]]; then
    echo 'API ROS integration test module missing' >&2
    exit 1
  fi
  export PATH=/tmp/ps-e2e-venv/bin:\$PATH
  /tmp/ps-e2e-venv/bin/pip install -q -e /src/python/perceptshift_common -e /src/python/perceptshift_api
  export PERCEPTSHIFT_ROS_E2E_REQUIRED=1
  export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
  /tmp/ps-e2e-venv/bin/python -m pytest -c /dev/null /src/tests/e2e/test_api_ros_integration.py -rs -vv --tb=short
fi
"
