# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | Yes       |

## Reporting a vulnerability

Do not open public issues for security vulnerabilities.

If this repository has GitHub private vulnerability reporting enabled, use that
channel. Otherwise, contact the repository maintainers through the private
security contact listed in the repository settings when available.

Please include:

- affected version and commit;
- reproduction steps;
- impact assessment;
- whether a fix is already known.

## Disclosure expectations

- Acknowledge receipt when a private channel exists.
- Coordinate disclosure timelines based on severity and fix readiness.
- Do not require public credit as a condition of reporting.

## Scope notes

PerceptShift is a local-first, deadline-aware inference system. It publishes a
control-hold request when no eligible profile is available. It does not
directly command actuators by default and is not a functional-safety certified
component.
