#!/usr/bin/env bash
# Native Arm64 acceptance gate. Fails if not running on AArch64.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${ARM_ACCEPTANCE_OUT:-$ROOT/build/verification/native-arm}"
mkdir -p "$OUT_DIR"

ARCH="$(uname -m)"
echo "Host architecture: $ARCH"
if [[ "$ARCH" != "aarch64" && "$ARCH" != "arm64" ]]; then
  cat >"$OUT_DIR/summary.json" <<EOF
{
  "status": "NOT_APPLICABLE",
  "reason": "host_not_aarch64",
  "uname_m": "$ARCH",
  "note": "Native Arm acceptance requires a real AArch64 host. Emulation is not a substitute.",
  "command": "./scripts/run-arm-acceptance.sh"
}
EOF
  echo "Native Arm acceptance NOT APPLICABLE on $ARCH" >&2
  exit 2
fi

cd "$ROOT"
export PERCEPTSHIFT_ORT_ROOT="${PERCEPTSHIFT_ORT_ROOT:-$ROOT/.cache/onnxruntime}"
export DYLD_LIBRARY_PATH="$PERCEPTSHIFT_ORT_ROOT/lib:${DYLD_LIBRARY_PATH:-}"
export LD_LIBRARY_PATH="$PERCEPTSHIFT_ORT_ROOT/lib:${LD_LIBRARY_PATH:-}"

./scripts/verify-repository.sh
PRESET=release-arm64
cmake --preset "$PRESET"
cmake --build --preset "$PRESET" -j

ctest --test-dir "build/$PRESET" --output-on-failure
./scripts/run-e2e.sh --native-arm --native-only

HOST_FP="$OUT_DIR/host-fingerprint.json"
"./build/$PRESET/cpp/perceptshift-runtime" --doctor >"$HOST_FP"

# Record XNNPACK availability truthfully from inspect worker when a model exists later;
# for acceptance, capture provider list from ORT via inspect --host.
"./build/$PRESET/cpp/perceptshift-inspect-worker" --host >"$OUT_DIR/inspect-host.json"

cat >"$OUT_DIR/summary.json" <<EOF
{
  "status": "PASS",
  "uname_m": "$ARCH",
  "preset": "$PRESET",
  "host_fingerprint_path": "$HOST_FP",
  "finished_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "note": "Software diagnostic timings are not product performance claims."
}
EOF
echo "Native Arm acceptance PASS: $OUT_DIR/summary.json"
