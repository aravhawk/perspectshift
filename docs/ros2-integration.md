# ROS 2 integration

Packages:

- `perceptshift_msgs` — messages and services
- `perceptshift_ros` — lifecycle component wrapping `libperceptshift_core`
- `perceptshift_bringup` — launch/config (no bundled models)

## Launch

```bash
ros2 launch perceptshift_bringup runtime.launch.py bundle_path:=/path/to/bundle
ros2 launch perceptshift_bringup composable.launch.py bundle_path:=/path/to/bundle
ros2 launch perceptshift_bringup with_lifecycle_manager.launch.py bundle_path:=/path/to/bundle
```

## Topics (node-relative defaults)

- `~/classifications`, `~/detections`
- `~/health`, `~/profiles`, `~/traces`, `~/switches`
- `~/control_hold_request` — advisory hold/degrade request, not an actuator command

## QoS

- Image input: SensorDataQoS (best effort, volatile)
- Health/profile/hold: reliable, transient local where appropriate
- Traces: best effort, bounded depth

## Mutation services

Disabled unless `enable_mutation_services:=true`. The ROS graph is not assumed authenticated; prefer SROS 2 for hostile networks.
