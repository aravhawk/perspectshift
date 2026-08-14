#!/usr/bin/env bash
# Canonical verification orchestrator — emits machine-readable evidence.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

TIER="host_software"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --tier) TIER="$2"; shift 2 ;;
    -h|--help)
      cat <<'EOF'
Usage: verify-all.sh --tier <tier>

Tiers:
  host_software
  ubuntu_clean_room
  ros_jazzy
  package_install
  container_runtime
  native_arm64
  external_model_certification
EOF
      exit 0
      ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

OUT_DIR="$ROOT/build/verification"
LOG_DIR="$OUT_DIR/logs"
mkdir -p "$LOG_DIR"
GATES_JSONL="$LOG_DIR/gates.jsonl"
: > "$GATES_JSONL"

START_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
HOST_ARCH="$(uname -m)"
HOST_OS="$(uname -s)"
if git rev-parse HEAD >/dev/null 2>&1; then
  GIT_STATE="$(git rev-parse HEAD)"
else
  GIT_STATE="no-commits"
fi

record_gate() {
  local name="$1" status="$2" required="$3" command="$4" exit_code="$5" duration="$6" log_path="$7" skip_reason="${8:-}"
  python3 - "$name" "$status" "$required" "$command" "$exit_code" "$duration" "$log_path" "$skip_reason" >>"$GATES_JSONL" <<'PY'
import json, sys
name, status, required, command, exit_code, duration, log_path, skip_reason = sys.argv[1:]
json.dump({
  "name": name,
  "status": status,
  "required": required == "true",
  "command": command,
  "exit_code": int(exit_code),
  "duration_seconds": float(duration),
  "log_path": log_path or None,
  "skip_reason": skip_reason or None,
}, sys.stdout)
sys.stdout.write("\n")
PY
  echo "[$status] $name (exit=$exit_code, ${duration}s)${skip_reason:+ — $skip_reason}"
}

run_gate() {
  local name="$1" required="$2" command="$3"
  local log="$LOG_DIR/${name}.log"
  local start end dur rc status
  start=$(date +%s)
  set +e
  bash -lc "$command" >"$log" 2>&1
  rc=$?
  set -e
  end=$(date +%s)
  dur=$((end - start))
  if [[ $rc -eq 0 ]]; then status=PASS; else status=FAIL; fi
  record_gate "$name" "$status" "$required" "$command" "$rc" "$dur" "$log" ""
}

skip_gate() {
  local name="$1" required="$2" command="$3" reason="$4"
  record_gate "$name" "SKIP" "$required" "$command" 0 0 "" "$reason"
}

echo "verify-all tier=$TIER host=$HOST_OS/$HOST_ARCH"
export PERCEPTSHIFT_ORT_ROOT="${PERCEPTSHIFT_ORT_ROOT:-$ROOT/.cache/onnxruntime}"
export DYLD_LIBRARY_PATH="$PERCEPTSHIFT_ORT_ROOT/lib:${DYLD_LIBRARY_PATH:-}"
export LD_LIBRARY_PATH="$PERCEPTSHIFT_ORT_ROOT/lib:${LD_LIBRARY_PATH:-}"

case "$TIER" in
  host_software)
    run_gate repository_policy true "./scripts/verify-repository.sh"
    if [[ -d build/default ]]; then PRESET=default
    elif [[ "$HOST_ARCH" == "arm64" || "$HOST_ARCH" == "aarch64" ]]; then PRESET=dev-arm64
    else PRESET=dev-x64; fi
    run_gate cmake_ort_build true "cmake --preset $PRESET && cmake --build --preset $PRESET -j"
    run_gate native_tests true "ctest --test-dir build/$PRESET --output-on-failure"
    if command -v uv >/dev/null; then
      run_gate python_tests true "uv sync --all-packages && uv run pytest python -q"
    else
      skip_gate python_tests true "uv run pytest python -q" "uv missing"
    fi
    if command -v pnpm >/dev/null; then
      run_gate web_unit true "cd web && pnpm install && pnpm test && pnpm build"
    else
      skip_gate web_unit true "cd web && pnpm test" "pnpm missing"
    fi
    run_gate docs_check true "make docs-check"
    run_gate e2e_native true "./scripts/run-e2e.sh --native-only"
    ;;
  ubuntu_clean_room)
    run_gate clean_room true "./scripts/clean-room-verify.sh"
    ;;
  ros_jazzy)
    if command -v ros2 >/dev/null; then
      run_gate ros_build_test true "bash -lc 'source /opt/ros/jazzy/setup.bash && cd ros2_ws && colcon build --symlink-install && colcon test --event-handlers console_direct+ && colcon test-result --verbose'"
    else
      skip_gate ros_build_test true "colcon test" "ROS 2 Jazzy not installed; on Ubuntu 24.04: source /opt/ros/jazzy/setup.bash && ./scripts/verify-all.sh --tier ros_jazzy"
    fi
    ;;
  package_install)
    if [[ "$HOST_OS" == "Linux" ]]; then
      run_gate package_deb true "./scripts/package-deb.sh"
    else
      skip_gate package_deb true "./scripts/package-deb.sh" "Debian packaging requires Linux; on Ubuntu: ./scripts/package-deb.sh"
    fi
    ;;
  container_runtime)
    if command -v docker >/dev/null; then
      run_gate docker_build true "docker build -f deploy/containers/Dockerfile.runtime -t perceptshift-runtime:local ."
    else
      skip_gate docker_build true "docker build ..." "docker not installed"
    fi
    ;;
  native_arm64)
    run_gate arm_acceptance true "./scripts/run-arm-acceptance.sh"
    ;;
  external_model_certification)
    skip_gate external_model true "perceptshift forge run --config USER_CONFIG.yaml" "Requires user-supplied ONNX model, calibration, and evaluation data. Example: perceptshift forge run --config /abs/path/forge.yaml"
    ;;
  *)
    echo "Unknown tier: $TIER" >&2
    exit 2
    ;;
