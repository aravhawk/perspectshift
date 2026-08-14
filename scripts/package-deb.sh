#!/usr/bin/env bash
# Canonical complete Debian release package. Never silently emit a ROS-incomplete artifact.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${DIST_DIR:-$ROOT/dist}"
mkdir -p "$OUT_DIR"

if [[ ! -f /opt/ros/jazzy/setup.bash ]]; then
  echo "ERROR: make package / scripts/package-deb.sh requires ROS 2 Jazzy." >&2
  echo "Install ROS Jazzy or run the Arm64 Docker packaging path (debian-acceptance / clean-room)." >&2
  echo "For a non-release C++ core developer artifact, use: make package-core-dev" >&2
  exit 2
fi

ORT_OK=0
if [[ -n "${PERCEPTSHIFT_ORT_ROOT:-}" && -d "${PERCEPTSHIFT_ORT_ROOT}/lib" ]]; then
  ORT_OK=1
fi
if [[ -d "$ROOT/.cache/onnxruntime-linux-aarch64-1.28.0/lib" ]]; then
  ORT_OK=1
fi
if [[ "$ORT_OK" -ne 1 ]]; then
  echo "ERROR: complete release packaging requires ONNX Runtime libraries." >&2
  echo "Set PERCEPTSHIFT_ORT_ROOT or populate .cache/onnxruntime-linux-aarch64-1.28.0" >&2
  echo "For a non-release C++ core developer artifact, use: make package-core-dev" >&2
  exit 2
fi

echo "Using scripts/build-release-deb.sh (complete supported release package)"
exec "$ROOT/scripts/build-release-deb.sh"
