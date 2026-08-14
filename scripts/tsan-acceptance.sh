#!/usr/bin/env bash
# Dependency-scoped TSan: controller/queue concurrency without ORT.
# Prefer native host TSan (Colima QEMU user-mode rejects TSan mappings).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

run_host() {
  echo "TSan strategy: native host (ORT off; Controller|LatestFrame|Queue|RawImage)"
  cmake -S . -B build/tsan-host \
    -DPERCEPTSHIFT_ENABLE_TSAN=ON \
    -DPERCEPTSHIFT_WITH_ONNXRUNTIME=OFF \
    -DPERCEPTSHIFT_BUILD_TESTS=ON
  cmake --build build/tsan-host -j"$(sysctl -n hw.ncpu 2>/dev/null || nproc || echo 4)"
  ctest --test-dir build/tsan-host -R 'Controller|LatestFrame|Queue|RawImage' --output-on-failure
  echo "STATUS=PASS gate=tsan_or_documented_dependency_scoped_tsan host=$(uname -s)/$(uname -m) note=ORT_excluded_dependency_scoped"
}

run_linux_native_hint() {
  # Attempt Linux TSan only when not under QEMU (uname -m matches but /proc/cpuinfo may say QEMU).
  if grep -qi qemu /proc/cpuinfo 2>/dev/null; then
    echo "Linux under QEMU: TSan unsupported (unexpected memory mapping). Use host TSan." >&2
    return 1
  fi
  return 0
}

if [[ "$(uname -s)" == "Darwin" ]]; then
  run_host
  exit 0
fi

if run_linux_native_hint; then
  cmake -S . -B build/tsan \
    -DPERCEPTSHIFT_ENABLE_TSAN=ON \
    -DPERCEPTSHIFT_WITH_ONNXRUNTIME=OFF
  cmake --build build/tsan -j2
  ctest --test-dir build/tsan -R 'Controller|LatestFrame|Queue|RawImage' --output-on-failure
  echo "STATUS=PASS gate=tsan_or_documented_dependency_scoped_tsan host=linux note=ORT_excluded_dependency_scoped"
  exit 0
fi

# Fallback: still execute host path if available via nested darwin (should not reach here in docker).
echo "TSan unavailable in this environment" >&2
exit 1