esac

END_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

python3 - <<PY
import json, platform
from pathlib import Path

root = Path("$ROOT")
out_dir = root / "build" / "verification"
gates = []
for line in (out_dir / "logs" / "gates.jsonl").read_text(encoding="utf-8").splitlines():
    if line.strip():
        gates.append(json.loads(line))
required = [g for g in gates if g.get("required")]
has_skip = any(g.get("status") == "SKIP" for g in required)
tier_pass = all(g.get("status") == "PASS" for g in required) if required else False
if has_skip:
    tier_status = "INCOMPLETE"
elif tier_pass:
    tier_status = "PASS"
else:
    tier_status = "FAIL"
doc = {
  "schema_version": "verification-v1",
  "product_version": Path("VERSION").read_text(encoding="utf-8").strip(),
  "git": {"state": "$GIT_STATE"},
  "host_fingerprint": {"os": "$HOST_OS", "arch": "$HOST_ARCH", "platform": platform.platform()},
  "start_utc": "$START_UTC",
  "end_utc": "$END_UTC",
  "requested_tier": "$TIER",
  "gates": gates,
  "acceptance_tiers": {
    "$TIER": {
      "status": tier_status,
      "required_gates": [g["name"] for g in required],
      "passed": tier_pass and not has_skip,
    }
  },
}
(out_dir / "verification.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
tiers_dir = out_dir / "tiers"
tiers_dir.mkdir(parents=True, exist_ok=True)
tier_path = tiers_dir / f"{doc['requested_tier']}.json"
tier_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

# Aggregate durable final verification from all tier files.
aggregate = {
  "schema_version": "final-verification-v1",
  "product_version": doc["product_version"],
  "git": doc["git"],
  "host_fingerprint": doc["host_fingerprint"],
  "tiers": {},
  "required_software_pass": True,
}
for path in sorted(tiers_dir.glob("*.json")):
    tier_doc = json.loads(path.read_text(encoding="utf-8"))
    tname = tier_doc.get("requested_tier") or path.stem
    tstatus = tier_doc.get("acceptance_tiers", {}).get(tname, {}).get("status", "FAIL")
    aggregate["tiers"][tname] = {
        "status": tstatus,
        "path": str(path.relative_to(out_dir)),
        "end_utc": tier_doc.get("end_utc"),
    }
    if tname not in {
        "external_model_certification",
        "physical_arm_performance_certification",
    }:
        if tstatus != "PASS":
            aggregate["required_software_pass"] = False
# External tiers default to NOT_RUN when absent.
for ext in ("external_model_certification", "physical_arm_performance_certification"):
    aggregate["tiers"].setdefault(
        ext,
        {"status": "NOT_RUN_EXTERNAL_INPUT_REQUIRED", "path": None, "end_utc": None},
    )
aggregate["overall_status"] = "PASS" if aggregate["required_software_pass"] else "FAIL"
(out_dir / "final-verification.json").write_text(json.dumps(aggregate, indent=2) + "\n", encoding="utf-8")
(out_dir / "final-verification.md").write_text(
    "# Final verification\n\n"
    + f"- Overall: **{aggregate['overall_status']}**\n"
    + "\n".join(f"- `{name}`: `{info['status']}`" for name, info in aggregate["tiers"].items())
    + "\n",
    encoding="utf-8",
)
md = [
  "# Verification report", "",
  f"- Tier: \`{doc['requested_tier']}\`",
  f"- Status: **{tier_status}**",
  f"- Host: \`{doc['host_fingerprint']['platform']}\`",
  f"- Git: \`{doc['git']['state']}\`",
  f"- Start: \`{doc['start_utc']}\`",
  f"- End: \`{doc['end_utc']}\`",
  "",
  "| Gate | Status | Required | Exit | Duration |",
  "|---|---|---|---|---|",
]
for g in gates:
    md.append(f"| {g['name']} | {g['status']} | {g['required']} | {g['exit_code']} | {g['duration_seconds']}s |")
    if g.get("skip_reason"):
        md.append(f"| | skip_reason | {g['skip_reason']} | | |")
(out_dir / "verification.md").write_text("\n".join(md) + "\n", encoding="utf-8")
(out_dir / "artifacts.json").write_text(json.dumps({
  "verification_json": str(out_dir / "verification.json"),
  "verification_md": str(out_dir / "verification.md"),
}, indent=2) + "\n", encoding="utf-8")
print(f"Wrote {out_dir / 'verification.md'} status={tier_status}")
raise SystemExit(0 if tier_status == "PASS" else 1)
PY
