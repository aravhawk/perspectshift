# Threat model

Methodology: STRIDE-oriented asset and trust-boundary analysis.

## Assets

Model files and external data, profile bundles, signing keys, API mutation token, runtime policy, benchmark/evaluation integrity, local datasets, ROS control-hold signal, runtime availability, report provenance, operator audit records.

## Trust boundaries

User-supplied model/dataset → forge; bundle import → runtime; forge → C++ workers; ROS graph; local API; browser console; filesystem; systemd/container; optional hardware telemetry providers.

## Selected threats

| Threat | Preconditions | Impact | Mitigation | Residual risk | Verification |
|--------|---------------|--------|------------|---------------|--------------|
| Malicious ONNX resource exhaustion | Attacker-controlled model | DoS / OOM | Worker limits, timeouts, size caps | Kernel/shared-host exhaustion | Worker timeout/memory tests |
| Path traversal / symlink escape | Crafted paths/links | Read/write outside roots | Canonicalization, `O_NOFOLLOW`, root allowlists | Kernel TOCTOU races | Security path tests |
| Tampered bundle | Writable FS / supply chain | Wrong model execution | SHA-256 manifest, optional signature | Stolen signing key | Tamper/wrong-key tests |
| API exposure beyond loopback | Misconfiguration / proxy | Unauthorized control | Loopback default, origin policy, token auth | Compromised host local user | API bind/auth tests |
| Unauthorized policy/pin | Open ROS graph | Unexpected switches | Mutation services disabled by default; rate limits | Unauthenticated ROS peers | Service validation tests |
| Secret leakage | Logging/debug | Credential theft | Redaction, no secrets in repo, credential files | Operator misconfiguration | Canary secret tests |
| Stale-data replay | Old frames accepted | Stale perception | Source age gates, fail-closed on stale | Clock sync errors | Stale input tests |
| Compromised dependency | Upstream CVE | RCE/supply chain | Dependency review, CodeQL, SBOM, container scan | Zero-days | CI supply-chain workflows |

## Out of scope

Physical attacker with root on the robot computer; functional-safety certification; adversarial ML robustness guarantees.
