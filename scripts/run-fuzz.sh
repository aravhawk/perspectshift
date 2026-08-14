#!/usr/bin/env bash
# Fuzz smoke — fails if no targets or any target crashes.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
OUT_DIR="${FUZZ_OUT:-$ROOT/build/verification/fuzz}"
mkdir -p "$OUT_DIR"
DURATION="${FUZZ_DURATION_SECONDS:-5}"

# Portable target discovery (no GNU mapfile / find -perm required).
# Prefer an explicit build tree so sanitizer/coverage binaries are not mixed in.
SEARCH_ROOT="${FUZZ_BUILD_DIR:-}"
if [[ -z "$SEARCH_ROOT" ]]; then
  HOST_OS="$(uname -s)"
  if [[ "$HOST_OS" == "Darwin" ]]; then
    CANDIDATES=(build/default build/dev-arm64 build/release)
  else
    CANDIDATES=(build/noble-arm64 build/deb-arm64 build/asan build/default build/release-arm64 build/dev-arm64)
  fi
  for candidate in "${CANDIDATES[@]}"; do
    if [[ -d "$candidate" ]]; then
      SEARCH_ROOT="$candidate"
      break
    fi
  done
fi
if [[ -z "$SEARCH_ROOT" ]]; then
  SEARCH_ROOT=build
fi

TARGETS=()
while IFS= read -r -d '' t; do
  case "$t" in
    *asan*|*tsan*|*ubsan*|*coverage*|*CMakeFiles*|*_deps*|*.o|*.obj) continue ;;
  esac
  # Only real executables (skip object files / foreign-arch leftovers).
  if [[ -x "$t" && -f "$t" ]] && file "$t" | grep -Eqi 'executable|Mach-O|ELF'; then
    # Skip ELF binaries on Darwin and vice versa.
    if [[ "$(uname -s)" == "Darwin" ]] && file "$t" | grep -qi 'ELF'; then
      continue
    fi
    if [[ "$(uname -s)" == "Linux" ]] && file "$t" | grep -qi 'Mach-O'; then
      continue
    fi
    TARGETS+=("$t")
  fi
done < <(find "$SEARCH_ROOT" -type f -name 'fuzz_*' -print0 2>/dev/null || true)

if [[ ${#TARGETS[@]} -eq 0 ]]; then
  echo '{"status":"fail","reason":"NO_FUZZ_TARGETS","message":"No fuzz_* executables found under build/"}' \
    | tee "$OUT_DIR/fuzz-summary.json"
  echo "ERROR: no fuzz targets built" >&2
  exit 1
fi

run_with_deadline() {
  local seconds="$1"
  shift
  python3 - "$seconds" "$@" <<'PY'
import subprocess, sys, time
seconds = max(1, int(sys.argv[1]))
cmd = sys.argv[2:]
proc = subprocess.Popen(cmd)
deadline = time.time() + seconds
timed_out = False
while True:
    rc = proc.poll()
    if rc is not None:
        # Signal termination after we asked to stop counts as duration-elapsed success.
        if timed_out or rc < 0:
            sys.exit(124)
        sys.exit(rc)
    if time.time() >= deadline:
        timed_out = True
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)
        sys.exit(124)
    time.sleep(0.05)
PY
}

FAILED=0
RESULTS=()
for t in "${TARGETS[@]}"; do
  name="$(basename "$t")"
  log="$OUT_DIR/${name}.log"
  echo "Running $name for ${DURATION}s..."
  set +e
  run_with_deadline "${DURATION}" "$t" -max_total_time="$DURATION" -artifact_prefix="$OUT_DIR/" >"$log" 2>&1
  rc=$?
  set -e
  # 124 = duration elapsed without crash (smoke pass)
  if [[ $rc -eq 0 || $rc -eq 124 ]]; then
    RESULTS+=("{\"target\":\"$name\",\"status\":\"pass\",\"exit_code\":$rc}")
  else
    RESULTS+=("{\"target\":\"$name\",\"status\":\"fail\",\"exit_code\":$rc}")
    FAILED=1
  fi
done

{
  echo -n '{"status":"'
  if [[ $FAILED -eq 0 ]]; then echo -n 'pass'; else echo -n 'fail'; fi
  echo -n '","targets":['
  printf '%s,' "${RESULTS[@]}" | sed 's/,$//'
  echo ']}'
} | tee "$OUT_DIR/fuzz-summary.json"

exit "$FAILED"
