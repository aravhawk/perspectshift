# Agent instructions for PerceptShift

## Product

PerceptShift is a local-first, deadline-aware adaptive inference platform that
profiles, certifies, and switches among quality-attested ONNX Runtime execution
profiles on Arm64 ROS 2 systems.

## Non-negotiable rules

1. Never fabricate measurements, quality scores, or hardware results.
2. Never ship production TODO/FIXME/stub/NotImplementedError paths.
3. Never bundle models, datasets, bags, or precomputed benchmarks.
4. Never claim hard real-time, functional safety, or actuator command authority.
5. Prefer explicit unavailable reason codes over silent omission.
6. Keep schemas in `config/schemas/` as the contract source of truth.
7. Production inference path is C++; offline orchestration is Python; ROS wraps C++ core.
8. Run verification commands; do not claim success from inspection alone.

## Safety language

- say `deadline-aware`, not `deadline-guaranteed`
- say `offline-attested quality floor`, not `guaranteed runtime accuracy`
- say `control-hold request`, not `emergency stop command`
- say `fail-closed state`, not certified `safe state`

## Architecture ownership

- `cpp/` — production inference engine
- `python/perceptshift_forge/` — offline orchestration
- `python/perceptshift_cli/` — operator CLI
- `python/perceptshift_api/` — local API
- `ros2_ws/` — ROS transport only
- `web/` — operational console presentation
- `config/schemas/` — versioned contracts
- `deploy/` — containers, systemd, logrotate, tmpfiles
- `docs/` — operational truth matching executable behavior

## Useful commands

```bash
make setup
make build
make test
make verify
make verify-host
make verify-arm
./scripts/verify-repository.sh
./scripts/release-verify.sh
./scripts/run-e2e.sh
./scripts/run-arm-acceptance.sh
```

## Formatting and tests

- C++: `.clang-format`, `.clang-tidy`
- Python: Ruff via pre-commit / `make lint`
- Web: pnpm workspace under `web/`
- Pre-commit: `.pre-commit-config.yaml` (convenience, not a CI substitute)

## How to add an adapter

1. Implement in `cpp/include/perceptshift/adapters/` and `cpp/src/adapters/`.
2. Register via `adapter_factory`.
3. Document tensor layouts and confidence semantics in `docs/model-adapters.md`.
4. Add unit tests with runtime-generated fixtures (no committed model binaries).

## How to add a schema version

1. Add `config/schemas/<name>-vN.schema.json` (never silently break v1 consumers).
2. Update templates under `config/templates/`.
3. Contract-test Python/TS/C++ validators against the schema.
4. Document fields in the relevant docs page.

## Native Arm acceptance

Run only on a real AArch64 host:

```bash
make verify-arm
# or
./scripts/run-arm-acceptance.sh
```

Do not claim native Arm results from QEMU or non-AArch64 machines.
