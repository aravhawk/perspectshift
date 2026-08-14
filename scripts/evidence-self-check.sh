#!/usr/bin/env bash
# Assert final-verification.json points at durable existing evidence.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

FINAL="${1:-}"
if [[ -z "$FINAL" ]]; then
  if [[ -n "${PERCEPTSHIFT_FINAL_VERIFICATION:-}" ]]; then
    FINAL="$PERCEPTSHIFT_FINAL_VERIFICATION"
  else
    CAND="$(ls -1dt release-evidence/tree_*/final-verification.json 2>/dev/null | head -1 || true)"
    if [[ -z "$CAND" ]]; then
      CAND="build/verification/final-verification.json"
    fi
    FINAL="$CAND"
  fi
fi

if [[ ! -f "$FINAL" ]]; then
  echo "ERROR: final-verification.json missing: $FINAL" >&2
  exit 1
fi

python3 - "$ROOT" "$FINAL" <<'PY'
import hashlib, json, pathlib, re, subprocess, sys

root = pathlib.Path(sys.argv[1]).resolve()
final_path = pathlib.Path(sys.argv[2]).resolve()
doc = json.loads(final_path.read_text(encoding="utf-8"))
errors: list[str] = []

def fail(msg: str) -> None:
    errors.append(msg)

if doc.get("overall_status") != "PASS":
    fail(f"overall_status={doc.get('overall_status')!r} (want PASS)")
if doc.get("required_pass_count") != 26:
    fail(f"required_pass_count={doc.get('required_pass_count')!r} (want 26)")
if doc.get("required_total") != 26:
    fail(f"required_total={doc.get('required_total')!r} (want 26)")

current = subprocess.check_output([str(root / "scripts/source-fingerprint.sh")], cwd=root, text=True).strip()
recorded = doc.get("source_fingerprint")
if current != recorded:
    fail(f"current fingerprint {current} != recorded {recorded}")

allowed_external = {"NOT_RUN_EXTERNAL_INPUT_REQUIRED", "PASS"}
if doc.get("external_model_certification") not in allowed_external:
    fail("external_model_certification has a disallowed value")
if doc.get("physical_arm_performance_certification") not in allowed_external:
    fail("physical_arm_performance_certification has a disallowed value")
if doc.get("physical_performance_claimed") is True:
    fail("physical_performance_claimed must not be true")

deb_sha = doc.get("debian_sha256") or ""
if not re.fullmatch(r"[0-9a-f]{64}", deb_sha or ""):
    fail("debian_sha256 is not 64 lowercase hex")
if not doc.get("oci_digest"):
    fail("oci_digest is empty")

tiers = doc.get("tiers") or {}
required = [
    "repository_hygiene", "schema_contracts", "python_format_lint_typecheck",
    "python_unit_contract_tests", "cpp_build_warnings", "cpp_unit_property_tests",
    "canonical_preprocessing_equivalence", "onnx_runtime_executor_e2e",
    "forge_real_path_e2e", "quantization_calibration_equivalence",
    "quality_baseline_degradation", "adaptive_controller_behavior",
    "bundle_integrity_signature", "ros_jazzy_build_tests", "ros_runtime_inference_e2e",
    "api_contract_tests", "api_ros_runtime_e2e", "web_unit_tests",
    "browser_real_stack_inference_e2e", "debian_arm64_package_install_uninstall",
    "oci_arm64_build_runtime", "asan_ubsan", "tsan", "fuzz", "coverage",
    "clean_room_arm64_noble",
]
for name in required:
    info = tiers.get(name) or {}
    if info.get("status") != "PASS":
        fail(f"tier {name} status={info.get('status')!r}")
    path_raw = info.get("path") or info.get("evidence_path")
    if not path_raw:
        fail(f"tier {name} missing evidence path")
        continue
    if "build/verification" in str(path_raw):
        fail(f"tier {name} evidence path points at deleted build/verification: {path_raw}")
    p = pathlib.Path(path_raw)
    if not p.is_absolute():
        p = root / p
    if not p.is_file():
        fail(f"tier {name} evidence missing: {path_raw}")
    else:
        try:
            tdoc = json.loads(p.read_text(encoding="utf-8"))
            if tdoc.get("status") != "PASS":
                fail(f"tier {name} durable status={tdoc.get('status')!r}")
            if tdoc.get("source_fingerprint") not in {None, recorded}:
                fail(f"tier {name} fingerprint mismatch")
        except json.JSONDecodeError:
            fail(f"tier {name} evidence is not JSON: {path_raw}")

export = doc.get("source_export") or {}
archive_name = export.get("archive")
archive_sha = export.get("sha256")
candidates = []
if export.get("path"):
    candidates.append(root / export["path"] if not pathlib.Path(export["path"]).is_absolute() else pathlib.Path(export["path"]))
if archive_name:
    candidates.append(root / "release-artifacts" / archive_name)
    candidates.append(root / "dist" / archive_name)
archive = next((c for c in candidates if c.is_file()), None)
if archive is None:
    fail(f"source export archive missing ({archive_name})")
else:
    actual = hashlib.sha256(archive.read_bytes()).hexdigest()
    if archive_sha and actual != archive_sha:
        fail("source export SHA-256 does not match the archive")
    if export.get("source_fingerprint") not in {None, recorded}:
        fail("source export fingerprint does not match final fingerprint")

if errors:
    print("evidence self-check FAILED:", file=sys.stderr)
    for e in errors:
        print(f"  - {e}", file=sys.stderr)
    sys.exit(1)
print("evidence self-check PASSED")
PY
