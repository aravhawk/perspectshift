#!/usr/bin/env bash
# Deterministic product-source fingerprint. Always content-based (tree:<sha256>).
# Git commit hash is never the release identity.
set -euo pipefail

ROOT="${PERCEPTSHIFT_FINGERPRINT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$ROOT"

is_excluded() {
  local rel="$1"
  case "$rel" in
    ./.git|/*/.git/*|./.git/*) return 0 ;;
  esac
  case "$rel" in
    ./build/*|./.cache/*|./.venv/*|./venv/*|./node_modules/*|*/node_modules/*) return 0 ;;
    ./dist/*|./web/dist/*|./web/apps/console/dist/*|./web/test-results/*|./web/playwright-report/*) return 0 ;;
    ./coverage/*|./htmlcov/*|./.pytest_cache/*|*/.pytest_cache/*) return 0 ;;
    ./.mypy_cache/*|*/.mypy_cache/*|./.ruff_cache/*|*/.ruff_cache/*|./.tox/*) return 0 ;;
    ./ros2_ws/build/*|./ros2_ws/install/*|./ros2_ws/log/*) return 0 ;;
    */__pycache__/*|*.egg-info/*|*/.eggs/*) return 0 ;;
    ./release-evidence/*|./release-artifacts/*) return 0 ;;
  esac
  local base
  base="$(basename "$rel")"
  case "$base" in
    .DS_Store|.coverage|coverage.xml|.coverage.*) return 0 ;;
  esac
  if [[ "$base" == PERCEPTSHIFT_*.md ]]; then
    if [[ "$base" =~ PERCEPTSHIFT_.*(PROMPT|GAUNTLET|FINISHER|FINAL|PATCH|REPAIR|MULTITASK|LOCK) ]]; then
      return 0
    fi
  fi
  return 1
}

TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

(
  cd "$ROOT"
  find . -type f -print | LC_ALL=C sort | while IFS= read -r f; do
    if is_excluded "$f"; then
      continue
    fi
    if command -v sha256sum >/dev/null 2>&1; then
      h=$(sha256sum "$f" | awk '{print $1}')
    else
      h=$(shasum -a 256 "$f" | awk '{print $1}')
    fi
    mode="-"
    if [[ -x "$f" ]]; then
      mode="x"
    fi
    printf '%s  %s  %s\n' "$h" "$mode" "$f"
  done
) >"$TMP"

if command -v sha256sum >/dev/null 2>&1; then
  echo "tree:$(sha256sum "$TMP" | awk '{print $1}')"
else
  echo "tree:$(shasum -a 256 "$TMP" | awk '{print $1}')"
fi
