# Security

See also [threat-model.md](threat-model.md) and [privacy.md](privacy.md).

## Deployment defaults

- API on loopback
- Mutation token via protected credentials
- Bundle integrity verification before load
- Optional Ed25519 signatures
- ROS mutation services off by default
- Systemd hardening (see `deploy/systemd/README.md`)

## Model trust

User-supplied ONNX models are untrusted input. Inspection and session creation run in isolated workers with timeouts and limits. Isolation is defense in depth, not a complete sandbox.

## Vulnerability reporting

Follow [SECURITY.md](../SECURITY.md). Do not file public issues for vulnerabilities.
