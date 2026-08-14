# Release process

1. Ensure `VERSION`, changelog, and schemas are synchronized.
2. Run `./scripts/verify-repository.sh` and `make verify-host` during development.
3. Run `make verify` (`./scripts/release-verify.sh`) as the canonical complete software release gate.
4. On AArch64 hardware, run `make verify-arm` when available. Do not treat QEMU/Colima results as physical performance.
5. `make package` builds the complete supported Debian package and fails if ROS/ORT are missing. Do not use `make package-core-dev` as a release artifact.
6. Tag `vX.Y.Z`. The release workflow runs the canonical verifier and publishes only matching-fingerprint artifacts with checksums.
7. Verify install/uninstall on clean Ubuntu 24.04 using the package acceptance path.

Do not publish fabricated benchmark attachments as release evidence.
