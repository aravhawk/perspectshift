#!/usr/bin/env python3
"""Lifecycle configure/activate + fixture inference against the installed runtime."""

from __future__ import annotations

import subprocess
import time

import rclpy
from lifecycle_msgs.msg import Transition
from lifecycle_msgs.srv import ChangeState, GetState
from perceptshift_msgs.msg import ClassificationArray
from rclpy.node import Node
from sensor_msgs.msg import Image


def _dump_runtime() -> None:
    subprocess.run(
        [
            "bash",
            "-lc",
            "echo '--- ros-runtime.log ---'; tail -200 /tmp/ros-runtime.log; "
            "echo '--- ros2 node list ---'; ros2 node list; "
            "echo '--- ros2 service list ---'; ros2 service list",
        ],
        check=False,
    )


def main() -> None:
    rclpy.init()
    node = Node("ps_pkg_accept")
    try:
        deadline = time.time() + 60
        state_cli = node.create_client(GetState, "/perceptshift_runtime/get_state")
        change_cli = node.create_client(ChangeState, "/perceptshift_runtime/change_state")
        while time.time() < deadline and not state_cli.wait_for_service(timeout_sec=1.0):
            pass
        if not state_cli.service_is_ready():
            _dump_runtime()
            raise AssertionError("runtime get_state unavailable")

        def get_label() -> str:
            fut = state_cli.call_async(GetState.Request())
            rclpy.spin_until_future_complete(node, fut, timeout_sec=5.0)
            return fut.result().current_state.label if fut.result() else ""

        label = get_label()
        if label in ("unconfigured", "unknown", ""):
            change_cli.wait_for_service(timeout_sec=10)
            req = ChangeState.Request()
            req.transition.id = Transition.TRANSITION_CONFIGURE
            req.transition.label = "configure"
            fut = change_cli.call_async(req)
            rclpy.spin_until_future_complete(node, fut, timeout_sec=120)
            if not (fut.result() and fut.result().success):
                _dump_runtime()
                raise AssertionError(f"configure failed: {fut.result()}")
            label = get_label()
        if label == "inactive":
            req = ChangeState.Request()
            req.transition.id = Transition.TRANSITION_ACTIVATE
            req.transition.label = "activate"
            fut = change_cli.call_async(req)
            rclpy.spin_until_future_complete(node, fut, timeout_sec=60)
            if not (fut.result() and fut.result().success):
                _dump_runtime()
                raise AssertionError(f"activate failed: {fut.result()}")
            label = get_label()
        for _ in range(60):
            if get_label() == "active":
                break
            time.sleep(0.5)
        if get_label() != "active":
            _dump_runtime()
            raise AssertionError(f"expected ACTIVE, got {get_label()}")

        classes: list = []
        node.create_subscription(
            ClassificationArray,
            "/perceptshift_runtime/classifications",
            lambda m: classes.append(m),
            10,
        )
        pub = node.create_publisher(Image, "/camera/image_raw", 10)
        time.sleep(0.5)
        width = height = 8
        img = Image()
        img.height = height
        img.width = width
        img.encoding = "rgb8"
        img.is_bigendian = 0
        img.step = width * 3
        img.data = bytes([10, 20, 30] * (width * height))
        img.header.frame_id = "camera"
        end = time.time() + 45
        while time.time() < end and not classes:
            img.header.stamp = node.get_clock().now().to_msg()
            pub.publish(img)
            rclpy.spin_once(node, timeout_sec=0.2)
        if not classes:
            _dump_runtime()
            raise AssertionError("installed ROS runtime did not produce ClassificationArray")
        if not classes[0].predictions:
            raise AssertionError("empty predictions")
        print("installed_ros_inference_ok seq=", classes[0].sequence_id)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
