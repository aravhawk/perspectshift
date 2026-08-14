#!/usr/bin/env bash
# C++ coverage portion (Linux arm64). Invoked inside Ubuntu container with /src mounted.
set -euo pipefail
cd /src
rm -rf build/coverage
cmake -S . -B build/coverage \
  -DCMAKE_BUILD_TYPE=Debug \
  -DPERCEPTSHIFT_ENABLE_COVERAGE=ON \
  -DPERCEPTSHIFT_ORT_ROOT=/src/.cache/onnxruntime-linux-aarch64-1.28.0 \
  -DPERCEPTSHIFT_BUILD_TESTS=ON
cmake --build build/coverage -j2
ctest --test-dir build/coverage --output-on-failure

mkdir -p /out
gcovr -r /src/cpp \
  --object-directory /src/build/coverage \
  --filter '.*/digest\.cpp' \
  --filter '.*/latest_frame_queue\.cpp' \
  --filter '.*/raw_tensor_adapter\.cpp' \
  --exclude '.*/tests/.*' --exclude '.*/_deps/.*' \
  --print-summary --fail-under-line 70 \
  --xml /out/cpp-coverage.xml | tee /out/cpp-coverage.log

gcovr -r /src/cpp \
  --object-directory /src/build/coverage \
  --filter '.*/controller\.cpp' \
  --filter '.*/eligibility\.cpp' \
  --filter '.*/preprocessor_scalar\.cpp' \
  --filter '.*/bundle_loader\.cpp' \
  --exclude '.*/tests/.*' --exclude '.*/_deps/.*' \
  --json /out/cpp-represented.json >/dev/null

python3 - <<'PY'
import json
from pathlib import Path

doc = json.loads(Path("/out/cpp-represented.json").read_text(encoding="utf-8"))
needed = ["controller.cpp", "eligibility.cpp", "preprocessor_scalar.cpp", "bundle_loader.cpp"]
found = set()
for meta in doc.get("files") or []:
    path = meta.get("file") or meta.get("path") or ""
    for name in needed:
        if path.endswith(name):
            lines = meta.get("lines")
            if isinstance(lines, list):
                total = len(lines)
                covered = sum(1 for line in lines if (line.get("count") or 0) > 0)
            elif isinstance(lines, dict):
                total = int(lines.get("total") or 0)
                covered = int(lines.get("covered") or 0)
            else:
                total = int(meta.get("line_total") or 0)
                covered = int(meta.get("line_covered") or 0)
            rate = (100.0 * covered / total) if total else 0.0
            print(name, f"{rate:.1f}%", covered, total)
            assert rate > 0.0, name
            found.add(name)
missing = [name for name in needed if name not in found]
assert not missing, missing
print("CPP_REPRESENTED_OK")
PY

echo "cpp_coverage_scope=digest,latest_frame_queue,raw_tensor_adapter (+ represented controller/eligibility/preprocessor_scalar/bundle_loader)"
