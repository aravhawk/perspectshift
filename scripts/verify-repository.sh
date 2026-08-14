#!/usr/bin/env bash
# Verify repository policy for PerceptShift tracked product content.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

FAIL=0
WARN=0

red() { printf 'ERROR: %s\n' "$*" >&2; }
yellow() { printf 'WARN: %s\n' "$*" >&2; }
green() { printf 'OK: %s\n' "$*"; }

note_fail() {
  red "$1"
  FAIL=$((FAIL + 1))
}

note_warn() {
  yellow "$1"
  WARN=$((WARN + 1))
}

# Paths excluded from product-content scans. Each entry is a ripgrep --glob value.
EXCLUDE_GLOBS=(
  '!.git/**'
  '!.venv/**'
  '!**/.venv/**'
  '!**/node_modules/**'
  '!**/.cache/**'
  '!**/build/**'
  '!**/install/**'
  '!**/log/**'
  '!**/dist/**'
  '!**/__pycache__/**'
  '!**/.pytest_cache/**'
  '!**/.ruff_cache/**'
  # Nested verification logs in durable evidence must not re-trigger product scans.
  '!release-evidence/**'
  '!release-artifacts/**'
  '!tests/test_verify_repository_globs.sh'
  '!tests/test_release_contracts.sh'
  '!.github/pull_request_template.md'
  '!.github/workflows/docs.yml'
)

# Expand EXCLUDE_GLOBS into repeated -g arguments for ripgrep.
rg_exclude_args() {
  local args=()
  local g
  for g in "${EXCLUDE_GLOBS[@]}"; do
    args+=(-g "$g")
  done
  printf '%s\0' "${args[@]}"
}

# Run rg with correctly expanded exclusion globs. Remaining args are passed to rg.
run_rg() {
  local -a excl=()
  local g
  for g in "${EXCLUDE_GLOBS[@]}"; do
    excl+=(-g "$g")
  done
  rg -n --hidden "${excl[@]}" "$@"
}

has_rg() { command -v rg >/dev/null 2>&1; }

echo "=== PerceptShift repository verification ==="
echo "root: $ROOT"

