# Supported platforms

## Primary targets

- Ubuntu 24.04 LTS on AArch64 (Arm64), including SBCs such as Raspberry Pi-class boards when the OS and dependencies are supported.
- ROS 2 Jazzy on the same hosts for the ROS integration packages.
- ONNX Runtime CPU and XNNPACK execution providers.

## Secondary / developer hosts

- Ubuntu 24.04 x86_64 for CI, packaging, and software verification.
- macOS may be used for documentation and repository policy checks; native Arm64 Linux acceptance and ROS Jazzy builds are not claimed on macOS.

## Explicit non-claims

- QEMU/emulation results are not native performance evidence.
- Hardware-specific latency and power numbers are not portable across boards without re-measurement.
- Hard real-time kernels and functional-safety certification are out of scope.
