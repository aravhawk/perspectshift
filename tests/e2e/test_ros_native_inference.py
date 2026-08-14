"""ROS 2 Jazzy native inference integration: Image → RuntimeEngine → topics/services."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from bundle_fixture import write_classification_bundle  # noqa: E402


def _require_ros_env() -> None:
    required = os.environ.get("PERCEPTSHIFT_ROS_E2E_REQUIRED") == "1"

    def _fail_or_skip(msg: str) -> None:
        if required:
            pytest.fail(msg)
        pytest.skip(msg)

    if os.environ.get("ROS_DISTRO") != "jazzy":
        _fail_or_skip(f"ROS_DISTRO must be jazzy (got {os.environ.get('ROS_DISTRO')!r})")
    try:
        import rclpy  # noqa: F401
        from lifecycle_msgs.msg import Transition  # noqa: F401
        from lifecycle_msgs.srv import ChangeState, GetState  # noqa: F401
        from perceptshift_msgs.srv import GetRuntimeStatus  # noqa: F401
        from sensor_msgs.msg import Image  # noqa: F401
    except ImportError as exc:
        _fail_or_skip(f"ROS Python deps unavailable: {exc}")


def _lifecycle_call(node, service: str, transition_id: int, label: str) -> None:
    import rclpy
    from lifecycle_msgs.srv import ChangeState

    client = node.create_client(ChangeState, service)
    assert client.wait_for_service(timeout_sec=30.0), f"missing {service}"
    req = ChangeState.Request()
    req.transition.id = transition_id
    req.transition.label = label
    fut = client.call_async(req)
    rclpy.spin_until_future_complete(node, fut, timeout_sec=60.0)
    assert fut.result() is not None and fut.result().success, f"lifecycle {label} failed"


def _wait_active(node, get_state_svc: str, timeout_s: float = 60.0) -> None:
    import rclpy
    from lifecycle_msgs.srv import GetState

    client = node.create_client(GetState, get_state_svc)
    assert client.wait_for_service(timeout_sec=30.0)
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        fut = client.call_async(GetState.Request())
        rclpy.spin_until_future_complete(node, fut, timeout_sec=5.0)
        if fut.result() and fut.result().current_state.label == "active":
            return
        time.sleep(0.2)
    raise AssertionError("runtime node never reached active")


def test_ros_native_inference_image_to_status() -> None:
    _require_ros_env()
    import rclpy
    from lifecycle_msgs.msg import Transition
    from perceptshift_msgs.msg import ClassificationArray, RuntimeHealth
    from perceptshift_msgs.srv import GetRuntimeStatus
    from rclpy.node import Node
    from sensor_msgs.msg import Image

    bundle_root = Path(tempfile.mkdtemp(prefix="ps-ros-bundle-"))
    write_classification_bundle(bundle_root)

    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = ":".join(
        [
            env.get("LD_LIBRARY_PATH", ""),
            "/opt/perceptshift/lib/perceptshift",
            "/opt/perceptshift/lib",
            "/cache/onnxruntime-linux-aarch64-1.28.0/lib",
            str(ROOT / ".cache/onnxruntime-linux-aarch64-1.28.0/lib"),
        ]
    )
    env["CMAKE_PREFIX_PATH"] = f"/opt/perceptshift:{env.get('CMAKE_PREFIX_PATH', '')}"

    launch_cmd = [
        "ros2",
        "run",
        "perceptshift_ros",
        "perceptshift_runtime_node",
        "--ros-args",
        "-p",
        f"bundle_path:={bundle_root}",
        "-p",
        "image_topic:=/camera/image_raw",
        "-p",
        "task:=image_classification",
        "-p",
        "deadline_ms:=500.0",
        "-p",
        "require_signature:=false",
        "-p",
        "enable_mutation_services:=true",
        "-p",
        "maximum_source_age_ms:=5000.0",
        "-p",
        "telemetry_period_ms:=200",
    ]
    log_file = tempfile.NamedTemporaryFile(prefix="ps-ros-runtime-", suffix=".log", delete=False)
    proc = subprocess.Popen(
        launch_cmd,
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
    )
    classifications: list = []
    rclpy.init()
    node = Node("ps_ros_e2e")
    try:
        time.sleep(2.0)
        _lifecycle_call(
            node,
            "/perceptshift_runtime/change_state",
            Transition.TRANSITION_CONFIGURE,
            "configure",
        )
        _lifecycle_call(
            node,
            "/perceptshift_runtime/change_state",
            Transition.TRANSITION_ACTIVATE,
            "activate",
        )
        _wait_active(node, "/perceptshift_runtime/get_state")

        health_msgs: list = []
        node.create_subscription(
            ClassificationArray,
            "/perceptshift_runtime/classifications",
            lambda m: classifications.append(m),
            10,
        )
        node.create_subscription(
            RuntimeHealth,
            "/perceptshift_runtime/health",
            lambda m: health_msgs.append(m),
            10,
        )

        pub = node.create_publisher(Image, "/camera/image_raw", 10)
        time.sleep(0.5)
        w, h = 8, 8
        img = Image()
        img.height = h
        img.width = w
        img.encoding = "rgb8"
        img.is_bigendian = 0
        img.step = w * 3
        img.data = bytes([10, 20, 30] * (w * h))
        img.header.stamp = node.get_clock().now().to_msg()
        img.header.frame_id = "camera"

        deadline = time.time() + 45.0
        while time.time() < deadline and not classifications:
            img.header.stamp = node.get_clock().now().to_msg()
            pub.publish(img)
            rclpy.spin_once(node, timeout_sec=0.2)

        assert classifications, "expected ClassificationArray from native RuntimeEngine path"
        assert classifications[0].predictions, "classification predictions empty"

        status_cli = node.create_client(GetRuntimeStatus, "/perceptshift_runtime/get_runtime_status")
        assert status_cli.wait_for_service(timeout_sec=10.0)
        fut = status_cli.call_async(GetRuntimeStatus.Request())
        rclpy.spin_until_future_complete(node, fut, timeout_sec=10.0)
        assert fut.result() is not None
        resp = fut.result()
        assert resp.success
        assert resp.active_profile_id
        assert resp.health.eligible_profile_count >= 1
        assert health_msgs or resp.health.health_state >= 0
    finally:
        node.destroy_node()
        rclpy.shutdown()
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                pass
        log_file.close()
        if not classifications:
            try:
                print("--- runtime node log ---")
                print(Path(log_file.name).read_text(encoding="utf-8")[-8000:])
            except Exception:
                pass