# --- Prohibited tracked binaries / large data / results ---
echo
echo "-- prohibited binaries / oversized tracked files --"
# Model/weight/dataset extensions. Exclude virtualenvs, node_modules, build caches.
PROHIBITED_EXT_REGEX='\.(onnx|pt|pb|tflite|engine|bag|mcap|h5|hdf5|ckpt|safetensors|npy)$'
# .pth is ambiguous (PyTorch vs Python path config); only flag outside site-packages/.venv.
PTH_MODEL_REGEX='\.pth$'
while IFS= read -r -d '' f; do
  rel="${f#./}"
  case "$rel" in
    .git/*|build/*|.cache/*|dist/*|node_modules/*|.venv/*|*/.venv/*|*/site-packages/*|*/__pycache__/*|release-evidence/*) continue ;;
  esac
  if [[ "$rel" =~ $PROHIBITED_EXT_REGEX ]]; then
    note_fail "prohibited binary/data artifact tracked: $rel"
  fi
  if [[ "$rel" =~ $PTH_MODEL_REGEX ]]; then
    note_fail "prohibited model weight artifact tracked: $rel"
  fi
  # Size check: >5MiB outside allowed caches
  size=$(wc -c <"$f" | tr -d ' ')
  if [[ "$size" -gt $((5 * 1024 * 1024)) ]]; then
    note_fail "file exceeds 5MiB without allowlist: $rel ($size bytes)"
  fi
done < <(find . -type f \
  -not -path './.git/*' \
  -not -path './.venv/*' \
  -not -path '*/.venv/*' \
  -not -path '*/node_modules/*' \
  -not -path './build/*' \
  -not -path './.cache/*' \
  -not -path './dist/*' \
  -not -path './release-evidence/*' \
  -print0 2>/dev/null)

# Precomputed result path patterns
if has_rg; then
  if run_rg \
    '(benchmark[_-]results?|precomputed[_-]benchmark|mock[_-]dataset|sample[_-]model\.onnx)' \
    -g '!scripts/verify-repository.sh' . 2>/dev/null | head -n 20 | grep -q .; then
    note_fail "prohibited result/data naming patterns found (see rg output above)"
    run_rg \
      '(benchmark[_-]results?|precomputed[_-]benchmark|mock[_-]dataset|sample[_-]model\.onnx)' \
      -g '!scripts/verify-repository.sh' . 2>/dev/null | head -n 40 || true
  else
    green "no prohibited result/data naming patterns"
  fi
else
  note_warn "rg not installed; skipped pattern naming check"
fi

# --- TODO / FIXME / stub patterns ---
echo
echo "-- incomplete-work markers --"
# Allowlist: third-party, generated, and this verifier's self-reference patterns.
ALLOW_TODO='(scripts/verify-repository\.sh|third_party/|vendor/|\.pb\.cc|\.pb\.h|node_modules/)'
if has_rg; then
  TODO_HITS=$(run_rg \
    '(TODO|FIXME|NotImplementedError|throw new Error\(["'\'']not implemented|pass\s*#\s*unimplemented|\.\.\.\s*#\s*stub)' \
    -g '!*.md' \
    . 2>/dev/null | grep -Ev "$ALLOW_TODO" || true)
  if [[ -n "$TODO_HITS" ]]; then
    note_fail "TODO/FIXME/stub markers in product source"
    printf '%s\n' "$TODO_HITS" | head -n 50
  else
    green "no production TODO/FIXME/stub markers"
  fi
else
  note_warn "rg not installed; skipped TODO/FIXME scan"
fi

# --- Event / competition / evaluator language ---
echo
echo "-- event-specific prohibited language --"
if has_rg; then
  EVENT_HITS=$(run_rg -i \
    '(competition[- ]specific|event[- ]specific|evaluator[- ]facing|submission[- ]portal|prize[- ]specific|pitch deck|score optimization|hackathon|grand prize)' \
    -g '!scripts/verify-repository.sh' \
    . 2>/dev/null || true)
  if [[ -n "$EVENT_HITS" ]]; then
    note_fail "event/competition/evaluator language found in product content"
    printf '%s\n' "$EVENT_HITS" | head -n 50
  else
    green "no event-specific prohibited language"
  fi
else
  note_warn "rg not installed; skipped event-language scan"
fi

# --- Secrets ---
echo
echo "-- secrets --"
SECRET_PATTERNS='(BEGIN (RSA |OPENSSH |EC )?PRIVATE KEY|aws_secret_access_key|xox[baprs]-|ghp_[A-Za-z0-9]{20,}|PERCEPTSHIFT_API_TOKEN=[^$\s{])'
if has_rg; then
  SECRET_HITS=$(run_rg -i "$SECRET_PATTERNS" \
    -g '!.env.example' \
    -g '!**/*.template.*' \
    -g '!scripts/verify-repository.sh' \
    . 2>/dev/null || true)
  if [[ -n "$SECRET_HITS" ]]; then
    note_fail "possible secrets detected"
    printf '%s\n' "$SECRET_HITS" | head -n 30
  else
    green "no obvious secrets"
  fi
else
  note_warn "rg not installed; skipped secret scan"
fi

if [[ -f .env ]]; then
  note_fail ".env file present in repository root (secrets policy)"
fi

