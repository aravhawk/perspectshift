"""Unit tests for RosBridge with mocked rclpy (no live ROS required)."""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace
from typing import Any

import pytest

from perceptshift_api.errors import ApiError
from perceptshift_api.ros_bridge import RosBridge, allow_test_hooks
from perceptshift_api.telemetry import TelemetryHub


class _FakeFuture:
    def __init__(
        self, result: Any = None, *, delay_s: float = 0.0, error: Exception | None = None
    ) -> None:
        self._result = result
        self._error = error
        self._delay_s = delay_s
        self._done = delay_s <= 0.0 and error is None and True
        self._lock = threading.Lock()
        if delay_s > 0:
            self._done = False
            threading.Thread(target=self._complete, daemon=True).start()

    def _complete(self) -> None:
        time.sleep(self._delay_s)
        with self._lock:
            self._done = True

    def done(self) -> bool:
        with self._lock:
            return self._done

    def result(self) -> Any:
        if self._error is not None:
            raise self._error
        return self._result


class _FakeClient:
    def __init__(self, *, ready: bool = True) -> None:
        self._ready = ready
        self.requests: list[Any] = []
        self._response: Any = None
        self._delay_s = 0.0
        self._error: Exception | None = None

    def service_is_ready(self) -> bool:
        return self._ready

    def set_response(
        self, response: Any, *, delay_s: float = 0.0, error: Exception | None = None
    ) -> None:
        self._response = response
        self._delay_s = delay_s
        self._error = error

    def call_async(self, request: Any) -> _FakeFuture:
        self.requests.append(request)
        return _FakeFuture(self._response, delay_s=self._delay_s, error=self._error)


class _SrvType:
    class Request:
        def __init__(self) -> None:
            self.deadline_ms = 0.0
            self.apply_deadline = False
            self.minimum_quality_value = 0.0
            self.apply_minimum_quality = False
            self.confidence_escalation_threshold = 0.0
            self.apply_confidence_threshold = False
            self.minimum_dwell_ms = 0
            self.promotion_confirmation_frames = 0
            self.demotion_confirmation_frames = 0
            self.apply_hysteresis = False
            self.profile_id = ""
            self.duration_seconds = 0
            self.reason = ""
            self.reload_bundle = False


@pytest.fixture
def hub() -> TelemetryHub:
    return TelemetryHub(cache_size=32, queue_size=8, max_clients=4)


def test_allow_test_hooks_under_pytest() -> None:
    assert allow_test_hooks() is True


def test_disabled_bridge_reports_ros_disabled(hub: TelemetryHub) -> None:
    bridge = RosBridge(hub, enable_ros=False)
    bridge.start()
    try:
        status = bridge.runtime_status()
        assert status.connected is False
        assert status.mode == "artifact_store"
        assert status.unavailable["runtime"].reason_code == "ROS_DISABLED"
        with pytest.raises(ApiError) as exc:
            bridge.set_policy({"deadline_ms": 10.0})
        assert exc.value.code == "ROS_UNAVAILABLE"
    finally:
        bridge.stop()


def test_mark_connected_for_tests_does_not_enable_mutations(hub: TelemetryHub) -> None:
    bridge = RosBridge(hub, enable_ros=False)
    bridge.start()
    try:
        bridge.mark_connected_for_tests()
        assert bridge.runtime_status().connected is True
        with pytest.raises(ApiError) as exc:
            bridge.pin_profile("p1")
        assert exc.value.code in {"ROS_UNAVAILABLE", "ROS_SERVICE_UNAVAILABLE"}
    finally:
        bridge.stop()


