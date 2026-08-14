#!/usr/bin/env bash
# Canonical end-to-end software test harness.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

CONTAINERS=0
NATIVE_ARM=0
NATIVE_ONLY=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --containers) CONTAINERS=1 ;;
    --native-arm) NATIVE_ARM=1 ;;
    --native-only) NATIVE_ONLY=1 ;;
    -h|--help)
      echo "Usage: run-e2e.sh [--containers] [--native-arm] [--native-only]"
      exit 0
      ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

TMP="$(mktemp -d "${TMPDIR:-/tmp}/perceptshift-e2e.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT

echo "E2E workspace: $TMP"
export PERCEPTSHIFT_E2E_TMP="$TMP"
export PERCEPTSHIFT_ORT_ROOT="${PERCEPTSHIFT_ORT_ROOT:-$ROOT/.cache/onnxruntime}"
export DYLD_LIBRARY_PATH="$PERCEPTSHIFT_ORT_ROOT/lib:${DYLD_LIBRARY_PATH:-}"
export LD_LIBRARY_PATH="$PERCEPTSHIFT_ORT_ROOT/lib:${LD_LIBRARY_PATH:-}"

RUNTIME_BIN=""
for cand in \
  "$ROOT/build/default/cpp/perceptshift-runtime" \
  "$ROOT/build/dev-arm64/cpp/perceptshift-runtime" \
  "$ROOT/build/release-arm64/cpp/perceptshift-runtime"
do
  if [[ -x "$cand" ]]; then RUNTIME_BIN="$cand"; break; fi
done
BENCH_BIN=""
for cand in \
  "$ROOT/build/default/cpp/perceptshift-bench-worker" \
  "$ROOT/build/dev-arm64/cpp/perceptshift-bench-worker"
do
  if [[ -x "$cand" ]]; then BENCH_BIN="$cand"; break; fi
done
INSPECT_BIN=""
for cand in \
  "$ROOT/build/default/cpp/perceptshift-inspect-worker" \
  "$ROOT/build/dev-arm64/cpp/perceptshift-inspect-worker"
do
  if [[ -x "$cand" ]]; then INSPECT_BIN="$cand"; break; fi
done

if [[ -z "$RUNTIME_BIN" || -z "$BENCH_BIN" || -z "$INSPECT_BIN" ]]; then
  echo "Native binaries missing; build ORT-enabled targets first" >&2
  exit 1
fi
export PERCEPTSHIFT_RUNTIME_BIN="$RUNTIME_BIN"

"$RUNTIME_BIN" --version
"$RUNTIME_BIN" --doctor >/dev/null
"$INSPECT_BIN" --host >/dev/null

# Generate tiny ONNX + Forge run + runtime inference via Python (test fixtures only).
uv run python - <<PY
import json, os, shutil, subprocess, sys
from pathlib import Path
import yaml

tmp = Path(os.environ["PERCEPTSHIFT_E2E_TMP"])
root = Path("$ROOT")
sys.path.insert(0, str(root / "python" / "perceptshift_forge" / "src"))
sys.path.insert(0, str(root / "python" / "perceptshift_common" / "src"))

import importlib.util
spec = importlib.util.spec_from_file_location("helpers", root / "python" / "perceptshift_forge" / "tests" / "helpers.py")
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)

model = helpers.make_tiny_onnx(tmp / "model.onnx")
cal_root = tmp / "cal"; ev_root = tmp / "ev"
helpers.write_rgb_image(cal_root / "a.png", (1, 2, 3))
helpers.write_rgb_image(ev_root / "b.png", (4, 5, 6))
cal = helpers.write_json(tmp / "cal.json", helpers.classification_manifest(cal_root, [{"path": "a.png", "class_id": 0}]))
ev_doc = helpers.classification_manifest(ev_root, [{"path": "b.png", "class_id": 1}])
ev_doc["split_name"] = "evaluation"
ev = helpers.write_json(tmp / "ev.json", ev_doc)

