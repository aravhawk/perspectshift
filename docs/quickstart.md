# Quickstart

PerceptShift does **not** ship models, calibration data, evaluation sets, bags, or precomputed benchmarks. Replace the placeholder paths below with your own licensed inputs.

```bash
perceptshift doctor
perceptshift inspect model --model /path/to/model.onnx
perceptshift dataset validate --manifest /path/to/evaluation.json
perceptshift forge run --config /path/to/forge.yaml
perceptshift bundle verify --bundle /path/to/generated/bundle
ros2 launch perceptshift_bringup runtime.launch.py bundle_path:=/path/to/generated/bundle
```

## What success looks like

- `doctor` reports host capabilities and unavailable telemetry with reason codes.
- `forge run` writes measured artifacts and a certified bundle only when gates pass.
- `bundle verify` validates digests (and signature when configured).
- ROS launch requires `bundle_path`; configure fails if the path is missing.

## Safety reminder

The runtime is deadline-aware and soft real-time. It may publish a control-hold request; it does not claim an emergency stop or actuator authority.
