#!/usr/bin/env bash
# Build all PerceptShift components available on the current host.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

WITH_ROS="${WITH_ROS:-0}"
PRESET="${PRESET:-}"
ARCH="$(uname -m)"

if [[ -z "$PRESET" ]]; then
  case "$ARCH" in
    aarch64|arm64) PRESET=dev-arm64 ;;
    *) PRESET=dev-x64 ;;
  esac
fi

echo "Building with CMake preset: $PRESET"
if [[ -f CMakePresets.json ]]; then
  cmake --preset "$PRESET"
  cmake --build --preset "$PRESET"
else
  mkdir -p build
  cmake -S . -B build -DCMAKE_BUILD_TYPE=RelWithDebInfo
  cmake --build build -j
fi

if [[ -d python ]]; then
  if ! command -v uv >/dev/null 2>&1; then
    echo "uv is required to build Python packages" >&2
    exit 1
  fi
  uv sync --all-packages
fi

if [[ -d web && -f web/package.json ]]; then
  if ! command -v pnpm >/dev/null 2>&1; then
    echo "pnpm is required to build web console" >&2
    exit 1
  fi
  (cd web && pnpm install && pnpm build)
fi

if [[ "$WITH_ROS" == "1" ]]; then
  if ! command -v ros2 >/dev/null 2>&1 || [[ ! -d ros2_ws ]]; then
    echo "ROS build requested but ros2/colcon/ros2_ws unavailable" >&2
    exit 1
  fi
  # shellcheck disable=SC1091
  source /opt/ros/jazzy/setup.bash
  (cd ros2_ws && colcon build --symlink-install)
fi

echo "build-all.sh complete"
