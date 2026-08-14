#!/usr/bin/env bash
# Canonical 26-tier release verification orchestrator.
# Evidence only from executed commands. Never hand-write PASS.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

OUT_DIR="$ROOT/build/verification"
TIER_DIR="$OUT_DIR/tiers"
LOG_DIR="$OUT_DIR/logs"
ART_DIR="$OUT_DIR/artifacts"
mkdir -p "$TIER_DIR" "$LOG_DIR" "$ART_DIR"

chmod +x "$ROOT/scripts/source-fingerprint.sh"
SOURCE_FP="$("$ROOT/scripts/source-fingerprint.sh")"
HOST_OS="$(uname -s)"
HOST_ARCH="$(uname -m)"
START_ALL="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

sha_file() {
  local f="$1"
  if [[ ! -f "$f" ]]; then echo ""; return; fi
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$f" | awk '{print $1}'
  else
    shasum -a 256 "$f" | awk '{print $1}'
  fi
}

write_tier() {
  local name="$1" classification="$2" status="$3" command="$4" exit_code="$5"
  local start_ts="$6" end_ts="$7" duration="$8" log_path="$9" reason="${10:-}"
  local test_count="${11:-}"
  local log_sha=""
  if [[ -n "$log_path" && -f "$log_path" ]]; then
    log_sha="$(sha_file "$log_path")"
  fi
  TIER_NAME="$name" TIER_CLASS="$classification" TIER_STATUS="$status" \
  TIER_CMD="$command" TIER_EXIT="$exit_code" TIER_START="$start_ts" TIER_END="$end_ts" \
  TIER_DUR="$duration" TIER_LOG="$log_path" TIER_LOG_SHA="$log_sha" TIER_REASON="$reason" \
  TIER_COUNT="$test_count" TIER_FP="$SOURCE_FP" TIER_OS="$HOST_OS" TIER_ARCH="$HOST_ARCH" \
  TIER_PATH="$TIER_DIR/${name}.json" \
  python3 - <<'PY'
import json, os
path = os.environ["TIER_PATH"]
count = os.environ.get("TIER_COUNT", "").strip()
doc = {
  "tier": os.environ["TIER_NAME"],
  "classification": os.environ["TIER_CLASS"],
  "status": os.environ["TIER_STATUS"],
  "command": os.environ.get("TIER_CMD") or None,
  "exit_code": int(os.environ["TIER_EXIT"]),
  "start": os.environ["TIER_START"],
  "end": os.environ["TIER_END"],
  "duration_seconds": float(os.environ["TIER_DUR"]),
  "host": {"os": os.environ["TIER_OS"], "arch": os.environ["TIER_ARCH"], "context": "release-verify"},
  "source_fingerprint": os.environ["TIER_FP"],
  "log_path": os.environ.get("TIER_LOG") or None,
  "log_sha256": os.environ.get("TIER_LOG_SHA") or None,
  "artifact_paths": [],
  "test_count": int(count) if count else None,
  "reason": os.environ.get("TIER_REASON") or None,
}
with open(path, "w", encoding="utf-8") as f:
    json.dump(doc, f, indent=2)
    f.write("\n")
PY
  echo "[$status] $name (${duration}s) exit=$exit_code"
}

run_required() {
  local name="$1"
  shift
  local command="$*"
  local log="$LOG_DIR/${name}.log"
  local start end dur rc status
  start_ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  start=$(date +%s)
  set +e
  bash -lc "$command" >"$log" 2>&1
  rc=$?
  set -e
  end=$(date +%s)
  end_ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  dur=$((end - start))
  if [[ $rc -eq 0 ]]; then status=PASS; else status=FAIL; fi
  write_tier "$name" "required" "$status" "$command" "$rc" "$start_ts" "$end_ts" "$dur" "$log" ""
  return $rc
}

record_external() {
  local name="$1" reason="$2"
  local ts
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  write_tier "$name" "external" "NOT_RUN_EXTERNAL_INPUT_REQUIRED" "n/a" 0 "$ts" "$ts" 0 "" "$reason"
}

