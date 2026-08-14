#!/usr/bin/env bash
# Fresh project-owned warning-as-error C++ and ROS build (linux/arm64).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLATFORM="${DOCKER_PLATFORM:-linux/arm64}"
ORT_LINUX="$ROOT/.cache/onnxruntime-linux-aarch64-1.28.0"

arch="$(docker run --rm --platform "$PLATFORM" ubuntu:24.04 uname -m)"
[[ "$arch" == "aarch64" ]] || { echo "expected aarch64, got $arch" >&2; exit 1; }
[[ -d "$ORT_LINUX/lib" ]] || { echo "missing $ORT_LINUX" >&2; exit 1; }

NAME="ps-warnings-$$"
cleanup() { docker rm -f "$NAME" >/dev/null 2>&1 || true; }
trap cleanup EXIT

docker run -d --name "$NAME" --platform "$PLATFORM" \
  -v "$ROOT:/src:ro" \
  -v "$ROOT/.cache:/cache:ro" \
  ros:jazzy-ros-base sleep infinity >/dev/null

docker exec "$NAME" bash -lc '
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
set +u; source /opt/ros/jazzy/setup.bash; set -u
apt-get update -qq
apt-get install -y -qq build-essential cmake ninja-build git python3 python3-pip python3-venv \
  python3-setuptools python3-colcon-common-extensions nlohmann-json3-dev libssl-dev zlib1g-dev \
  rsync \
  ros-jazzy-rclcpp-lifecycle ros-jazzy-rclcpp-components ros-jazzy-sensor-msgs \
  ros-jazzy-diagnostic-updater ros-jazzy-launch-ros ros-jazzy-lifecycle-msgs \
  ros-jazzy-rclpy ros-jazzy-image-transport ros-jazzy-cv-bridge \
  ros-jazzy-ament-cmake-gtest >/dev/null
rm -rf /work
mkdir -p /work
rsync -a --exclude build --exclude .venv --exclude .cache --exclude node_modules \
  --exclude dist --exclude .git --exclude ros2_ws/build --exclude ros2_ws/install \
  --exclude ros2_ws/log --exclude release-evidence --exclude release-artifacts \
  /src/ /work/
mkdir -p /work/.cache
cp -a /cache/onnxruntime-linux-aarch64-1.28.0 /work/.cache/
cd /work
export PERCEPTSHIFT_ORT_ROOT=/work/.cache/onnxruntime-linux-aarch64-1.28.0
rm -rf /work/build/warnings-fresh
cmake -S . -B /work/build/warnings-fresh -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DPERCEPTSHIFT_ORT_ROOT="$PERCEPTSHIFT_ORT_ROOT" \
  -DPERCEPTSHIFT_BUILD_TESTS=ON \
  -DPERCEPTSHIFT_WARNINGS_AS_ERRORS=ON
cmake --build /work/build/warnings-fresh -j2
cmake --install /work/build/warnings-fresh --prefix /opt/perceptshift
export CMAKE_PREFIX_PATH=/opt/perceptshift:${CMAKE_PREFIX_PATH:-}
export LD_LIBRARY_PATH=$PERCEPTSHIFT_ORT_ROOT/lib:/opt/perceptshift/lib/perceptshift:/opt/perceptshift/lib:${LD_LIBRARY_PATH:-}
cd /work/ros2_ws
rm -rf build install log
colcon build --cmake-args \
  -DCMAKE_BUILD_TYPE=Release \
  -DPERCEPTSHIFT_WARNINGS_AS_ERRORS=ON \
  -DCMAKE_CXX_FLAGS="-isystem /opt/ros/jazzy/include"
echo "cpp_build_warnings fresh build OK"
'
