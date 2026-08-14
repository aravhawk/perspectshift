# Testing

- C++ unit/property/integration/fuzz under `cpp/tests/`
- Python tests beside each package
- ROS tests in package `test/` directories
- Cross-component under `tests/`
- E2E: `./scripts/run-e2e.sh`
- Repository policy: `./scripts/verify-repository.sh`
- Native Arm: `./scripts/run-arm-acceptance.sh` (real AArch64 only)

Fixtures are generated at test time in temporary directories. Binaries are not committed.
