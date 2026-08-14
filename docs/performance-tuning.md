# Performance tuning

- Re-measure on the deployment host; do not copy latency numbers across boards.
- Prefer XNNPACK on Arm64 when certified for the profile.
- Keep latest-only queue depth at 1 unless you have a measured reason.
- Warm profiles at configure; account for cold-start separately.
- Thread affinity and realtime priority are opt-in and may be unavailable.

Tuning changes that affect eligibility must be re-certified when quality or latency envelopes change.
