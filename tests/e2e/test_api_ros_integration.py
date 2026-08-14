"""API ↔ live ROS bridge integration against a running perceptshift_runtime node."""

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
        from perceptshift_msgs.msg import RuntimeHealth  # noqa: F401
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


def test_api_ros_bridge_connected_status_and_policy() -> None:
    _require_ros_env()
    httpx = pytest.importorskip("httpx")
    import rclpy
    from lifecycle_msgs.msg import Transition
    from rclpy.node import Node

    bundle_root = Path(tempfile.mkdtemp(prefix="ps-api-ros-bundle-"))
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

    runtime_log = tempfile.NamedTemporaryFile(prefix="ps-api-runtime-", suffix=".log", delete=False)
    api_log = tempfile.NamedTemporaryFile(prefix="ps-api-api-", suffix=".log", delete=False)

    runtime = subprocess.Popen(
        [
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
        ],
        env=env,
        stdout=runtime_log,
        stderr=subprocess.STDOUT,
        text=True,
    )

    api_env = env.copy()
    api_env["PERCEPTSHIFT_API_ENABLE_ROS"] = "true"
    api_env["PERCEPTSHIFT_API_MUTATION_TOKEN"] = "e2e-mutation-token"
    api_env["PYTHONPATH"] = ":".join(
        [
            str(ROOT / "python" / "perceptshift_common" / "src"),
            str(ROOT / "python" / "perceptshift_api" / "src"),
            api_env.get("PYTHONPATH", ""),
        ]
    )
    api = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "perceptshift_api",
            "--host",
            "127.0.0.1",
            "--port",
            "8741",
        ],
        env=api_env,
        cwd=str(ROOT / "python" / "perceptshift_api"),
        stdout=api_log,
        stderr=subprocess.STDOUT,
        text=True,
    )

    rclpy.init()
    node = Node("ps_api_ros_e2e")
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

        client = httpx.Client(base_url="http://127.0.0.1:8741", timeout=5.0)
        deadline = time.time() + 45.0
        status = None
        while time.time() < deadline:
            try:
                r = client.get("/api/v1/healthz")
                if r.status_code != 200:
                    time.sleep(0.3)
                    continue
                st = client.get("/api/v1/runtime/status")
                if st.status_code == 200 and st.json().get("connected") is True:
                    status = st.json()
                    break
            except Exception:
                pass
            time.sleep(0.3)
        assert status is not None, "API never reported connected ROS bridge"
        assert status.get("mode") == "ros"

        health = client.get("/api/v1/runtime/health")
        assert health.status_code == 200
        body = health.json()
        assert body.get("state") or body.get("health_state") or body.get("status")

        headers = {"Authorization": "Bearer e2e-mutation-token"}
        patch = client.patch(
            "/api/v1/runtime/policy",
            headers=headers,
            json={"deadline_ms": 420.0},
        )
        assert patch.status_code == 200, patch.text
    finally:
        try:
            node.destroy_node()
        except Exception:
            pass
        try:
            rclpy.shutdown()
        except Exception:
            pass
        for p in (api, runtime):
            p.terminate()
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
                try:
                    p.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
        runtime_log.close()
        api_log.close()
