# Operations

## Health monitoring

Watch `~/health`, diagnostics, and API `/health`. Reason codes explain degraded and fail-closed states.

## Control-hold

Treat `ControlHoldRequest` as an upstream advisory. Integrate with your own control stack; PerceptShift does not command motors by default.

## Upgrades

1. Stop services.
2. Install new packages.
3. Re-verify bundles if format versions change.
4. Start services; confirm doctor/health.

## Uninstall

```bash
./scripts/uninstall-local.sh          # preserves user data
./scripts/uninstall-local.sh --purge  # removes managed state
```
