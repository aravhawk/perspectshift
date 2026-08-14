#!/usr/bin/env bash
# Deterministic source-only export. Product source only — never evidence or artifacts.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

OUT_DIR="${SOURCE_EXPORT_DIR:-$ROOT/release-artifacts}"
mkdir -p "$OUT_DIR"
FP="$("$ROOT/scripts/source-fingerprint.sh")"
FP_SAFE="$(echo "$FP" | tr ':/' '_')"
ARCHIVE="$OUT_DIR/perceptshift-source-${FP_SAFE}.tar.gz"
STAGE="$(mktemp -d "${TMPDIR:-/tmp}/ps-export.XXXXXX")"
trap 'rm -rf "$STAGE"' EXIT

rsync -a \
  --exclude '.git/' \
  --exclude 'build/' \
  --exclude '.cache/' \
  --exclude '.venv/' \
  --exclude 'venv/' \
  --exclude 'node_modules/' \
  --exclude 'web/node_modules/' \
  --exclude 'web/dist/' \
  --exclude 'web/apps/console/dist/' \
  --exclude 'web/test-results/' \
  --exclude 'web/playwright-report/' \
  --exclude 'dist/' \
  --exclude 'coverage/' \
  --exclude 'htmlcov/' \
  --exclude '.pytest_cache/' \
  --exclude '**/.pytest_cache/' \
  --exclude '.mypy_cache/' \
  --exclude '**/.mypy_cache/' \
  --exclude '.ruff_cache/' \
  --exclude '**/.ruff_cache/' \
  --exclude '.tox/' \
  --exclude 'ros2_ws/build/' \
  --exclude 'ros2_ws/install/' \
  --exclude 'ros2_ws/log/' \
  --exclude '__pycache__/' \
  --exclude '*.egg-info/' \
  --exclude '.DS_Store' \
  --exclude '.coverage' \
  --exclude '.coverage.*' \
  --exclude 'coverage.xml' \
  --exclude '.env' \
  --exclude '*.pem' \
  --exclude '*.key' \
  --exclude 'release-evidence/' \
  --exclude 'release-artifacts/' \
  --exclude 'PERCEPTSHIFT_*PROMPT*.md' \
  --exclude 'PERCEPTSHIFT_*GAUNTLET*.md' \
  --exclude 'PERCEPTSHIFT_*FINISHER*.md' \
  --exclude 'PERCEPTSHIFT_*FINAL*.md' \
  --exclude 'PERCEPTSHIFT_*PATCH*.md' \
  --exclude 'PERCEPTSHIFT_*REPAIR*.md' \
  --exclude 'PERCEPTSHIFT_*MULTITASK*.md' \
  --exclude 'PERCEPTSHIFT_*LOCK*.md' \
  "$ROOT/" "$STAGE/"

FAIL=0
fail_if() {
  echo "ERROR: excluded path present in export: $1" >&2
  FAIL=1
}

while IFS= read -r bad; do
  fail_if "$bad"
done < <(
  (
    cd "$STAGE"
    find . \( \
      -path './.git' -o -path './.git/*' -o \
      -path './.venv' -o -path './.venv/*' -o \
      -path './build' -o -path './build/*' -o \
      -path './.cache' -o -path './.cache/*' -o \
      -path './node_modules' -o -path './node_modules/*' -o \
      -path '*/node_modules/*' -o \
      -path './dist' -o -path './dist/*' -o \
      -path './release-evidence' -o -path './release-evidence/*' -o \
      -path './release-artifacts' -o -path './release-artifacts/*' -o \
      -path './ros2_ws/build/*' -o -path './ros2_ws/install/*' -o \
      -path './ros2_ws/log/*' -o \
      -name '.DS_Store' -o \
      -name '.coverage' \
    \) -print 2>/dev/null
  )
)

while IFS= read -r prompt; do
  fail_if "$prompt"
done < <(
  (
    cd "$STAGE"
    find . -type f -name 'PERCEPTSHIFT_*.md' | while IFS= read -r f; do
      base="$(basename "$f")"
      if [[ "$base" =~ PERCEPTSHIFT_.*(PROMPT|GAUNTLET|FINISHER|FINAL|PATCH|REPAIR|MULTITASK|LOCK) ]]; then
        echo "$f"
      fi
    done
  )
)

[[ "$FAIL" -eq 0 ]] || exit 1

# Scripts intended for direct execution must retain executable mode.
while IFS= read -r script; do
  if [[ ! -x "$STAGE/$script" ]]; then
    echo "ERROR: script lost executable mode in export stage: $script" >&2
    FAIL=1
  fi
done < <(cd "$ROOT" && find scripts -maxdepth 1 -type f -name '*.sh' -print | sed 's|^\./||')
[[ "$FAIL" -eq 0 ]] || exit 1

rm -f "$ARCHIVE"
tar -C "$STAGE" -czf "$ARCHIVE" .
SIZE="$(wc -c <"$ARCHIVE" | tr -d ' ')"
if command -v sha256sum >/dev/null 2>&1; then
  SHA="$(sha256sum "$ARCHIVE" | awk '{print $1}')"
else
  SHA="$(shasum -a 256 "$ARCHIVE" | awk '{print $1}')"
fi
echo "$SHA  $(basename "$ARCHIVE")" >"${ARCHIVE}.sha256"

echo "source_export_archive=$ARCHIVE"
echo "source_export_bytes=$SIZE"
echo "source_export_sha256=$SHA"
echo "source_fingerprint=$FP"
echo "top_level:"
tar -tzf "$ARCHIVE" | awk -F/ 'NF<=2 {print}' | head -40

cat >"${ARCHIVE}.json" <<JSON
{
  "archive": "$(basename "$ARCHIVE")",
  "path": "release-artifacts/$(basename "$ARCHIVE")",
  "bytes": $SIZE,
  "sha256": "$SHA",
  "source_fingerprint": "$FP"
}
JSON
