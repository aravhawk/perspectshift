# PerceptShift

Local-first, **deadline-aware** adaptive inference for Arm64 ROS 2 systems.
It profiles, certifies, and switches among quality-attested ONNX Runtime execution
profiles. Soft real-time only: not hard real-time, not functionally safety-certified.

## Supported adapters (v1)

- `raw_tensor`
- `image_classification`
- `yolo_v8_detection`

## Prerequisites

- CMake ≥ 3.28, Ninja, C++20 toolchain
- ONNX Runtime **1.28.0** (`PERCEPTSHIFT_ORT_ROOT` or `ORT_PREFIX`)
- Python 3.12+ with `uv`
- Node 24+ with `pnpm` (console)
- ROS 2 Jazzy (Ubuntu 24.04) for ROS / API mutation tiers

## Quick start (developer)

```bash
# Install / point at ORT 1.28.0
export PERCEPTSHIFT_ORT_ROOT="$PWD/.cache/onnxruntime"
# or: ./scripts/build-onnxruntime.sh

cmake --preset default && cmake --build --preset default -j
ctest --test-dir build/default --output-on-failure

uv sync --all-packages
uv run pytest python -q

# Software E2E with runtime-generated fixtures (not product benchmarks)
./scripts/run-e2e.sh --native-only
```

## Verification

```bash
make verify            # canonical complete 26-tier software release verifier
make verify-host       # fast host-only subset
./scripts/verify-all.sh --tier native_arm64   # real AArch64 only
./scripts/verify-all.sh --tier ros_jazzy      # requires ROS 2 Jazzy
```

Evidence is written to `build/verification/` and compact durable copies under
`release-evidence/`.

## Architecture

- `cpp/` — production inference engine, workers, adaptive controller
- `python/perceptshift_forge/` — offline Forge orchestration
- `python/perceptshift_cli/` — operator CLI
- `python/perceptshift_api/` — loopback operational API
- `ros2_ws/` — ROS 2 transport wrapping the C++ core
- `web/` — operational console
- `config/schemas/` — versioned contracts

## Security boundary

Local-first. Mutation APIs require a token. Bundles are hash-inventoried and optionally
Ed25519-signed. Unavailable telemetry is reported with validity flags — never substituted
as zero measurements.

## Known limitations

- Official macOS ORT builds may lack XNNPACK; registration failure is reported truthfully.
- ROS / Debian / Docker tiers require Linux environments.
- External model certification requires operator-supplied ONNX + calibration/evaluation data.
- Control-hold is a **request**, not an actuator command.
- Individual container images are not an integrated ROS product stack.

See `docs/` for operational detail.