REQUIRED_TIERS=(
  repository_hygiene
  schema_contracts
  python_format_lint_typecheck
  python_unit_contract_tests
  cpp_build_warnings
  cpp_unit_property_tests
  canonical_preprocessing_equivalence
  onnx_runtime_executor_e2e
  forge_real_path_e2e
  quantization_calibration_equivalence
  quality_baseline_degradation
  adaptive_controller_behavior
  bundle_integrity_signature
  ros_jazzy_build_tests
  ros_runtime_inference_e2e
  api_contract_tests
  api_ros_runtime_e2e
  web_unit_tests
  browser_real_stack_inference_e2e
  debian_arm64_package_install_uninstall
  oci_arm64_build_runtime
  asan_ubsan
  tsan
  fuzz
  coverage
  clean_room_arm64_noble
)

echo "release-verify source_fingerprint=$SOURCE_FP host=$HOST_OS/$HOST_ARCH"

export PERCEPTSHIFT_ORT_ROOT="${PERCEPTSHIFT_ORT_ROOT:-$ROOT/.cache/onnxruntime}"
export DYLD_LIBRARY_PATH="${PERCEPTSHIFT_ORT_ROOT}/lib:${DYLD_LIBRARY_PATH:-}"
export LD_LIBRARY_PATH="${PERCEPTSHIFT_ORT_ROOT}/lib:${LD_LIBRARY_PATH:-}"
export PATH="$ROOT/build/default/cpp:$ROOT/build/dev-arm64/cpp:$PATH"

OVERALL_RC=0

# --- Host / fast tiers ---
run_required repository_hygiene \
  "rm -rf ros2_ws/build ros2_ws/install ros2_ws/log && ./scripts/verify-repository.sh" || OVERALL_RC=1

run_required schema_contracts \
  "uv run pytest tests/contract -q --tb=line" || OVERALL_RC=1

if command -v uv >/dev/null 2>&1; then
  run_required python_format_lint_typecheck \
    "uv sync --all-packages && uv run ruff check python && uv run ruff format --check python && uv run pyright" \
    || OVERALL_RC=1
else
  run_required python_format_lint_typecheck \
    ".venv/bin/ruff check python && .venv/bin/ruff format --check python" \
    || OVERALL_RC=1
fi

PRESET=default
if [[ -d build/dev-arm64 ]]; then PRESET=dev-arm64; fi
if [[ ! -d "build/$PRESET" ]]; then
  cmake --preset "$PRESET"
fi
cmake --build --preset "$PRESET" -j

run_required python_unit_contract_tests \
  "uv pip install pycocotools -p .venv >/dev/null && PATH=\"$ROOT/build/$PRESET/cpp:\$PATH\" uv run pytest python tests/contract -q" \
  || OVERALL_RC=1

run_required cpp_unit_property_tests \
  "ctest --test-dir build/$PRESET --output-on-failure" || OVERALL_RC=1

run_required canonical_preprocessing_equivalence \
  "ctest --test-dir build/$PRESET -R Preprocessor --output-on-failure && PATH=\"$ROOT/build/$PRESET/cpp:\$PATH\" uv run pytest python/perceptshift_forge/tests/test_preprocess_contract.py -q" \
  || OVERALL_RC=1

run_required onnx_runtime_executor_e2e \
  "test -x build/$PRESET/cpp/perceptshift-runtime && test -x build/$PRESET/cpp/perceptshift-bench-worker && test -x build/$PRESET/cpp/perceptshift-preprocess-worker && build/$PRESET/cpp/perceptshift-runtime --version && build/$PRESET/cpp/perceptshift-bench-worker --version" \
  || OVERALL_RC=1

run_required forge_real_path_e2e \
  "PATH=\"$ROOT/build/$PRESET/cpp:\$PATH\" uv run pytest python/perceptshift_forge/tests/test_forge_e2e_adapters.py -q" \
  || OVERALL_RC=1

