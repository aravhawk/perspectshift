#!/usr/bin/env bash
# Fingerprint is content-based regardless of Git commit state.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FP_SCRIPT="$ROOT/scripts/source-fingerprint.sh"
[[ -x "$FP_SCRIPT" ]] || { echo "source-fingerprint.sh not executable" >&2; exit 1; }

STAGE="$(mktemp -d "${TMPDIR:-/tmp}/ps-fp.XXXXXX")"
trap 'rm -rf "$STAGE"' EXIT

mkdir -p "$STAGE/scripts" "$STAGE/src"
cp "$FP_SCRIPT" "$STAGE/scripts/source-fingerprint.sh"
chmod +x "$STAGE/scripts/source-fingerprint.sh"
echo "hello product" >"$STAGE/src/file.txt"
mkdir -p "$STAGE/release-evidence/old" "$STAGE/release-artifacts"
echo "old evidence" >"$STAGE/release-evidence/old/note.txt"
echo "artifact" >"$STAGE/release-artifacts/skip.bin"

export PERCEPTSHIFT_FINGERPRINT_ROOT="$STAGE"
uncommitted="$("$STAGE/scripts/source-fingerprint.sh")"
[[ "$uncommitted" == tree:* ]] || { echo "expected tree: fingerprint, got $uncommitted" >&2; exit 1; }

git -C "$STAGE" init -q
git -C "$STAGE" config user.name "Fingerprint Test"
git -C "$STAGE" config user.email "fingerprint-test@example.invalid"
git -C "$STAGE" add src scripts
git -C "$STAGE" commit -q -m "identical source"
committed="$("$STAGE/scripts/source-fingerprint.sh")"
if [[ "$committed" != "$uncommitted" ]]; then
  echo "fingerprint changed after commit: $uncommitted -> $committed" >&2
  exit 1
fi
if [[ "$committed" == git:* ]]; then
  echo "fingerprint incorrectly switched to git: after commit" >&2
  exit 1
fi

echo "hello product changed" >"$STAGE/src/file.txt"
modified="$("$STAGE/scripts/source-fingerprint.sh")"
if [[ "$modified" == "$uncommitted" ]]; then
  echo "fingerprint did not change after product edit" >&2
  exit 1
fi

# Restore product file; evidence-only change must not alter fingerprint.
echo "hello product" >"$STAGE/src/file.txt"
echo "more evidence" >"$STAGE/release-evidence/old/note.txt"
evidence="$("$STAGE/scripts/source-fingerprint.sh")"
if [[ "$evidence" != "$uncommitted" ]]; then
  echo "fingerprint changed after evidence-only edit: $uncommitted -> $evidence" >&2
  exit 1
fi

echo "source fingerprint regressions PASSED ($uncommitted)"
