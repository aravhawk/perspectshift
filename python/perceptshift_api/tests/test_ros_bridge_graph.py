"""Real ROS graph integration tests.

Gated on ROS_DISTRO=jazzy plus importable rclpy and perceptshift_msgs.
When unavailable, tests are skipped with an explicit UNAVAILABLE reason
(not a fake PASS of ROS connectivity).
"""

from __future__ import annotations

import os
import time

import pytest

from perceptshift_api.ros_bridge import RosBridge
from perceptshift_api.telemetry import TelemetryHub

ROS_DISTRO = os.environ.get("ROS_DISTRO", "")
_UNAVAILABLE_REASONS: list[str] = []

if ROS_DISTRO != "jazzy":
    _UNAVAILABLE_REASONS.append(f"ROS_DISTRO={ROS_DISTRO!r} (need jazzy)")

try:
    import rclpy  # type: ignore[import-not-found]
except ImportError:
    rclpy = None  # type: ignore[assignment]
    _UNAVAILABLE_REASONS.append("rclpy_not_importable")

try:
    from perceptshift_msgs.msg import RuntimeHealth  # type: ignore[import-not-found]
    from perceptshift_msgs.srv import GetRuntimeStatus  # type: ignore[import-not-found]
except ImportError:
    RuntimeHealth = None  # type: ignore[assignment,misc]
    GetRuntimeStatus = None  # type: ignore[assignment,misc]
    _UNAVAILABLE_REASONS.append("perceptshift_msgs_not_importable")

pytestmark = pytest.mark.skipif(
    bool(_UNAVAILABLE_REASONS),
    reason="UNAVAILABLE: " + "; ".join(_UNAVAILABLE_REASONS) if _UNAVAILABLE_REASONS else "",
)


@pytest.fixture
def ros_context():
    assert rclpy is not None
    owned = False
    if not rclpy.ok():
        rclpy.init(args=None)
        owned = True
    try:
        yield
    finally:
        if owned and rclpy.ok():
            rclpy.shutdown()


def test_bridge_connects_when_runtime_status_service_present(ros_context, tmp_path) -> None:
    """Spin a minimal status service and prove the bridge marks connected."""
    from rclpy.executors import MultiThreadedExecutor
    from rclpy.node import Node

    assert GetRuntimeStatus is not None
    assert RuntimeHealth is not None

    server_node = Node("perceptshift_runtime")

    def handle_status(_req, response):
        response.success = True
        response.active_profile_id = "fixture-profile"
        response.bundle_id = "fixture"
        response.policy_summary = "test"
        response.policy_hash = "hash"
        response.health.health_state = RuntimeHealth.HEALTH_OK
        response.health.reason_code = "fixture_ok"
        response.health.active_profile_id = "fixture-profile"
        response.error_code = ""
        response.error_message = ""
        return response

    server_node.create_service(GetRuntimeStatus, "~/get_runtime_status", handle_status)
    executor = MultiThreadedExecutor()
    executor.add_node(server_node)
    spin_stop = False

    def spin():
        while not spin_stop:
            executor.spin_once(timeout_sec=0.05)

    import threading

    thread = threading.Thread(target=spin, daemon=True)
    thread.start()

    hub = TelemetryHub()
    bridge = RosBridge(
        hub, enable_ros=True, service_timeout_s=2.0, runtime_node="perceptshift_runtime"
    )
    bridge.start()
    try:
        deadline = time.time() + 10.0
        while time.time() < deadline and not bridge.state.connected:
            time.sleep(0.1)
        assert bridge.state.connected is True, (
            f"bridge did not connect; reason={bridge.state.reason_code} message={bridge.state.message}"
        )
        status = bridge.runtime_status()
        assert status.mode == "ros"
        assert status.connected is True
    finally:
        bridge.stop()
        spin_stop = True
        thread.join(timeout=2.0)
        executor.remove_node(server_node)
        server_node.destroy_node()


def test_bridge_reports_absent_graph_without_runtime(ros_context) -> None:
    hub = TelemetryHub()
    bridge = RosBridge(
        hub,
        enable_ros=True,
        service_timeout_s=0.5,
        runtime_node="perceptshift_runtime_absent_fixture",
    )
    bridge.start()
    try:
        time.sleep(0.8)
        status = bridge.runtime_status()
        assert status.connected is False
        assert status.unavailable["runtime"].reason_code == "ROS_GRAPH_ABSENT"
    finally:
        bridge.stop()
        assert bridge._thread is None or not bridge._thread.is_alive()
