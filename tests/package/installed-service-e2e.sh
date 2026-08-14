#!/usr/bin/env bash
# Installed Debian product E2E: service-user API + ROS runtime + credentials.
# Intended to run inside the package-acceptance installer container.
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
set +u; source /opt/ros/jazzy/setup.bash; set -u
apt-get update -qq
apt-get install -y -qq dpkg file curl ca-certificates systemd python3-setuptools \
  ros-jazzy-rclcpp-lifecycle ros-jazzy-sensor-msgs ros-jazzy-launch-ros \
  ros-jazzy-lifecycle-msgs ros-jazzy-rclpy ros-jazzy-diagnostic-updater \
  ros-jazzy-rmw-cyclonedds-cpp \
  python3 adduser passwd util-linux >/dev/null

DEB="/dist/${DEB_BASE}"
test -s "$DEB"
ACTUAL_SHA="$(sha256sum "$DEB" | awk '{print $1}')"
[[ "$ACTUAL_SHA" == "$DEB_SHA" ]] || { echo "sha mismatch"; exit 1; }
file "$DEB" | grep -qi "debian\|archive"
dpkg-deb -f "$DEB" Architecture | grep -qx arm64

dpkg -i "$DEB" || apt-get install -y -f -qq
dpkg -i "$DEB"

test -x /usr/bin/perceptshift
perceptshift --help >/tmp/cli-help.txt
perceptshift --json version | tee /tmp/cli-json-version.txt
python3 -c 'import json; json.load(open("/tmp/cli-json-version.txt"))'

test -x /usr/bin/perceptshift-api
test -x /usr/lib/perceptshift/bin/perceptshift-api-service
python3 -c 'import perceptshift_api, inspect; p=inspect.getfile(perceptshift_api); assert "/src" not in p and ".venv" not in p and "/work" not in p, p'

getent passwd perceptshift
getent passwd perceptshift-api
getent group perceptshift
id -nG perceptshift-api | grep -qw perceptshift

test -d /var/lib/perceptshift/api
test -d /var/lib/perceptshift/api/state
test -d /var/lib/perceptshift/api/data
test -d /var/log/perceptshift/api
owner_mode() { stat -c '%U %G %a' "$1"; }
[[ "$(owner_mode /var/lib/perceptshift)" == "root perceptshift 750" ]]
[[ "$(owner_mode /var/lib/perceptshift/api)" == "perceptshift-api perceptshift 750" ]]
[[ "$(owner_mode /var/lib/perceptshift/api/state)" == "perceptshift-api perceptshift 750" ]]
[[ "$(owner_mode /var/log/perceptshift/api)" == "perceptshift-api perceptshift 750" ]]
[[ "$(owner_mode /var/lib/perceptshift/runtime)" == "perceptshift perceptshift 750" ]]

test -f /usr/lib/systemd/system/perceptshift-runtime.service
test -f /usr/lib/systemd/system/perceptshift-api.service
test -x /usr/lib/perceptshift/bin/perceptshift-ros-runtime
grep -q 'ExecStart=/usr/lib/perceptshift/bin/perceptshift-api-service' /usr/lib/systemd/system/perceptshift-api.service
if grep -q 'LoadCredential' /usr/lib/systemd/system/perceptshift-runtime.service; then
  echo "runtime unit must not load unused API token credential" >&2
  exit 1
fi

install -d -m 0700 /etc/perceptshift/credentials
printf '%s' 'pkg-accept-token' >/etc/perceptshift/credentials/api-token
chmod 0600 /etc/perceptshift/credentials/api-token

command -v systemd-analyze >/dev/null
systemd-analyze verify \
  /usr/lib/systemd/system/perceptshift-runtime.service \
  /usr/lib/systemd/system/perceptshift-api.service

set +u; source /opt/ros/jazzy/setup.bash
source /usr/share/perceptshift/ros/setup.bash
set -u
ros2 pkg prefix perceptshift_msgs
ros2 pkg prefix perceptshift_ros
test -f /usr/share/perceptshift/ros/setup.bash

if ! compgen -G '/usr/lib/perceptshift/libonnxruntime.so*' >/dev/null; then
  echo "packaged libonnxruntime missing" >&2
  exit 1
fi

