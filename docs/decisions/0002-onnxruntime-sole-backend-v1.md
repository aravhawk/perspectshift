# ADR 0002: ONNX Runtime as sole inference backend in v1

## Status

Accepted

## Context

PerceptShift must certify and switch among production inference profiles without
becoming a generic model optimization framework. Multiple backends would expand
surface area and invite empty placeholder adapters.

## Decision

Version 1 uses ONNX Runtime 1.28.0 with the CPU Execution Provider and XNNPACK
Execution Provider only. Microsoft Olive and other optimizer stacks are not
dependencies. ExecuTorch and LiteRT are out of scope for v1 and must not ship as
empty backends.

## Consequences

- Candidate generation stays narrow and transparent.
- Forge Python `onnxruntime` is pinned to 1.28.0 and must align with the native
  runtime build used by workers.
- Provider fallback evidence is recorded truthfully; silent success on unwanted
  providers is rejected by certification policy when configured.
