# Limitations

Intrinsic product limitations:

- Soft real-time / deadline-aware only — not a hard real-time guarantee.
- ONNX Runtime CPU/XNNPACK only in the supported production path.
- Task adapters cover documented layouts; not every export variant.
- Adapter confidence is not correctness.
- Offline-attested quality may not cover deployment distribution shift.
- No direct actuator acknowledgment unless integrated externally.
- Runtime inference calls may not be cancellable safely mid-execution.
- Power telemetry unavailable without a physical sensor/provider.
- Provider assignment observability has limits imposed by ORT.
- Hardware-specific results are not universally portable.
- Not a safety-certified or functional-safety component.

When a capability is unavailable, PerceptShift exposes an explicit reason code rather than inventing a value.