python3 - <<'PY'
from pathlib import Path
import sys
sys.path.insert(0, "/tests/e2e")
from bundle_fixture import write_classification_bundle
write_classification_bundle(Path("/var/lib/perceptshift/bundle"))
print("bundle_ok")
PY
chown -R perceptshift:perceptshift /var/lib/perceptshift/bundle

if grep -F '.venv/' /usr/bin/perceptshift /usr/bin/perceptshift-api /usr/lib/perceptshift/bin/perceptshift-api-service >/dev/null 2>&1; then
  echo "wrappers reference .venv paths" >&2
  exit 1
fi

export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
export FASTDDS_BUILTIN_TRANSPORTS=UDPv4

install -d -m 0750 -o root -g perceptshift /run/perceptshift
install -d -m 0770 -o perceptshift -g perceptshift /run/perceptshift/dds

ros_user_env=(
  HOME=/var/lib/perceptshift/runtime
  USER=perceptshift
  LOGNAME=perceptshift
  PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
  ROS_HOME=/var/lib/perceptshift/ros
  XDG_RUNTIME_DIR=/run/perceptshift/dds
  ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
  FASTDDS_BUILTIN_TRANSPORTS=UDPv4
  RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
  LANG=C.UTF-8
)

runuser -u perceptshift -- env -i "${ros_user_env[@]}" \
  /usr/lib/perceptshift/bin/perceptshift-ros-runtime \
    --bundle /var/lib/perceptshift/bundle \
    --task image_classification \
    deadline_ms:=500.0 maximum_source_age_ms:=5000.0 telemetry_period_ms:=200 \
  >/tmp/ros-runtime.log 2>&1 &
ROS_WRAP_PID=$!
sleep 8
if ! kill -0 "$ROS_WRAP_PID" 2>/dev/null; then
  echo "ros runtime wrapper exited early" >&2
  tail -200 /tmp/ros-runtime.log >&2
  exit 1
fi

# Same Unix user as the runtime node (avoids Fast DDS SHM/UID isolation).
runuser -u perceptshift -- env -i "${ros_user_env[@]}" \
  bash -c 'set +u; source /opt/ros/jazzy/setup.bash; source /usr/share/perceptshift/ros/setup.bash; set -u; python3 /tests/package/installed_ros_infer.py'

CRED_DIR=/run/credentials/perceptshift-api.service
mkdir -p "$CRED_DIR"
printf '%s' 'pkg-accept-token' >"$CRED_DIR/perceptshift-api-token"
chown perceptshift-api:perceptshift "$CRED_DIR/perceptshift-api-token"
chmod 0400 "$CRED_DIR/perceptshift-api-token"

runuser -u perceptshift-api -- env -i \
  HOME=/var/lib/perceptshift/api \
  USER=perceptshift-api \
  LOGNAME=perceptshift-api \
  PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
  XDG_STATE_HOME=/var/lib/perceptshift/api/state \
  XDG_DATA_HOME=/var/lib/perceptshift/api/data \
  PERCEPTSHIFT_API_STATE_DIR=/var/lib/perceptshift/api/state \
  PERCEPTSHIFT_API_DATA_DIR=/var/lib/perceptshift/api/data \
  PERCEPTSHIFT_API_ROS_SERVICE_TIMEOUT_S=20 \
  XDG_RUNTIME_DIR=/run/perceptshift/dds \
  CREDENTIALS_DIRECTORY="$CRED_DIR" \
  ROS_HOME=/var/lib/perceptshift/api/ros \
  ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST \
  FASTDDS_BUILTIN_TRANSPORTS=UDPv4 \
  RMW_IMPLEMENTATION=rmw_cyclonedds_cpp \
  LANG=C.UTF-8 \
  /usr/lib/perceptshift/bin/perceptshift-api-service --host 127.0.0.1 --port 8080 \
  >/tmp/api-service.log 2>&1 &
API_PID=$!
ok=0
for _ in $(seq 1 80); do
  if curl -fsS http://127.0.0.1:8080/api/v1/healthz >/tmp/healthz.json 2>/dev/null; then
    ok=1
    break
  fi
  if ! kill -0 "$API_PID" 2>/dev/null; then
    echo "API service died"; tail -200 /tmp/api-service.log; exit 1
  fi
  sleep 0.5
done
[[ "$ok" == "1" ]] || { echo "API health failed"; tail -200 /tmp/api-service.log; exit 1; }

