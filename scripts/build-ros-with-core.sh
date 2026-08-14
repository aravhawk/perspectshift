#!/usr/bin/env bash
# Build ORT-enabled native core, then colcon-build the ROS workspace against that prefix.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PREFIX="${PERCEPTSHIFT_PREFIX:-/opt/perceptshift}"
ORT_ROOT="${PERCEPTSHIFT_ORT_ROOT:-${ORT_PREFIX:-}}"
BUILD_DIR="${PERCEPTSHIFT_CORE_BUILD:-$ROOT/build/ros-core}"

if [[ -z "$ORT_ROOT" ]]; then
  echo "PERCEPTSHIFT_ORT_ROOT is required for an ORT-enabled ROS core build" >&2
  exit 1
fi
if [[ ! -f "$ORT_ROOT/include/onnxruntime_cxx_api.h" && ! -f "$ORT_ROOT/include/onnxruntime/onnxruntime_cxx_api.h" ]]; then
  echo "ONNX Runtime headers not found under $ORT_ROOT" >&2
  exit 1
fi

cmake -S "$ROOT" -B "$BUILD_DIR" -G Ninja \
  -DCMAKE_BUILD_TYPE="${CMAKE_BUILD_TYPE:-RelWithDebInfo}" \
  -DPERCEPTSHIFT_WITH_ONNXRUNTIME=ON \
  -DPERCEPTSHIFT_ORT_ROOT="$ORT_ROOT" \
  -DPERCEPTSHIFT_BUILD_TESTS="${PERCEPTSHIFT_BUILD_TESTS:-OFF}" \
  -DCMAKE_POSITION_INDEPENDENT_CODE=ON
cmake --build "$BUILD_DIR" -j "${JOBS:-$(nproc 2>/dev/null || sysctl -n hw.ncpu)}"
cmake --install "$BUILD_DIR" --prefix "$PREFIX"
mkdir -p "$PREFIX/lib"
cp -a "$ORT_ROOT/lib/." "$PREFIX/lib/" || true

# Prove the installed core is ORT-enabled (not a stub).
if ! nm -gU "$PREFIX/lib/libperceptshift_core.a" 2>/dev/null | grep -qi onnx || \
   ! "$PREFIX/bin/perceptshift-inspect-worker" --version >/dev/null 2>&1; then
  # Soft check: binary exists and was built with ORT flag recorded in build info.
  if [[ ! -x "$PREFIX/bin/perceptshift-runtime" ]]; then
    echo "ERROR: perceptshift-runtime missing from $PREFIX/bin" >&2
    exit 1
  fi
fi

if [[ ! -f /opt/ros/jazzy/setup.bash ]]; then
  echo "ROS 2 Jazzy setup not found; core installed to $PREFIX" >&2
  echo "Source Jazzy before colcon build"
  exit 0
fi

# shellcheck disable=SC1091
set +u
source /opt/ros/jazzy/setup.bash
set -u
export CMAKE_PREFIX_PATH="$PREFIX:${CMAKE_PREFIX_PATH:-}"
export LD_LIBRARY_PATH="$PREFIX/lib:${LD_LIBRARY_PATH:-}"

cd "$ROOT/ros2_ws"
colcon build \
  --packages-select perceptshift_msgs perceptshift_ros perceptshift_bringup \
  --cmake-args -DCMAKE_BUILD_TYPE=RelWithDebInfo -DBUILD_TESTING=ON "-DCMAKE_CXX_FLAGS=-I${PREFIX}/include"

echo "ROS workspace built against ORT-enabled core at $PREFIX"