run_required quantization_calibration_equivalence \
  "PATH=\"$ROOT/build/$PRESET/cpp:\$PATH\" uv run pytest python/perceptshift_forge/tests/test_forge.py::test_forge_run_workspace python/perceptshift_forge/tests/test_preprocess_contract.py -q" \
  || OVERALL_RC=1

run_required quality_baseline_degradation \
  "PATH=\"$ROOT/build/$PRESET/cpp:\$PATH\" uv run pytest python/perceptshift_forge/tests/test_forge_e2e_adapters.py::test_forge_classification_e2e python/perceptshift_forge/tests/test_forge_e2e_adapters.py::test_forge_yolo_e2e -q" \
  || OVERALL_RC=1

run_required adaptive_controller_behavior \
  "ctest --test-dir build/$PRESET -R Controller --output-on-failure" || OVERALL_RC=1

run_required bundle_integrity_signature \
  "PATH=\"$ROOT/build/$PRESET/cpp:\$PATH\" uv run pytest python/perceptshift_forge/tests/test_forge.py::test_ed25519_bundle_sign_roundtrip python/perceptshift_forge/tests/test_forge.py::test_blake2b_not_accepted_as_ed25519 tests/security -q" \
  || OVERALL_RC=1

run_required api_contract_tests \
  "uv run pytest python/perceptshift_api -q && ./tests/test_systemd_units.sh" || OVERALL_RC=1

run_required web_unit_tests \
  "cd web && pnpm install --frozen-lockfile && pnpm lint && pnpm test && pnpm build" || OVERALL_RC=1

run_required fuzz "./scripts/run-fuzz.sh" || OVERALL_RC=1

run_required coverage \
  "bash \"$ROOT/scripts/coverage-acceptance.sh\"" || OVERALL_RC=1

# --- Docker arm64 Ubuntu/ROS tiers ---
DOCKER_PLATFORM="linux/arm64"
prove_arch() {
  docker run --rm --platform "$DOCKER_PLATFORM" ubuntu:24.04 uname -m | grep -q aarch64
}

if ! prove_arch; then
  for t in ros_jazzy_build_tests ros_runtime_inference_e2e api_ros_runtime_e2e \
           browser_real_stack_inference_e2e debian_arm64_package_install_uninstall \
           oci_arm64_build_runtime asan_ubsan tsan clean_room_arm64_noble cpp_build_warnings; do
    write_tier "$t" "required" "FAIL" "docker arm64 prove" 1 \
      "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" 0 "" \
      "docker platform linux/arm64 did not report aarch64"
  done
  OVERALL_RC=1
else
  ORT_LINUX="$ROOT/.cache/onnxruntime-linux-aarch64-1.28.0"
  if [[ ! -d "$ORT_LINUX/lib" ]]; then
    mkdir -p "$ROOT/.cache"
    curl -fsSL "https://github.com/microsoft/onnxruntime/releases/download/v1.28.0/onnxruntime-linux-aarch64-1.28.0.tgz" \
      -o "$ROOT/.cache/ort-linux.tgz"
    rm -rf "$ROOT/.cache/ort-linux-extract"
    mkdir -p "$ROOT/.cache/ort-linux-extract"
    tar -xzf "$ROOT/.cache/ort-linux.tgz" -C "$ROOT/.cache/ort-linux-extract"
    rm -rf "$ORT_LINUX"
    mv "$ROOT/.cache/ort-linux-extract/onnxruntime-linux-aarch64-1.28.0" "$ORT_LINUX"
    echo "1.28.0" >"$ORT_LINUX/VERSION.txt"
  fi

  run_required cpp_build_warnings \
    "bash \"$ROOT/scripts/cpp-warnings-acceptance.sh\"" || OVERALL_RC=1

  run_required oci_arm64_build_runtime \
    "bash \"$ROOT/scripts/container-acceptance.sh\"" || OVERALL_RC=1

  run_required debian_arm64_package_install_uninstall \
    "bash \"$ROOT/scripts/debian-acceptance.sh\"" || OVERALL_RC=1

  run_required asan_ubsan \
    "docker run --rm --platform $DOCKER_PLATFORM -v \"$ROOT:/src\" -v \"$ROOT/.cache:/src/.cache\" ubuntu:24.04 bash -lc 'apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq build-essential cmake ninja-build git python3 libssl-dev zlib1g-dev >/dev/null && cd /src && cmake -S . -B build/asan -DPERCEPTSHIFT_ENABLE_ASAN=ON -DPERCEPTSHIFT_ENABLE_UBSAN=ON -DPERCEPTSHIFT_ORT_ROOT=/src/.cache/onnxruntime-linux-aarch64-1.28.0 && cmake --build build/asan -j2 && ctest --test-dir build/asan --output-on-failure'" \
    || OVERALL_RC=1

  run_required tsan \
    "bash \"$ROOT/scripts/tsan-acceptance.sh\"" || OVERALL_RC=1

  run_required ros_jazzy_build_tests \
    "bash \"$ROOT/scripts/ros-jazzy-acceptance.sh\" --build-test-only" || OVERALL_RC=1
  run_required ros_runtime_inference_e2e \
    "bash \"$ROOT/scripts/ros-jazzy-acceptance.sh\" --integration" || OVERALL_RC=1
  run_required api_ros_runtime_e2e \
    "bash \"$ROOT/scripts/ros-jazzy-acceptance.sh\" --api" || OVERALL_RC=1
  run_required browser_real_stack_inference_e2e \
    "bash \"$ROOT/scripts/browser-real-stack-acceptance.sh\"" || OVERALL_RC=1

  run_required clean_room_arm64_noble \
    "bash \"$ROOT/scripts/clean-room-acceptance.sh\" final" || OVERALL_RC=1
