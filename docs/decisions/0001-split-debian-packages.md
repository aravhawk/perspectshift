# ADR 0001: Split Debian packages

## Status

Accepted

## Context

Section 20.2 prefers split packages (`perceptshift-core`, `cli`, `ros`, `api`, `console`) while allowing a single package if splitting is fragile.

## Decision

Ship split Debian packages with shared versioning. CPack component install mirrors the split.

## Consequences

Slightly more packaging metadata; clearer dependency surfaces for ROS versus API-only hosts.