# --- Executable-bit sanity for scripts ---
echo
echo "-- executable bits --"
for s in scripts/*.sh; do
  [[ -f "$s" ]] || continue
  if [[ ! -x "$s" ]]; then
    note_fail "script is not executable: $s"
  fi
done
green "scripts executable-bit check complete"

# --- Orchestration prompts and OS junk ---
echo
echo "-- orchestration prompts / .DS_Store --"
while IFS= read -r -d '' f; do
  rel="${f#./}"
  case "$rel" in
    .git/*|release-evidence/*|release-artifacts/*|build/*|.venv/*|.cache/*|node_modules/*) continue ;;
    */node_modules/*|*/.venv/*) continue ;;
  esac
  note_fail "forbidden .DS_Store present: $rel"
done < <(find . -name '.DS_Store' -print0 2>/dev/null)

while IFS= read -r -d '' f; do
  rel="${f#./}"
  case "$rel" in
    .git/*|release-evidence/*|release-artifacts/*|build/*|.venv/*|.cache/*) continue ;;
  esac
  base="$(basename "$rel")"
  if [[ "$base" =~ ^PERCEPTSHIFT_.*(PROMPT|GAUNTLET|FINISHER|FINAL|PATCH|REPAIR|MULTITASK|LOCK).*\.md$ ]]; then
    note_fail "orchestration prompt present in product tree: $rel"
  fi
done < <(find . -type f -name 'PERCEPTSHIFT_*.md' -print0 2>/dev/null)

# --- Release command / CI contracts ---
echo
echo "-- release command contracts --"
if [[ -x "$ROOT/tests/test_release_contracts.sh" ]]; then
  if ! "$ROOT/tests/test_release_contracts.sh"; then
    note_fail "release contract tests failed"
  else
    green "release contract tests passed"
  fi
else
  note_fail "tests/test_release_contracts.sh missing or not executable"
fi

if [[ -x "$ROOT/tests/test_source_fingerprint.sh" ]]; then
  if ! "$ROOT/tests/test_source_fingerprint.sh"; then
    note_fail "source fingerprint regression tests failed"
  else
    green "source fingerprint regression tests passed"
  fi
else
  note_fail "tests/test_source_fingerprint.sh missing or not executable"
fi

if [[ -x "$ROOT/tests/test_deployment_surface.sh" ]]; then
  if ! "$ROOT/tests/test_deployment_surface.sh"; then
    note_fail "deployment surface tests failed"
  else
    green "deployment surface tests passed"
  fi
else
  note_fail "tests/test_deployment_surface.sh missing or not executable"
fi

# --- Lock files ---
echo
echo "-- lock files --"
if [[ -f pnpm-workspace.yaml ]] || [[ -f web/package.json ]]; then
  if [[ ! -f web/pnpm-lock.yaml ]] && [[ ! -f pnpm-lock.yaml ]]; then
    note_warn "pnpm lockfile missing (web workspace may still be initializing)"
  else
    green "pnpm lockfile present or workspace pending"
  fi
fi
if [[ -f pyproject.toml ]]; then
  if [[ ! -f uv.lock ]]; then
    note_warn "uv.lock missing (Python workspace may still be initializing)"
  else
    green "uv.lock present"
  fi
fi

# --- Schema validity ---
echo
echo "-- schema validity --"
SCHEMA_DIR="config/schemas"
if [[ -d "$SCHEMA_DIR" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    python3 - <<'PY' || note_fail "JSON schema parse failure"
import json, pathlib, sys
root = pathlib.Path("config/schemas")
errors = 0
for path in sorted(root.glob("*.schema.json")):
    try:
        json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"INVALID: {path}: {exc}", file=sys.stderr)
        errors += 1
if errors:
    sys.exit(1)
print(f"validated {len(list(root.glob('*.schema.json')))} schema files")
PY
    green "schemas are valid JSON"
  else
    note_warn "python3 unavailable; skipped schema JSON parse"
  fi
else
  note_fail "config/schemas directory missing"
fi

# --- Broken symlinks ---
echo
echo "-- broken symlinks --"
BROKEN=0
while IFS= read -r -d '' link; do
  case "$link" in
    ./build/*|./ros2_ws/build/*|./ros2_ws/install/*|./ros2_ws/log/*|./*.venv/*|./.venv/*|./node_modules/*|./web/node_modules/*)
      continue
      ;;
  esac
  if [[ ! -e "$link" ]]; then
    note_fail "broken symlink: $link"
    BROKEN=$((BROKEN + 1))
  fi
done < <(find . -type l -print0 2>/dev/null)
if [[ "$BROKEN" -eq 0 ]]; then
  green "no broken symlinks"
fi

# --- Source-tree run output ---
echo
echo "-- source-tree run output --"
for p in ros2_ws/log ros2_ws/install cpp/build build/verification; do
  if [[ -d "$p" ]] && [[ -n "$(find "$p" -type f 2>/dev/null | head -n 1)" ]]; then
    note_warn "run output directory present (should not be committed): $p"
  fi
done

# --- Safety language smoke (flag affirmative unsafe claims, not negations) ---
echo
echo "-- unsafe claim language in docs --"
if has_rg && [[ -d docs ]]; then
  # Match claims that assert capability, not sentences that forbid them.
  UNSAFE=$(rg -n -i \
    '(provides a hard real-time guarantee|is hard real-time|issues an emergency stop command|guarantees runtime accuracy|is a safety[- ]certified component|is functional[- ]safety certified)' \
    docs README.md SECURITY.md 2>/dev/null || true)
  if [[ -n "$UNSAFE" ]]; then
    note_fail "imprecise/unsafe claim language in docs"
    printf '%s\n' "$UNSAFE" | head -n 30
  else
    green "no imprecise safety-claim language detected in docs"
  fi
fi

echo
if [[ "$FAIL" -gt 0 ]]; then
  red "verify-repository FAILED with $FAIL error(s), $WARN warning(s)"
  exit 1
fi
green "verify-repository PASSED with $WARN warning(s)"
exit 0