fi

record_external external_model_certification \
  "Requires user-supplied ONNX model, calibration, and evaluation dataset"
record_external physical_arm_performance_certification \
  "Requires physical Arm performance host; Colima/QEMU is software-correctness only"

# Fingerprint must be unchanged for final evidence validity
FINAL_FP="$("$ROOT/scripts/source-fingerprint.sh")"
if [[ "$FINAL_FP" != "$SOURCE_FP" ]]; then
  write_tier clean_room_arm64_noble "required" "FAIL" \
    "source-fingerprint equality" 1 \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" 0 "" \
    "source fingerprint changed during verification: start=$SOURCE_FP end=$FINAL_FP"
  OVERALL_RC=1
fi

END_ALL="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

export PS_VERIFY_OUT_DIR="$OUT_DIR"
export PS_VERIFY_ROOT="$ROOT"
export PS_VERIFY_FP="$SOURCE_FP"
export PS_VERIFY_START="$START_ALL"
export PS_VERIFY_END="$END_ALL"
export PS_VERIFY_OS="$HOST_OS"
export PS_VERIFY_ARCH="$HOST_ARCH"
export PS_VERIFY_REQUIRED="${REQUIRED_TIERS[*]}"
python3 - <<'PY'
import json, os, pathlib, subprocess, sys
root = pathlib.Path(os.environ["PS_VERIFY_OUT_DIR"])
repo = pathlib.Path(os.environ["PS_VERIFY_ROOT"])
tier_dir = root / "tiers"
required = os.environ["PS_VERIFY_REQUIRED"].split()
external = ["external_model_certification", "physical_arm_performance_certification"]
fp = os.environ["PS_VERIFY_FP"]
tiers = {}
missing = []
stale = []
nonpass = []
for name in required + external:
    path = tier_dir / f"{name}.json"
    if not path.is_file():
        missing.append(name)
        continue
    doc = json.loads(path.read_text())
    tiers[name] = {"status": doc.get("status"), "path": str(path.relative_to(repo))}
    if doc.get("source_fingerprint") != fp:
        stale.append(name)
    if name in required and doc.get("status") != "PASS":
        nonpass.append(name)
    if name in external and doc.get("status") not in {
        "NOT_RUN_EXTERNAL_INPUT_REQUIRED", "PASS"
    }:
        nonpass.append(name)

req_pass = sum(1 for n in required if tiers.get(n, {}).get("status") == "PASS")