def test_subscription_callbacks_update_last_known_state(hub: TelemetryHub) -> None:
    bridge = RosBridge(hub, enable_ros=False, stale_after_s=30.0)
    bridge.start()
    published: list[tuple[str, dict[str, Any]]] = []
    bridge.set_loop_publish(lambda et, payload, trace_id=None: published.append((et, payload)))
    bridge.mark_connected_for_tests()

    health = SimpleNamespace(
        health_state=1,
        reason_code="ok",
        active_profile_id="profile-a",
        control_hold_requested=False,
        available_memory_bytes=1024,
        primary_temperature_valid=True,
        primary_temperature_celsius=41.5,
        throttling_valid=True,
        throttling=False,
        source_stale=False,
        trace_id="t1",
    )
    bridge._on_health(health)
    status = bridge.runtime_status()
    assert status.active_profile_id == "profile-a"
    assert status.source_freshness == "fresh"
    rh = bridge.runtime_health()
    assert rh.state == "healthy"
    assert rh.temperature_c == 41.5
    assert any(et == "runtime_health" for et, _ in published)

    profile = SimpleNamespace(
        profile_id="profile-a",
        label="A",
        lifecycle_state=3,
        eligible=True,
        rejection_reason_codes=[],
        certified_quality_metric="numeric_equivalence",
        certified_quality_value=0.99,
        recent_p99_ms=4.5,
        predicted_latency_bound_ms=8.0,
        peak_rss_attestation_bytes=2048,
        provider_summary="CPUExecutionProvider",
        active=True,
        manual_pin_active=False,
    )
    bridge._on_profile(profile)
    listed = bridge.list_profiles()
    assert len(listed) == 1
    assert listed[0].active is True
    assert listed[0].online_p99_ms == 4.5

    hold = SimpleNamespace(
        request_active=True,
        reason_code="fail_closed",
        summary="hold",
        trace_id="t2",
    )
    bridge._on_control_hold(hold)
    assert bridge.runtime_status().control_hold is True
    bridge.stop()


def test_policy_mutation_waits_for_service_response(hub: TelemetryHub) -> None:
    bridge = RosBridge(hub, enable_ros=False, service_timeout_s=1.0)
    bridge.start()
    bridge.mark_connected_for_tests()
    bridge._srv_types = {
        "policy": _SrvType,
        "pin": _SrvType,
        "clear_pin": _SrvType,
        "recovery": _SrvType,
        "status": _SrvType,
    }
    client = _FakeClient(ready=True)
    client.set_response(SimpleNamespace(accepted=True, error_code="", error_message=""))
    bridge._clients = {"policy": client, "status": client}

    updated = bridge.set_policy({"deadline_ms": 12.5})
    assert updated.deadline_ms == 12.5
    assert updated.source == "operator"
    assert len(client.requests) == 1
    assert client.requests[0].apply_deadline is True
    assert client.requests[0].deadline_ms == 12.5
    bridge.stop()


def test_policy_timeout_maps_to_api_error(hub: TelemetryHub) -> None:
    bridge = RosBridge(hub, enable_ros=False, service_timeout_s=0.05)
    bridge.start()
    bridge.mark_connected_for_tests()
    bridge._srv_types = {"policy": _SrvType}
    client = _FakeClient(ready=True)
    client.set_response(SimpleNamespace(accepted=True), delay_s=1.0)
    bridge._clients = {"policy": client}

    with pytest.raises(ApiError) as exc:
        bridge.set_policy({"deadline_ms": 9.0})
    assert exc.value.code == "ROS_TIMEOUT"
    assert bridge.runtime_policy().deadline_ms is None
    bridge.stop()


def test_rejected_pin_does_not_mutate_local_state(hub: TelemetryHub) -> None:
    bridge = RosBridge(hub, enable_ros=False)
    bridge.start()
    bridge.mark_connected_for_tests()
    bridge._srv_types = {"pin": _SrvType}
    client = _FakeClient(ready=True)
    client.set_response(
        SimpleNamespace(
            accepted=False, error_code="no_eligible_profile", error_message="cannot pin"
        )
    )
    bridge._clients = {"pin": client}

    with pytest.raises(ApiError) as exc:
        bridge.pin_profile("missing")
    assert exc.value.code == "ROS_SERVICE_REJECTED"
    assert bridge.runtime_policy().pinned_profile_id is None
    bridge.stop()


def test_shutdown_joins_executor_thread(hub: TelemetryHub) -> None:
    bridge = RosBridge(hub, enable_ros=False)
    bridge.start()
    # No executor thread when ROS disabled.
    bridge.stop()
    assert bridge._thread is None


def test_service_not_ready_fail_closed(hub: TelemetryHub) -> None:
    bridge = RosBridge(hub, enable_ros=False)
    bridge.start()
    bridge.mark_connected_for_tests()
    bridge._srv_types = {"recovery": _SrvType}
    bridge._clients = {"recovery": _FakeClient(ready=False)}
    with pytest.raises(ApiError) as exc:
        bridge.recovery("clear_control_hold")
    assert exc.value.code == "ROS_SERVICE_UNAVAILABLE"
    bridge.stop()
