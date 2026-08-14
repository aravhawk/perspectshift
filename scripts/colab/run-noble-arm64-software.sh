#!/usr/bin/env bash
# Run required software tiers inside Ubuntu 24.04 arm64 (native or Colima).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOG_DIR="${ROOT}/build/verification/logs"
mkdir -p "$LOG_DIR" "${ROOT}/.cache"
LOG="${LOG_DIR}/noble-arm64-software.log"

{
  echo "=== noble arm64 software tier ==="
  uname -a
  cat /etc/os-release | head -8
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq \
    build-essential cmake ninja-build git curl ca-certificates \
    pkg-config libssl-dev python3 python3-pip python3-venv \
    clang llvm >/dev/null

  ORT_VER=1.28.0
  ORT_TGZ="onnxruntime-linux-aarch64-${ORT_VER}.tgz"
  ORT_URL="https://github.com/microsoft/onnxruntime/releases/download/v${ORT_VER}/${ORT_TGZ}"
  ORT_ROOT="${ROOT}/.cache/onnxruntime-linux-aarch64-${ORT_VER}"
  if [[ ! -f "${ORT_ROOT}/include/onnxruntime_cxx_api.h" ]]; then
    mkdir -p "${ROOT}/.cache"
    curl -fsSL "$ORT_URL" -o "/tmp/${ORT_TGZ}"
    rm -rf "$ORT_ROOT"
    mkdir -p "$ORT_ROOT"
    tar -xzf "/tmp/${ORT_TGZ}" -C "$ORT_ROOT" --strip-components=1
  fi
  export PERCEPTSHIFT_ORT_ROOT="$ORT_ROOT"
  export LD_LIBRARY_PATH="${ORT_ROOT}/lib:${LD_LIBRARY_PATH:-}"

  cd "$ROOT"
  rm -rf build/noble-arm64
  cmake -S . -B build/noble-arm64 -G Ninja \
    -DCMAKE_BUILD_TYPE=RelWithDebInfo \
    -DPERCEPTSHIFT_BUILD_TESTS=ON \
    -DPERCEPTSHIFT_WITH_ONNXRUNTIME=ON \
    -DPERCEPTSHIFT_ORT_ROOT="${ORT_ROOT}"
  cmake --build build/noble-arm64 -j "$(nproc)"
  ctest --test-dir build/noble-arm64 --output-on-failure

  # Sanitizers
  cmake -S . -B build/noble-arm64-asan-ubsan -G Ninja \
    -DCMAKE_BUILD_TYPE=Debug \
    -DPERCEPTSHIFT_ENABLE_ASAN=ON \
    -DPERCEPTSHIFT_ENABLE_UBSAN=ON \
    -DPERCEPTSHIFT_WITH_ONNXRUNTIME=ON \
    -DPERCEPTSHIFT_ORT_ROOT="${ORT_ROOT}"
  cmake --build build/noble-arm64-asan-ubsan -j "$(nproc)"
  ctest --test-dir build/noble-arm64-asan-ubsan --output-on-failure

  # TSan on recent Ubuntu kernels can fail discovery with
  # "unexpected memory mapping" when ASLR entropy is high.
  if [[ -w /proc/sys/vm/mmap_rnd_bits ]]; then
    echo 28 >/proc/sys/vm/mmap_rnd_bits || true
  elif command -v sysctl >/dev/null 2>&1; then
    sysctl -w vm.mmap_rnd_bits=28 || true
  fi

  cmake -S . -B build/noble-arm64-tsan -G Ninja \
    -DCMAKE_BUILD_TYPE=Debug \
    -DPERCEPTSHIFT_ENABLE_TSAN=ON \
    -DPERCEPTSHIFT_WITH_ONNXRUNTIME=ON \
    -DPERCEPTSHIFT_ORT_ROOT="${ORT_ROOT}"
  cmake --build build/noble-arm64-tsan -j "$(nproc)"
  ctest --test-dir build/noble-arm64-tsan --output-on-failure

  # Prefer RelWithDebInfo fuzz binaries from the primary build tree.
  FUZZ_DURATION_SECONDS=3 ./scripts/run-fuzz.sh

  echo "NOBLE_ARM64_SOFTWARE_OK"
} 2>&1 | tee "$LOG"
