#!/usr/bin/env bash
# Regression: verify-repository.sh must pass -g before each exclusion glob and
# still catch injected prohibited markers in product source.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

TMP_MARKER=""
cleanup() {
  if [[ -n "$TMP_MARKER" && -f "$TMP_MARKER" ]]; then
    rm -f "$TMP_MARKER"
  fi
}
trap cleanup EXIT

echo "== verify-repository must pass with a normal .git/hooks directory =="
if [[ ! -d .git/hooks ]]; then
  echo "FAIL: expected .git/hooks to exist for this regression"
  exit 1
fi
./scripts/verify-repository.sh
echo "PASS: baseline verify-repository"

echo "== verify-repository must fail on an injected prohibited marker =="
TMP_MARKER="python/perceptshift_common/src/perceptshift_common/_verify_repo_probe.py"
mkdir -p "$(dirname "$TMP_MARKER")"
cat >"$TMP_MARKER" <<'EOF'
# Temporary probe for verify-repository regression; must never remain committed.
# competition-specific evaluator-facing score optimization
EOF
set +e
./scripts/verify-repository.sh >/tmp/perceptshift-verify-repo-probe.log 2>&1
rc=$?
set -e
rm -f "$TMP_MARKER"
TMP_MARKER=""
if [[ "$rc" -eq 0 ]]; then
  echo "FAIL: verifier did not catch injected event-language marker"
  cat /tmp/perceptshift-verify-repo-probe.log
  exit 1
fi
if ! grep -q 'event/competition/evaluator language found' /tmp/perceptshift-verify-repo-probe.log; then
  echo "FAIL: expected event-language failure message"
  cat /tmp/perceptshift-verify-repo-probe.log
  exit 1
fi
echo "PASS: injected marker detected"

echo "== confirm .git is not searched as product content via broken glob expansion =="
# Re-run and ensure no .git/hooks sample file is cited as a hit.
./scripts/verify-repository.sh >/tmp/perceptshift-verify-repo-clean.log 2>&1
if grep -E '\.git/hooks/' /tmp/perceptshift-verify-repo-clean.log; then
  echo "FAIL: .git/hooks content leaked into product scans"
  exit 1
fi
echo "PASS: .git excluded from product scans"
echo "ALL verify-repository glob regressions passed"
