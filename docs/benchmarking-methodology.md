# Benchmarking methodology

Benchmarks measure the production inference path on the target host. Do not invent numbers.

## Required practices

- Stabilize thermal state; record governor/frequency when available.
- Distinguish cold versus warm starts.
- Keep calibration and evaluation data separate.
- Randomize candidate order; repeat trials; discard invalid trials with reason codes.
- Report p99 and confidence intervals from raw samples.
- Record power only when a physical sensor/provider is available; otherwise mark unavailable.
- Store raw artifacts under the run directory for reproduction.

## Prohibited claims

- No cross-hardware speedup claims without context.
- No QEMU performance claims as native evidence.
- No fabricated before/after marketing numbers.
