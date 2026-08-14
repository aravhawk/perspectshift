# Contributing to PerceptShift

## Development setup

On Ubuntu 24.04 (primary):

```bash
./scripts/bootstrap-ubuntu.sh
make setup
make verify-host
```

`make verify` is the complete 26-tier software release verifier and requires the
Linux/Arm64 Docker execution path. Use `make verify-host` for the fast host subset.

On other hosts, use the same commands where dependencies are available. Native
Arm64 Linux validation is required for performance claims.

## Principles

- Do not fabricate benchmark, quality, thermal, power, or hardware results.
- Do not commit models, datasets, bags, or precomputed benchmark artifacts.
- Keep production paths free of placeholders and stubs.
- Prefer measured evidence and explicit unavailable reason codes.
- Match language: deadline-aware, control-hold request, fail-closed state,
  offline-attested quality floor, sensor-to-command-publication latency.

## Pull requests

- Keep changes focused.
- Add or update tests with behavior changes.
- Run `make verify-host` before requesting review. Run `make verify` when changing
  release, packaging, systemd, or container surfaces.
- Update docs when operator-facing behavior changes.
