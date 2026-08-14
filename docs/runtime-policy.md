# Runtime policy

Policy fields live in runtime config and a safe mutable subset via `UpdateRuntimePolicy`.

## Hard gates (examples)

- Bundle integrity/signature policy
- Maximum RSS / minimum available memory
- Stale input age
- No eligible profile → fail-closed + control-hold request

## Soft / hysteresis controls

- `deadline_ms`
- `minimum_dwell_ms`
- promotion/demotion confirmation frames
- deadline-miss window/threshold
- latency quantile + margin + MAD multiplier
- confidence escalation threshold (when enabled)

## Pseudocode (conceptual)

```
for each frame:
  drop if invalid or stale
  estimate latency for eligible profiles
  if active profile misses deadline policy: consider demotion
  if higher-quality profile fits envelope: consider promotion after hysteresis
  if no eligible profile: request control-hold and fail closed
```

Exact reason codes are published on health and switch events.
