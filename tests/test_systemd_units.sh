#!/usr/bin/env bash
# Validate systemd unit ExecStart command lines without requiring PID 1.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

fail=0
check_unit() {
  local unit="$1"
  echo "-- $unit"
  if [[ ! -f "$unit" ]]; then
    echo "MISSING $unit"
    fail=1
    return
  fi
  local exec
  exec="$(awk -F= '/^ExecStart=/{print $2; exit}' "$unit")"
  if [[ -z "$exec" ]]; then
    echo "FAIL: no ExecStart in $unit"
    fail=1
    return
  fi
  echo "ExecStart=$exec"
  if grep -Eq -- '--bind |--mode ' <<<"$exec"; then
    echo "FAIL: unsupported API options in ExecStart: $exec"
    fail=1
  fi
  if grep -Eq -- 'perceptshift-runtime --config' <<<"$exec"; then
    echo "FAIL: native runtime CLI does not support --config in this form: $exec"
    fail=1
  fi
}

check_unit deploy/systemd/perceptshift-api.service
check_unit deploy/systemd/perceptshift-runtime.service

if ! grep -q 'ExecStart=/usr/lib/perceptshift/bin/perceptshift-api-service' deploy/systemd/perceptshift-api.service; then
  echo "FAIL: API unit must start the packaged service wrapper"
  fail=1
fi
if grep -q 'LoadCredential' deploy/systemd/perceptshift-runtime.service; then
  echo "FAIL: runtime unit must not load unused API token credential"
  fail=1
fi
if ! grep -q 'LoadCredential=perceptshift-api-token:' deploy/systemd/perceptshift-api.service; then
  echo "FAIL: API unit must LoadCredential the plaintext api-token"
  fail=1
fi
if grep -q 'LoadCredentialEncrypted' deploy/systemd/perceptshift-api.service; then
  echo "FAIL: API unit uses LoadCredentialEncrypted but documents a plaintext token file"
  fail=1
fi

if [[ ! -x deploy/systemd/perceptshift-ros-runtime ]]; then
  echo "FAIL: perceptshift-ros-runtime wrapper missing or not executable"
  fail=1
else
  echo "OK: perceptshift-ros-runtime wrapper present"
fi
if [[ ! -x deploy/systemd/perceptshift-api-service ]]; then
  echo "FAIL: perceptshift-api-service wrapper missing or not executable"
  fail=1
else
  echo "OK: perceptshift-api-service wrapper present"
fi

if ! grep -q '^StartLimitIntervalSec=' deploy/systemd/perceptshift-runtime.service; then
  echo "FAIL: StartLimitIntervalSec missing from runtime unit"
  fail=1
elif awk '
  /^\[/{sect=$0}
  /^StartLimitIntervalSec=/ {
    if (sect != "[Unit]") { print "FAIL: StartLimitIntervalSec must be in [Unit]"; exit 1 }
  }
' deploy/systemd/perceptshift-runtime.service; then
  echo "OK: StartLimitIntervalSec is in [Unit]"
else
  fail=1
fi

for wrapper in deploy/systemd/perceptshift-ros-runtime deploy/systemd/perceptshift-api-service; do
  if ! grep -q 'FASTDDS_BUILTIN_TRANSPORTS' "$wrapper"; then
    echo "FAIL: $wrapper must default Fast DDS to UDPv4 for cross-user ROS"
    fail=1
  else
    echo "OK: $wrapper sets FASTDDS_BUILTIN_TRANSPORTS"
  fi
  if ! grep -q 'rmw_cyclonedds_cpp' "$wrapper"; then
    echo "FAIL: $wrapper must default RMW to Cyclone DDS for cross-user ROS"
    fail=1
  else
    echo "OK: $wrapper sets RMW_IMPLEMENTATION"
  fi
done

if command -v systemd-analyze >/dev/null 2>&1; then
  systemd-analyze verify deploy/systemd/perceptshift-api.service deploy/systemd/perceptshift-runtime.service \
    || fail=1
else
  echo "WARN: systemd-analyze unavailable on this host; Debian acceptance requires it"
fi

if [[ "$fail" -ne 0 ]]; then
  echo "systemd unit validation FAILED"
  exit 1
fi
echo "systemd unit validation PASSED"
