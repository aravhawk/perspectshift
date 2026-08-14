#!/usr/bin/env bash
# Build ONNX Runtime from official upstream sources with optional XNNPACK.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ORT_VERSION="${ORT_VERSION:-1.28.0}"
# Canonical install root. ORT_PREFIX is accepted as an alias for PERCEPTSHIFT_ORT_ROOT.
PREFIX="${PERCEPTSHIFT_ORT_ROOT:-${ORT_PREFIX:-$ROOT/.cache/onnxruntime}}"
SRC_DIR="${ORT_SRC:-$ROOT/.cache/onnxruntime-src}"
BUILD_DIR="${ORT_BUILD:-$ROOT/.cache/onnxruntime-build}"
JOBS="${JOBS:-$(sysctl -n hw.ncpu 2>/dev/null || nproc 2>/dev/null || echo 4)}"
ENABLE_XNNPACK="${ENABLE_XNNPACK:-1}"
ARCH="$(uname -m)"

usage() {
  cat <<'EOF'
Usage: build-onnxruntime.sh [options]

Environment:
  ORT_VERSION       ONNX Runtime git tag (default: 1.20.1)
  PERCEPTSHIFT_ORT_ROOT / ORT_PREFIX
                    Install prefix (default: .cache/onnxruntime)
  ORT_SRC           Source checkout directory
  ORT_BUILD         Build directory
  ENABLE_XNNPACK    1 to enable XNNPACK EP (default: 1)
  JOBS              Parallel build jobs
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

mkdir -p "$(dirname "$SRC_DIR")" "$PREFIX"

if [[ ! -d "$SRC_DIR/.git" ]]; then
  echo "Cloning ONNX Runtime $ORT_VERSION from official GitHub..."
  git clone --depth 1 --branch "v${ORT_VERSION}" \
    https://github.com/microsoft/onnxruntime.git "$SRC_DIR"
else
  echo "Using existing source at $SRC_DIR"
fi

# Record provenance for supply-chain verification.
git -C "$SRC_DIR" rev-parse HEAD >"$PREFIX/SOURCE_COMMIT.txt"
echo "$ORT_VERSION" >"$PREFIX/VERSION.txt"

XNNPACK_FLAG="--use_xnnpack"
if [[ "$ENABLE_XNNPACK" != "1" ]]; then
  XNNPACK_FLAG=""
fi

echo "Building ONNX Runtime for $ARCH with jobs=$JOBS"
cd "$SRC_DIR"
./build.sh \
  --config Release \
  --build_shared_lib \
  --parallel "$JOBS" \
  --skip_tests \
  --compile_no_warning_as_error \
  --build_dir "$BUILD_DIR" \
  $XNNPACK_FLAG \
  --cmake_extra_defines CMAKE_INSTALL_PREFIX="$PREFIX"

cmake --install "$BUILD_DIR/Release" --prefix "$PREFIX"

echo "Installed ONNX Runtime to $PREFIX"
echo "Set PERCEPTSHIFT_ORT_ROOT=$PREFIX (ORT_PREFIX is accepted as an alias)."
