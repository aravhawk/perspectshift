# ADR 0001: Development host vs primary runtime platform

## Status

Accepted

## Context

The primary runtime and acceptance platform is Ubuntu 24.04 LTS on AArch64 with
ROS 2 Jazzy. Development and CI also target Ubuntu 24.04 x86_64 for functional
coverage. Initial implementation may occur on macOS Apple Silicon where CMake,
Python, and Node toolchains are available but ROS 2 Jazzy, Debian packaging,
systemd, and Linux sysfs telemetry providers are not.

## Decision

1. Keep Linux AArch64 + ROS 2 Jazzy as the normative production platform.
2. Compile and unit-test portable C++/Python/web components on macOS where
   possible, with Linux-only providers returning structured unavailable reasons.
3. Treat QEMU and non-Linux hosts as compatibility aids only; never derive
   performance or thermal claims from them.
4. Mark native Arm64 Linux acceptance, ROS E2E, Debian install smoke, and
   systemd validation as not executed when those environments are absent.

## Consequences

- Host inspection and telemetry APIs must encode unavailable measurements with
  reason codes rather than fabricated values.
- Packaging and ROS packages ship complete sources even when they cannot be
  built on the current development host.
- Delivery reports must separate software completeness from hardware-gated
  verification.