python3 - <<'PY'
import json, os, time, urllib.error, urllib.request
from pathlib import Path

def get(path):
    with urllib.request.urlopen("http://127.0.0.1:8080" + path, timeout=5) as resp:
        return json.loads(resp.read())

health = get("/api/v1/healthz")
assert health.get("status") == "ok", health
ready = get("/api/v1/readyz")
assert ready.get("ready") is True, ready

deadline = time.time() + 45
status = None
while time.time() < deadline:
    status = get("/api/v1/runtime/status")
    if status.get("connected") is True:
        break
    time.sleep(0.5)
assert status and status.get("connected") is True, status
assert status.get("mode") == "ros", status

db_hits = list(Path("/var/lib/perceptshift/api").rglob("*.sqlite"))
assert db_hits, "API did not create sqlite under API-owned path"
for p in db_hits:
    text = str(p)
    assert "/src" not in text and ".venv" not in text and "/work" not in text, text
print("api_db_paths", [str(p) for p in db_hits])

# Unauthenticated mutation rejected.
req = urllib.request.Request(
    "http://127.0.0.1:8080/api/v1/runtime/policy",
    data=json.dumps({"deadline_ms": 42.0}).encode(),
    method="PATCH",
    headers={"Content-Type": "application/json"},
)
try:
    urllib.request.urlopen(req, timeout=5)
    raise SystemExit("unauthenticated mutation unexpectedly succeeded")
except urllib.error.HTTPError as exc:
    assert exc.code in {401, 403}, exc.code
    body = json.loads(exc.read())
    assert body["error"]["code"] in {"AUTH_REQUIRED", "MUTATIONS_DISABLED", "AUTH_INVALID"}, body

# Authenticated mutation.
req = urllib.request.Request(
    "http://127.0.0.1:8080/api/v1/runtime/policy",
    data=json.dumps({"deadline_ms": 42.0}).encode(),
    method="PATCH",
    headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer pkg-accept-token",
    },
)
with urllib.request.urlopen(req, timeout=30) as resp:
    patched = json.loads(resp.read())
assert patched.get("deadline_ms") == 42.0, patched
readback = get("/api/v1/runtime/policy")
assert readback.get("deadline_ms") == 42.0, readback
recent = get("/api/v1/telemetry/recent?limit=20")
print("telemetry_recent_ok", type(recent).__name__)
print("service_user_api_ros_ok")
PY

kill "$API_PID" 2>/dev/null || true
wait "$API_PID" 2>/dev/null || true
kill "$ROS_WRAP_PID" 2>/dev/null || true
wait "$ROS_WRAP_PID" 2>/dev/null || true

if [[ -e /usr/lib/perceptshift/bin/perceptshift-api-service ]]; then
  if grep -E '^[^#]*(\.venv/|/src/|/work/)' /usr/lib/perceptshift/bin/perceptshift-api-service; then
    echo "API wrapper references checkout paths" >&2
    exit 1
  fi
fi

dpkg --purge perceptshift
hash -r || true
if [[ -e /usr/bin/perceptshift ]] || [[ -e /usr/bin/perceptshift-api ]] || [[ -e /usr/lib/perceptshift/bin/perceptshift-api-service ]]; then
  echo "package-owned executables remain after purge" >&2
  exit 1
fi
if [[ -e /usr/lib/perceptshift/bin/perceptshift-ros-runtime ]]; then
  echo "ros runtime wrapper remains after purge" >&2
  exit 1
fi

cat > /evidence/acceptance-summary.json <<JSON
{
  "status": "PASS",
  "deb": "$DEB_BASE",
  "sha256": "$DEB_SHA",
  "arch": "arm64",
  "checks": [
    "deb_generated", "arch_arm64", "sha256", "install",
    "cli_help", "cli_json", "service_accounts", "api_writable_dirs",
    "api_wrapper", "systemd_analyze_verify", "execstart_targets",
    "runtime_as_perceptshift", "api_as_perceptshift-api",
    "sqlite_under_api_state", "credential_token",
    "unauthenticated_mutation_rejected", "authenticated_policy_readback",
    "ros_connected", "ros_fixture_inference", "no_src_checkout", "purge"
  ]
}
JSON
echo "debian acceptance OK"