cfg = {
  "schema_version": "1.0",
  "document_type": "perceptshift.forge_config",
  "project": {"name": "e2e", "output_root": str((tmp / "out").resolve()), "random_seed": 7},
  "model": {
    "baseline_path": str(model.resolve()),
    "adapter": "raw_tensor",
    "adapter_config": {},
    "expected_input": {},
    "allowed_model_roots": [str(tmp.resolve())],
  },
  "datasets": {
    "calibration_manifest": str(cal.resolve()),
    "evaluation_manifest": str(ev.resolve()),
    "prohibit_cross_split_duplicates": True,
  },
  "quantization": {"enabled": False, "methods": ["minmax"], "format": "qdq",
                   "activation_type": "qint8", "weight_type": "qint8",
                   "per_channel_options": [False], "nodes_to_exclude": [],
                   "calibration_sample_limit": None},
  "candidates": {
    "include_baseline": True, "user_model_variants": [],
    "execution_providers": [{"name": "cpu", "provider_order": ["CPUExecutionProvider"]}],
    "xnnpack_thread_counts": [1], "ort_intra_op_thread_counts": [1],
    "ort_inter_op_thread_counts": [1], "allow_intra_op_spinning": [False],
    "graph_optimization_levels": ["all"], "preprocess_backends": ["scalar"],
    "input_variants": [],
  },
  "benchmark": {
    "warmup_iterations": 1, "measured_iterations": 2, "independent_trials": 1,
    "randomize_candidate_order": False, "cold_start_trials": 0,
    "per_candidate_timeout_seconds": 60, "maximum_worker_rss_mb": 1024,
    "minimum_stabilization_seconds": 0, "maximum_start_temperature_c": 99.0,
    "maximum_temperature_drift_c": 50.0, "require_no_throttling": False,
    "collect_perf": False, "collect_ros_trace": False, "bootstrap_resamples": 100,
  },
  "quality": {
    "metric_name": "numeric_equivalence", "direction": "higher_is_better",
    "minimum_absolute_value": 0.0, "maximum_degradation_from_baseline": 1.0,
    "confidence_level": 0.95,
  },
  "certification": {
    "deadline_ms": 500.0, "maximum_peak_rss_mb": 2048, "maximum_model_size_mb": 1024,
    "require_xnnpack_assignment": False, "maximum_cpu_fallback_fraction": None,
    "require_valid_environment": False, "require_output_equivalence": False,
    "sign_bundle": False, "signing_key_path": None,
  },
  "report": {"formats": ["json"], "include_raw_sample_links": False, "include_environment": True},
}
cfg_path = tmp / "forge.yaml"
cfg_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")

os.environ["XDG_DATA_HOME"] = str(tmp / "xdg")
from perceptshift_forge.orchestration import run_forge
result = run_forge(cfg_path, maximum_candidates=8)
assert result["status"] == "completed", result
bundle = Path(result["root"]) / "bundle" / "profile-bundle"
assert (bundle / "manifest.json").is_file()
# Corrupt copy must fail integrity.
corrupt = tmp / "corrupt-bundle"
shutil.copytree(bundle, corrupt)
(corrupt / "NOTICE").write_text("tampered\n", encoding="utf-8")
RUNTIME_BIN = os.environ["PERCEPTSHIFT_RUNTIME_BIN"]
proc = subprocess.run([RUNTIME_BIN, "--bundle", str(corrupt), "--json", "--input", "zeros"], capture_output=True, text=True)
assert proc.returncode != 0, "corrupt bundle must fail"
proc = subprocess.run([RUNTIME_BIN, "--bundle", str(bundle), "--json", "--input", "zeros"], capture_output=True, text=True)
print(proc.stdout)
print(proc.stderr, file=sys.stderr)
assert proc.returncode == 0, proc.stderr
payload = json.loads(proc.stdout)
assert payload.get("status") == "ok"
assert payload.get("inference", {}).get("ok") is True
print("native_e2e_ok", json.dumps({"run_id": result["run_id"], "bundle": str(bundle)}))
PY

if [[ "$NATIVE_ONLY" -eq 0 && -d tests/e2e ]]; then
  if command -v uv >/dev/null 2>&1; then
    uv run pytest tests/e2e -q --tb=short
  elif command -v pytest >/dev/null 2>&1; then
    pytest tests/e2e -q --tb=short
  else
    echo "pytest unavailable for tests/e2e" >&2
    exit 1
  fi
fi

if [[ "$CONTAINERS" -eq 1 ]]; then
  if command -v docker >/dev/null 2>&1; then
    bash "$ROOT/scripts/container-acceptance.sh"
  else
    echo "docker unavailable; container E2E cannot run" >&2
    exit 1
  fi
fi

if [[ "$NATIVE_ARM" -eq 1 ]]; then
  ARCH="$(uname -m)"
  if [[ "$ARCH" != "aarch64" && "$ARCH" != "arm64" ]]; then
    echo "native-arm flag set but host is $ARCH; not claiming Arm results" >&2
    exit 2
  fi
fi

echo "run-e2e.sh complete"
