#!/usr/bin/env bash
# Generate a software bill of materials (CycloneDX preferred).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${SBOM_OUT:-$ROOT/build/sbom}"
mkdir -p "$OUT_DIR"

echo "Generating SBOMs under $OUT_DIR"

if command -v syft >/dev/null 2>&1; then
  syft dir:"$ROOT" -o cyclonedx-json >"$OUT_DIR/perceptshift.cdx.json"
  syft dir:"$ROOT" -o spdx-json >"$OUT_DIR/perceptshift.spdx.json"
  echo "Wrote CycloneDX and SPDX via syft"
elif command -v cdxgen >/dev/null 2>&1; then
  cdxgen -o "$OUT_DIR/perceptshift.cdx.json" "$ROOT"
  echo "Wrote CycloneDX via cdxgen"
else
  python3 - <<PY
import json, pathlib, hashlib
root = pathlib.Path("$ROOT")
out = pathlib.Path("$OUT_DIR") / "perceptshift.inventory.json"
manifests = []
for pattern in ["**/package.json", "**/pyproject.toml", "**/CMakeLists.txt", "**/package.xml"]:
    for path in root.glob(pattern):
        if any(p in path.parts for p in (".git", "node_modules", ".venv", "build", ".cache")):
            continue
        data = path.read_bytes()
        manifests.append({
            "path": str(path.relative_to(root)),
            "sha256": hashlib.sha256(data).hexdigest(),
            "size": len(data),
        })
doc = {
    "bomFormat": "PerceptShiftInventory",
    "specVersion": "0.1",
    "note": "Fallback inventory; install syft or cdxgen for CycloneDX/SPDX",
    "components": manifests,
}
out.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
print(f"Wrote fallback inventory to {out}")
PY
fi

echo "generate-sbom.sh complete"
