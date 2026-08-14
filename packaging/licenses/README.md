# Third-party license inventory for PerceptShift distributions.

This directory accounts for licenses of dependencies redistributed or linked
by PerceptShift packages. Upstream license texts should be copied here when a
dependency is vendored or when Debian copyright files require them.

## Policy

- Prefer Apache-2.0 compatible dependencies.
- Do not vendor a dependency without its license and provenance.
- Record exact versions and source URLs in release SBOMs.

## Expected entries (populated when dependencies are pinned)

| Component | License | Notes |
|-----------|---------|-------|
| ONNX Runtime | MIT | Built from official GitHub tags |
| XNNPACK | BSD-3-Clause | Optional execution provider |
| ROS 2 Jazzy packages | Apache-2.0 | System packages, not vendored |
| FastAPI / Starlette | MIT | Python API |
| React / Vite console deps | MIT/Apache-2.0 | See web lockfile |

Generate machine-readable inventories with `./scripts/generate-sbom.sh`.
