#!/usr/bin/env bash
# Coverage acceptance: Python >=80% (with documented omissions) + C++ gcov >=70%.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
OUT="$ROOT/build/verification/coverage"
mkdir -p "$OUT"

export PATH="$ROOT/build/default/cpp:$ROOT/build/dev-arm64/cpp:${PATH:-}"
export DYLD_LIBRARY_PATH="${PERCEPTSHIFT_ORT_ROOT:-$ROOT/.cache/onnxruntime}/lib:${DYLD_LIBRARY_PATH:-}"
export LD_LIBRARY_PATH="${PERCEPTSHIFT_ORT_ROOT:-$ROOT/.cache/onnxruntime}/lib:${LD_LIBRARY_PATH:-}"

PYTHON="${ROOT}/.venv/bin/python"
[[ -x "$PYTHON" ]] || PYTHON=python3

echo "== Python coverage =="
"$PYTHON" -m pytest python \
  --cov=perceptshift_common --cov=perceptshift_forge --cov=perceptshift_cli --cov=perceptshift_api \
  --cov-config="$ROOT/.coveragerc" \
  --cov-report=term-missing \
  --cov-report=xml:"$OUT/python-coverage.xml" \
  --cov-fail-under=80 -q | tee "$OUT/python-coverage.log"

# Critical Forge modules floor (orchestration + certification).
"$PYTHON" - <<PY
import xml.etree.ElementTree as ET
from pathlib import Path
root = ET.parse(Path("$OUT/python-coverage.xml")).getroot()
critical = {
    # Residual orchestration error/environment branches are covered by forge_*_e2e tiers.
    "perceptshift_forge/orchestration/__init__.py": 70.0,
    "perceptshift_forge/certification/__init__.py": 85.0,
    "perceptshift_forge/certification/context.py": 80.0,
}
rates = {}
for cls in root.iter("class"):
    name = cls.attrib.get("filename", "")
    for key in critical:
        if name.endswith(key) or key in name:
            line_rate = float(cls.attrib.get("line-rate", 0)) * 100.0
            rates[key] = line_rate
missing = [k for k in critical if k not in rates]
if missing:
    raise SystemExit(f"critical modules missing from coverage report: {missing}")
bad = {k: v for k, v in rates.items() if v < critical[k]}
print("critical_forge_rates", rates)
if bad:
    raise SystemExit(f"critical forge coverage below floor: {bad}")
print("CRITICAL_FORGE_OK")
PY

echo "== C++ coverage (Linux arm64 gcov) =="
PLATFORM="${DOCKER_PLATFORM:-linux/arm64}"
docker run --rm --platform "$PLATFORM" \
  -v "$ROOT:/src" -v "$ROOT/.cache:/src/.cache" -v "$OUT:/out" \
  ubuntu:24.04 bash -lc '
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq build-essential cmake ninja-build git python3 \
  libssl-dev zlib1g-dev gcovr >/dev/null
bash /src/scripts/coverage-cpp.sh
'

echo "STATUS=PASS gate=coverage"
