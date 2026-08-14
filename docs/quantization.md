# Quantization

Forge may produce quantized candidates using supported ONNX Runtime tooling on user-provided calibration data.

Rules:

- Calibration and evaluation sets must remain separated.
- Quantized candidates are certified only when quality and deadline gates pass on measured results.
- Provider evidence (CPU/XNNPACK) is recorded truthfully; unavailable providers are marked unavailable.
