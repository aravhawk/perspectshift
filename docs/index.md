# PerceptShift documentation

PerceptShift is a local-first, **deadline-aware** adaptive inference platform for Arm64 ROS 2 systems. It profiles, certifies, and switches among quality-attested ONNX Runtime execution profiles.

## Start here

- [Quickstart](quickstart.md)
- [Architecture](architecture.md)
- [Installation](installation.md)
- [Limitations](limitations.md)
- [Threat model](threat-model.md)

## Operator guides

- [Operator workflow](operator-workflow.md)
- [CLI reference](cli-reference.md)
- [Configuration reference](configuration-reference.md)
- [Runtime policy](runtime-policy.md)
- [ROS 2 integration](ros2-integration.md)
- [Deployment](deployment.md)
- [Operations](operations.md)
- [Troubleshooting](troubleshooting.md)

## Engineering

- [Supported platforms](supported-platforms.md)
- [Profile bundle format](profile-bundle-format.md)
- [Model adapters](model-adapters.md)
- [Dataset formats](dataset-formats.md)
- [Quantization](quantization.md)
- [Benchmarking methodology](benchmarking-methodology.md)
- [Quality certification](quality-certification.md)
- [API reference](api-reference.md)
- [Console](console.md)
- [Security](security.md)
- [Privacy](privacy.md)
- [Performance tuning](performance-tuning.md)
- [Development](development.md)
- [Testing](testing.md)
- [Release process](release-process.md)

## Safety language

PerceptShift is a soft real-time, deadline-aware inference system. It is not a hard real-time scheduler, not safety-certified, and does not command actuators by default. When no eligible profile is available it publishes a **control-hold request** and enters a **fail-closed** inference posture.
