#!/usr/bin/env bash
# Enumerate advertised deployment surfaces and require a matching acceptance path.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
FAIL=0

fail() {
  echo "FAIL: $*" >&2
  FAIL=1
}

# Debian/systemd is advertised and must have package acceptance.
if [[ ! -f scripts/debian-acceptance.sh ]]; then
  fail "Debian/systemd advertised without debian-acceptance.sh"
fi
if [[ ! -f deploy/systemd/perceptshift-api.service ]]; then
  fail "API systemd unit missing"
fi
if [[ ! -f deploy/systemd/perceptshift-runtime.service ]]; then
  fail "runtime systemd unit missing"
fi

# Individual OCI images that remain must have acceptance coverage.
for df in deploy/containers/Dockerfile.runtime deploy/containers/Dockerfile.api deploy/containers/Dockerfile.console; do
  if [[ -f "$df" ]] && ! grep -q "$(basename "$df")" scripts/container-acceptance.sh; then
    fail "shipped $df is not covered by container-acceptance.sh"
  fi
done

# Compose is not a supported integrated surface unless an acceptance path exists.
if [[ -f deploy/containers/compose.yaml ]]; then
  fail "deploy/containers/compose.yaml is shipped; either delete it or add integrated compose E2E"
fi
hits="$(grep -R --include='*.md' -nE 'docker compose -f|docker compose up' docs README.md CONTRIBUTING.md 2>/dev/null || true)"
if [[ -n "$hits" ]]; then
  bad="$(echo "$hits" | grep -viE 'not |no supported|not shipped' || true)"
  if [[ -n "$bad" ]]; then
    fail "docs still advertise docker compose as a supported integrated stack"
    printf '%s\n' "$bad"
  fi
fi

if [[ "$FAIL" -ne 0 ]]; then
  echo "deployment surface tests FAILED"
  exit 1
fi
echo "deployment surface tests PASSED"
