#!/usr/bin/env bash
# Clean-room verification from source manifest or tracked/exportable tree.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${CLEANROOM_OUT:-$ROOT/build/verification/clean-room}"
SOURCE_ARCHIVE="${SOURCE_ARCHIVE:-}"
SOURCE_MANIFEST="${SOURCE_MANIFEST:-}"
WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/perceptshift-cleanroom.XXXXXX")"
trap 'rm -rf "$WORKDIR"' EXIT

mkdir -p "$OUT_DIR"
echo "Clean-room workdir: $WORKDIR"

if [[ -n "$SOURCE_ARCHIVE" ]]; then
  tar -xzf "$SOURCE_ARCHIVE" -C "$WORKDIR"
elif [[ -n "$SOURCE_MANIFEST" ]]; then
  echo "SOURCE_MANIFEST mode requires pre-expanded tree at WORKDIR; unsupported alone" >&2
  exit 2
elif git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1 && git -C "$ROOT" rev-parse HEAD >/dev/null 2>&1; then
  git -C "$ROOT" archive --format=tar HEAD | tar -x -C "$WORKDIR"
else
  # Explicit source-manifest mode for uncommitted trees: copy sanitized sources.
  rsync -a \
    --exclude '.git' \
    --exclude 'build' \
    --exclude '.cache' \
    --exclude 'node_modules' \
    --exclude '.venv' \
    --exclude 'venv' \
    --exclude 'dist' \
    --exclude 'coverage' \
    --exclude '.pytest_cache' \
    --exclude '.mypy_cache' \
    --exclude '.ruff_cache' \
    --exclude 'release-evidence' \
    --exclude 'release-artifacts' \
    --exclude '.env' \
    "$ROOT/" "$WORKDIR/"
fi

cd "$WORKDIR"

VERIFY_REPO="fail"
MAKE_VERIFY="fail"
BOOTSTRAP="skipped_non_linux"
STARTED="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
EXIT_CODE=0

if [[ "$(uname -s)" == "Linux" ]]; then
  BOOTSTRAP="attempted"
  if ./scripts/bootstrap-ubuntu.sh --noninteractive; then
    BOOTSTRAP="pass"
  else
    BOOTSTRAP="failed"
    EXIT_CODE=1
  fi
fi

if ./scripts/verify-repository.sh; then
  VERIFY_REPO="pass"
else
  VERIFY_REPO="fail"
  EXIT_CODE=1
fi

if ./scripts/clean-room-acceptance.sh; then
  MAKE_VERIFY="pass"
else
  MAKE_VERIFY="fail"
  EXIT_CODE=1
fi

FINISHED="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
SUMMARY="$OUT_DIR/clean-room-summary.json"
cat >"$SUMMARY" <<JSON
{
  "workdir": "$WORKDIR",
  "started_at": "$STARTED",
  "bootstrap": "$BOOTSTRAP",
  "verify_repository": "$VERIFY_REPO",
  "make_verify": "$MAKE_VERIFY",
  "finished_at": "$FINISHED",
  "exit_code": $EXIT_CODE
}
JSON

echo "Clean-room summary written to $SUMMARY"
exit "$EXIT_CODE"