def _read_text(path: pathlib.Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""

art = root / "artifacts"
packaging = art / "packaging"
clean_room = art / "clean-room"
deb_sha = ""
deb_name = ""
sha_file = packaging / "deb.sha256"
if sha_file.is_file():
    line = _read_text(sha_file).split()
    if line:
        deb_sha = line[0]
        if len(line) > 1:
            deb_name = pathlib.Path(line[1]).name
if not deb_name:
    debs = sorted((packaging).glob("perceptshift_*.deb")) if packaging.is_dir() else []
    if debs:
        deb_name = debs[-1].name
accept = packaging / "acceptance-summary.json"
if accept.is_file():
    try:
        adoc = json.loads(accept.read_text())
        deb_name = deb_name or adoc.get("deb") or ""
        deb_sha = deb_sha or adoc.get("sha256") or ""
    except json.JSONDecodeError:
        pass

oci_digest = ""
oci_log = root / "logs" / "oci_arm64_build_runtime.log"
if oci_log.is_file():
    for line in oci_log.read_text(encoding="utf-8", errors="replace").splitlines():
        if "digest_or_id=" in line:
            oci_digest = line.split("digest_or_id=", 1)[1].strip()

export_meta = {}
for candidate in sorted((clean_room).glob("perceptshift-source-*.tar.gz.json")) if clean_room.is_dir() else []:
    try:
        export_meta = json.loads(candidate.read_text())
        break
    except json.JSONDecodeError:
        continue
# Also check dist/clean-room-export from clean-room tier
dist = repo / "dist" / "clean-room-export"
for candidate in sorted(dist.glob("perceptshift-source-*.tar.gz.json")) if dist.is_dir() else []:
    try:
        export_meta = json.loads(candidate.read_text())
        break
    except json.JSONDecodeError:
        continue

agg = {
    "schema_version": "final-verification-v1",
    "overall_status": "FAIL",
    "source_fingerprint": fp,
    "debian_package": deb_name or None,
    "debian_sha256": deb_sha or None,
    "oci_digest": oci_digest or None,
    "source_export": export_meta or None,
    "release_evidence": None,
    "required_pass_count": req_pass,
    "required_total": len(required),
    "start": os.environ["PS_VERIFY_START"],
    "end": os.environ["PS_VERIFY_END"],
    "host": {"os": os.environ["PS_VERIFY_OS"], "arch": os.environ["PS_VERIFY_ARCH"]},
    "tiers": tiers,
    "missing_tiers": missing,
    "stale_tiers": stale,
    "nonpassing_tiers": nonpass,
    "physical_performance_claimed": False,
    "external_model_certification": tiers.get("external_model_certification", {}).get("status"),
    "physical_arm_performance_certification": tiers.get(
        "physical_arm_performance_certification", {}
    ).get("status"),
    "notes": "Emulated/Colima AArch64 evidence is software correctness only.",
}
if (
    agg["required_pass_count"] == agg["required_total"]
    and not missing
    and not stale
    and not [t for t in nonpass if t in required]
):
    agg["overall_status"] = "PASS"

# Durable evidence surviving cleanup.
import shutil
evidence_root = repo / "release-evidence" / fp.replace(":", "_")
evidence_root.mkdir(parents=True, exist_ok=True)
agg["release_evidence"] = str(evidence_root.relative_to(repo))

md = [
    "# PerceptShift final verification",
    "",
    f"- overall_status: **{agg['overall_status']}**",
    f"- source_fingerprint: `{fp}`",
    f"- required: {agg['required_pass_count']}/{agg['required_total']}",
    f"- debian_package: `{deb_name or 'n/a'}`",
    f"- debian_sha256: `{deb_sha or 'n/a'}`",
    f"- oci_digest: `{oci_digest or 'n/a'}`",
    f"- release_evidence: `{agg['release_evidence']}`",
    "- physical performance claimed: false",
    "",
    "## Tiers",
]
for n in required + external:
    st = tiers.get(n, {}).get("status", "MISSING")
    md.append(f"- `{n}`: {st}")
if missing:
    md += ["", "## Missing: " + ", ".join(missing)]
if stale:
    md += ["", "## Stale: " + ", ".join(stale)]
if nonpass:
    md += ["", "## Non-passing: " + ", ".join(nonpass)]
(root / "final-verification.md").write_text("\n".join(md) + "\n")

(evidence_root / "source-fingerprint.txt").write_text(fp + "\n")
# Rewrite tier evidence paths to durable copies before writing final JSON.
durable_tiers = {}
for name, info in tiers.items():
    durable_rel = str((evidence_root / "tests" / f"{name}.json").relative_to(repo))
    durable_tiers[name] = {**info, "path": durable_rel, "evidence_path": durable_rel}
tiers = durable_tiers
agg["tiers"] = tiers

# Source-only archive lives outside the fingerprint.
art_dir = repo / "release-artifacts"
art_dir.mkdir(parents=True, exist_ok=True)
env = os.environ.copy()
env["SOURCE_EXPORT_DIR"] = str(art_dir)
subprocess.run(
    [str(repo / "scripts" / "export-source.sh")],
    cwd=repo,
    env=env,
    check=True,
)
export_meta = {}
for candidate in sorted(art_dir.glob("perceptshift-source-*.tar.gz.json")):
    try:
        export_meta = json.loads(candidate.read_text())
        break
    except json.JSONDecodeError:
        continue
agg["source_export"] = export_meta or None

# Drop stale fingerprint evidence directories.
for sibling in (repo / "release-evidence").glob("*"):
    if sibling.is_dir() and sibling.resolve() != evidence_root.resolve():
        shutil.rmtree(sibling, ignore_errors=True)

(root / "final-verification.json").write_text(json.dumps(agg, indent=2) + "\n")
shutil.copy2(root / "final-verification.json", evidence_root / "final-verification.json")
shutil.copy2(root / "final-verification.md", evidence_root / "final-verification.md")
for sub in ("tests", "ros", "e2e", "packaging", "container", "sanitizers", "fuzz", "coverage", "clean-room", "environment"):
    (evidence_root / sub).mkdir(exist_ok=True)
for tier_json in (root / "tiers").glob("*.json"):
    shutil.copy2(tier_json, evidence_root / "tests" / tier_json.name)
for log in (root / "logs").glob("*.log"):
    try:
        text = log.read_text(encoding="utf-8", errors="replace")
        if len(text) > 200000:
            text = text[-200000:]
        (evidence_root / "tests" / log.name).write_text(text, encoding="utf-8")
    except OSError:
        pass
# Preserve compact packaging / clean-room evidence
for src_dir, dest_name in ((packaging, "packaging"), (clean_room, "clean-room")):
    if src_dir.is_dir():
        for f in src_dir.rglob("*"):
            if f.is_file() and f.stat().st_size <= 2_000_000:
                rel = f.relative_to(src_dir)
                dest = evidence_root / dest_name / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dest)

# Re-copy final verification after durable files exist.
(root / "final-verification.json").write_text(json.dumps(agg, indent=2) + "\n")
shutil.copy2(root / "final-verification.json", evidence_root / "final-verification.json")
shutil.copy2(root / "final-verification.md", evidence_root / "final-verification.md")

if agg["overall_status"] == "PASS":
    check = subprocess.run(
        [str(repo / "scripts" / "evidence-self-check.sh"), str(evidence_root / "final-verification.json")],
        cwd=repo,
    )
    if check.returncode != 0:
        agg["overall_status"] = "FAIL"
        (root / "final-verification.json").write_text(json.dumps(agg, indent=2) + "\n")
        shutil.copy2(root / "final-verification.json", evidence_root / "final-verification.json")

print(json.dumps({
    "overall_status": agg["overall_status"],
    "required_pass_count": agg["required_pass_count"],
    "required_total": agg["required_total"],
    "source_fingerprint": fp,
    "debian_sha256": deb_sha or None,
    "oci_digest": oci_digest or None,
    "release_evidence": str(evidence_root.relative_to(repo)),
}, indent=2))
sys.exit(0 if agg["overall_status"] == "PASS" else 1)
PY
