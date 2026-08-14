# CLI reference

Canonical command: `perceptshift`.

Common command groups (see `--help` on your installed version for authoritative flags):

| Command | Purpose |
|---------|---------|
| `perceptshift version` | Print synchronized product version |
| `perceptshift doctor` | Host and dependency diagnostics (`--json` available) |
| `perceptshift inspect model` | Inspect a user-supplied ONNX model |
| `perceptshift dataset validate` | Validate dataset manifests |
| `perceptshift forge run` | Offline candidate build/certify/bundle |
| `perceptshift bundle verify` | Verify profile bundle integrity |
| `perceptshift bundle sign` | Optional Ed25519 signing |
| `perceptshift api serve` | Local operational API |
| `perceptshift runtime` | Standalone runtime entry (non-ROS) |

Do not paste fabricated command output into runbooks. Capture real output from your host when documenting deployments.
