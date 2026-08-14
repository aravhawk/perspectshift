#!/usr/bin/env bash
# Fail if release/CI contracts regress to incomplete packaging or suppressed failures.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
FAIL=0

fail() {
  echo "FAIL: $*" >&2
  FAIL=1
}

# make verify must invoke the complete release verifier.
if ! awk '
  $0 ~ /^verify:/ {in_t=1; next}
  in_t && $0 ~ /^[a-zA-Z0-9_.-]+:/ {exit}
  in_t {print}
' Makefile | grep -q 'release-verify.sh'; then
  fail "make verify does not invoke scripts/release-verify.sh"
fi
if awk '
  $0 ~ /^verify:/ {in_t=1; next}
  in_t && $0 ~ /^[a-zA-Z0-9_.-]+:/ {exit}
  in_t {print}
' Makefile | grep -q 'verify-all.sh --tier host_software'; then
  fail "make verify still maps to host-only verification"
fi
if ! grep -q '^verify-host:' Makefile; then
  fail "verify-host target missing"
fi

# make package must not mention incomplete CPack fallback.
if grep -q 'ROS overlay may be incomplete' scripts/package-deb.sh; then
  fail "scripts/package-deb.sh still contains incomplete CPack fallback language"
fi
if grep -q 'cpack -G DEB' scripts/package-deb.sh; then
  fail "canonical package-deb.sh still invokes cpack"
fi
if [[ ! -f scripts/package-core-dev.sh ]]; then
  fail "package-core-dev.sh missing for explicit non-release artifacts"
fi

# Release workflow must not call incomplete packaging as the release path.
if grep -E 'package-deb.sh|package-core-dev.sh' .github/workflows/release.yml >/dev/null; then
  if grep -n 'package-core-dev.sh' .github/workflows/release.yml >/dev/null; then
    fail "release.yml publishes the core-dev packaging path"
  fi
fi
if ! grep -q 'release-verify.sh' .github/workflows/release.yml; then
  fail "release.yml does not run the canonical release verifier"
fi
if ! grep -q 'final-verification.json' .github/workflows/release.yml; then
  fail "release.yml does not gate publication on final-verification.json"
fi

# Required workflow commands must not suppress failures with || true.
while IFS= read -r line; do
  # Allow documented non-required cleanup / optional probes only in comments.
  if [[ "$line" =~ \|\|[[:space:]]*true ]]; then
    fail "required-path || true in workflow: $line"
  fi
done < <(grep -n '|| true' .github/workflows/*.yml || true)

# Trivy HIGH/CRITICAL must fail closed.
if grep -A2 'severity: HIGH,CRITICAL' .github/workflows/container-scan.yml | grep -q 'exit-code: "0"'; then
  fail "Trivy HIGH/CRITICAL scan uses exit-code 0"
fi
if grep -q 'exit-code: "0"' .github/workflows/container-scan.yml; then
  fail "container-scan.yml still uses Trivy exit-code 0"
fi

# Compose must not be shipped without integrated acceptance.
if [[ -f deploy/containers/compose.yaml ]]; then
  if ! grep -q 'compose' scripts/container-acceptance.sh; then
    fail "official compose file exists without container-acceptance coverage"
  fi
fi

# Container builds must not fall back to unlocked installs.
if grep -E 'pnpm install --frozen-lockfile \|\| pnpm install' deploy/containers/Dockerfile.console; then
  fail "console Dockerfile abandons frozen lockfile"
fi
if grep -E 'pip install .*--upgrade' deploy/containers/Dockerfile.api | grep -v 'pip wheel' >/dev/null; then
  : # allow explicit pinned upgrades if any
fi

if [[ "$FAIL" -ne 0 ]]; then
  echo "release contract tests FAILED"
  exit 1
fi
echo "release contract tests PASSED"
