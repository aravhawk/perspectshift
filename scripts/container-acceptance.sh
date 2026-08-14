#!/usr/bin/env bash
# Official OCI image acceptance (linux/arm64). No compose stack is shipped.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLATFORM="${DOCKER_PLATFORM:-linux/arm64}"
BUNDLE_HOST="${ROOT}/build/tmp/ps-container-bundle-$$"
POLICY_HOST="${ROOT}/build/tmp/ps-container-policy-$$.json"
mkdir -p "${ROOT}/build/tmp"

arch="$(docker run --rm --platform "$PLATFORM" ubuntu:24.04 uname -m)"
[[ "$arch" == "aarch64" ]] || { echo "expected aarch64" >&2; exit 1; }

API_NAME="ps-oci-api-$$"
CONSOLE_NAME="ps-oci-console-$$"
cleanup() {
  rm -rf "$BUNDLE_HOST" "$POLICY_HOST"
  docker rm -f "$API_NAME" "$CONSOLE_NAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT
rm -rf "$BUNDLE_HOST"
mkdir -p "$BUNDLE_HOST"

PYTHON="${ROOT}/.venv/bin/python"
[[ -x "$PYTHON" ]] || PYTHON=python3
"$PYTHON" - <<PY
from pathlib import Path
import sys
sys.path.insert(0, "${ROOT}/tests/e2e")
from bundle_fixture import write_classification_bundle
write_classification_bundle(Path("${BUNDLE_HOST}"))
print("bundle_ok")
PY
[[ -f "${BUNDLE_HOST}/manifest.json" ]] || { echo "bundle missing manifest.json" >&2; exit 1; }

assert_arch_nonroot() {
  local image="$1"
  local u arch
  arch="$(docker image inspect --format '{{.Architecture}}' "$image")"
  [[ "$arch" == "arm64" || "$arch" == "aarch64" ]] || { echo "$image arch=$arch" >&2; exit 1; }
  u="$(docker image inspect --format '{{.Config.User}}' "$image")"
  [[ -n "$u" && "$u" != "root" && "$u" != "0" ]] || { echo "$image user=$u" >&2; exit 1; }
  echo "ok image=$image arch=$arch user=$u"
}

echo "==> runtime image"
RUNTIME_IMAGE="perceptshift-runtime:local"
docker build --platform "$PLATFORM" -f "$ROOT/deploy/containers/Dockerfile.runtime" \
  -t "$RUNTIME_IMAGE" "$ROOT"
assert_arch_nonroot "$RUNTIME_IMAGE"
docker run --rm --platform "$PLATFORM" "$RUNTIME_IMAGE" --version
docker run --rm --platform "$PLATFORM" "$RUNTIME_IMAGE" --doctor --json >/dev/null

cat >"$POLICY_HOST" <<'EOF'
{"schema_version":"1.0","document_type":"perceptshift.runtime_policy","deadline_ms":500.0,"minimum_quality_value":0.0,"confidence_escalation_threshold":0.0,"maximum_source_age_ms":5000.0,"fail_closed_on_no_eligible_profile":true,"minimum_dwell_ms":0,"promotion_confirmation_frames":1,"demotion_confirmation_frames":1}
EOF

out="$(docker run --rm --platform "$PLATFORM" \
  -v "${BUNDLE_HOST}:/bundle:ro" \
  -v "${POLICY_HOST}:/policy.json:ro" \
  "$RUNTIME_IMAGE" \
  --bundle /bundle --signature-policy optional --policy /policy.json --verify-bundle --json)"
echo "$out"
echo "$out" | grep -q '"ok": true\|"ok":true'

echo "==> API image (artifact-store mode)"
API_IMAGE="perceptshift-api:local"
docker build --platform "$PLATFORM" -f "$ROOT/deploy/containers/Dockerfile.api" \
  -t "$API_IMAGE" "$ROOT"
assert_arch_nonroot "$API_IMAGE"
docker run -d --name "$API_NAME" --platform "$PLATFORM" "$API_IMAGE" >/dev/null
ok=0
for _ in $(seq 1 40); do
  if docker exec "$API_NAME" python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/v1/healthz')" >/dev/null 2>&1; then
    ok=1
    break
  fi
  sleep 0.5
done
[[ "$ok" == "1" ]] || { echo "API health failed"; docker logs "$API_NAME"; exit 1; }
docker exec "$API_NAME" python - <<'PY'
import json, urllib.request
health = json.loads(urllib.request.urlopen("http://127.0.0.1:8080/api/v1/healthz").read())
assert health.get("status") == "ok", health
ready = json.loads(urllib.request.urlopen("http://127.0.0.1:8080/api/v1/readyz").read())
assert ready.get("ready") is True, ready
caps = json.loads(urllib.request.urlopen("http://127.0.0.1:8080/api/v1/capabilities").read())
ros = str(caps.get("ros_bridge", "")).lower()
assert "connected" not in ros or ros in {"ros_unavailable", "ros_disabled", "unavailable"}, caps
status = json.loads(urllib.request.urlopen("http://127.0.0.1:8080/api/v1/runtime/status").read())
assert status.get("connected") is not True, status
assert status.get("mode") in {"artifact_store", "ros"}, status
if status.get("mode") == "ros":
    raise SystemExit(f"API image claimed ROS mode without ROS: {status}")
print("api_artifact_store_ok", json.dumps({"ready": ready, "caps": caps, "status": status}, default=str)[:500])
PY

echo "==> console image"
CONSOLE_IMAGE="perceptshift-console:local"
docker build --platform "$PLATFORM" -f "$ROOT/deploy/containers/Dockerfile.console" \
  -t "$CONSOLE_IMAGE" "$ROOT"
assert_arch_nonroot "$CONSOLE_IMAGE"
docker run -d --name "$CONSOLE_NAME" --platform "$PLATFORM" "$CONSOLE_IMAGE" >/dev/null
ok=0
html=""
for _ in $(seq 1 40); do
  if html="$(docker exec "$CONSOLE_NAME" wget -q -O - http://127.0.0.1:8080/ 2>/dev/null)"; then
    ok=1
    break
  fi
  sleep 0.5
done
[[ "$ok" == "1" ]] || { echo "console HTTP failed"; docker logs "$CONSOLE_NAME"; exit 1; }
echo "$html" | grep -qi '<html'
docker exec "$CONSOLE_NAME" wget -q -O /dev/null http://127.0.0.1:8080/healthz
# Fetch referenced local JS/CSS; fail on missing assets (load errors).
HTML="$html" python3 - "$CONSOLE_NAME" <<'PY'
import os, re, subprocess, sys
name = sys.argv[1]
html = os.environ["HTML"]
refs = re.findall(r'(?:src|href)="(/[^"]+\.(?:js|css))"', html)
assert refs, f"no js/css refs in console html: {html[:400]}"
for ref in refs:
    subprocess.run(
        ["docker", "exec", name, "wget", "-q", "-O", "/dev/null", f"http://127.0.0.1:8080{ref}"],
        check=True,
    )
print("console_static_ok", refs)
PY

[[ ! -f "$ROOT/deploy/containers/compose.yaml" ]] || {
  echo "compose.yaml is shipped without integrated acceptance" >&2
  exit 1
}

DIGEST="$(docker image inspect --format='{{index .RepoDigests 0}}' "$RUNTIME_IMAGE" 2>/dev/null || true)"
if [[ -z "$DIGEST" || "$DIGEST" == "<none>" ]]; then
  DIGEST="$(docker image inspect --format='{{.Id}}' "$RUNTIME_IMAGE")"
fi
echo "container_image=$RUNTIME_IMAGE digest_or_id=$DIGEST"
echo "STATUS=PASS gate=oci_arm64_build_runtime"
