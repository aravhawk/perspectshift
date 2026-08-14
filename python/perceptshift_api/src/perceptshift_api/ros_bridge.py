"""Optional ROS bridge with real rclpy wiring when available."""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from perceptshift_api.errors import ApiError
from perceptshift_api.schemas import (
    ProfileDetail,
    ProfileSummary,
    RuntimeHealth,
    RuntimePolicy,
    RuntimeStatus,
    UnavailableField,
)
from perceptshift_api.telemetry import TelemetryHub

logger = logging.getLogger(__name__)

# Default absolute topic/service names for node `perceptshift_runtime` (see bringup).
DEFAULT_RUNTIME_NODE = "perceptshift_runtime"

HEALTH_STATE_NAMES = {
    0: "unknown",
    1: "healthy",
    2: "degraded",
    3: "fail_closed",
    4: "recovering",
    5: "error",
}

LIFECYCLE_STATE_NAMES = {
    0: "unloaded",
    1: "loaded",
    2: "warmed",
    3: "active",
    4: "ineligible",
    5: "failed",
}

SWITCH_REASON_NAMES = {
    0: "startup",
    1: "deadline",
    2: "quality",
    3: "resource",
    4: "confidence",
    5: "manual_pin",
    6: "recovery",
    7: "fail_closed",
    8: "policy",
}


def _utc_now() -> datetime:
    return datetime.now(UTC)


def allow_test_hooks() -> bool:
    """Gate test-only bridge hooks. Never exposed via production API routes."""
    if os.environ.get("PERCEPTSHIFT_API_ALLOW_TEST_HOOKS") == "1":
        return True
    return "pytest" in sys.modules


@dataclass
class RosBridgeState:
    available: bool = False
    reason_code: str = "ROS_UNAVAILABLE"
    message: str = "ROS bridge is not connected"
    connected: bool = False
    active_profile_id: str | None = None
    pinned_profile_id: str | None = None
    control_hold: bool = False
    deadline_ms: float | None = None
    health_state: str = "unavailable"
    reason_codes: list[str] = field(default_factory=lambda: ["ROS_UNAVAILABLE"])
    profiles: dict[str, ProfileSummary] = field(default_factory=dict)
    policy: RuntimePolicy = field(default_factory=RuntimePolicy)
    last_health_at: datetime | None = None
    last_profile_at: datetime | None = None
    last_switch_at: datetime | None = None
    last_trace_at: datetime | None = None
    last_hold_at: datetime | None = None
    last_status_at: datetime | None = None
    memory_headroom_bytes: int | None = None
    temperature_c: float | None = None
    throttling: bool | None = None
    mode: str = "artifact_store"


class RosBridge:
    """Thread-safe ROS telemetry bridge.

    When rclpy is absent or enable_ros is false, the bridge reports
    graceful unavailability and the API remains healthy in artifact-store mode.
    """

    def __init__(
        self,
        hub: TelemetryHub,
        *,
        enable_ros: bool = True,
        service_timeout_s: float = 2.0,
        stale_after_s: float = 5.0,
        runtime_node: str = DEFAULT_RUNTIME_NODE,
        pin_duration_seconds: int = 900,
    ) -> None:
        self._hub = hub
        self._enable_ros = enable_ros
        self._service_timeout_s = service_timeout_s
        self._stale_after_s = stale_after_s
        self._runtime_node = runtime_node.strip().strip("/") or DEFAULT_RUNTIME_NODE
        self._pin_duration_seconds = pin_duration_seconds
        self._state = RosBridgeState()
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._loop_publish: Callable[..., None] | None = None
        self._ros_client_ready = False
        self._rclpy: Any = None
        self._node: Any = None
        self._executor: Any = None
        self._clients: dict[str, Any] = {}
        self._subs: list[Any] = []
        self._graph_seen = False
        self._msg_types: dict[str, Any] = {}
        self._srv_types: dict[str, Any] = {}

    @property
    def state(self) -> RosBridgeState:
        with self._lock:
            return self._state

    def set_loop_publish(self, callback: Callable[..., None] | None) -> None:
        """Register a thread-safe TelemetryHub publisher (from the asyncio loop)."""
        self._loop_publish = callback

    def start(self) -> None:
        if not self._enable_ros:
            with self._lock:
                self._state = RosBridgeState(
                    available=False,
                    reason_code="ROS_DISABLED",
                    message="ROS bridge disabled; running in artifact-store-only mode",
                    mode="artifact_store",
                    health_state="artifact_store",
                    reason_codes=["ROS_DISABLED"],
                )
            return

        try:
            import rclpy  # type: ignore[import-not-found]
        except ImportError:
            with self._lock:
                self._state = RosBridgeState(
                    available=False,
                    reason_code="RCLPY_MISSING",
                    message="rclpy is not installed; artifact-store-only mode is active",
                    mode="artifact_store",
                    health_state="artifact_store",
                    reason_codes=["RCLPY_MISSING"],
                )
            logger.info("rclpy unavailable; API continuing in artifact-store mode")
            return

        try:
            from perceptshift_msgs.msg import (  # type: ignore[import-not-found]
                ControlHoldRequest,
                InferenceTrace,
                ProfileState,
                SwitchEvent,
            )
            from perceptshift_msgs.msg import (
                RuntimeHealth as RosRuntimeHealth,
            )
            from perceptshift_msgs.srv import (  # type: ignore[import-not-found]
                ClearProfilePin,
                GetRuntimeStatus,
                PinProfile,
                RequestRecovery,
                UpdateRuntimePolicy,
            )
        except ImportError:
            with self._lock:
                self._state = RosBridgeState(
                    available=False,
                    reason_code="PERCEPTSHIFT_MSGS_MISSING",
                    message="perceptshift_msgs is not importable; artifact-store-only mode is active",
                    mode="artifact_store",
                    health_state="artifact_store",
                    reason_codes=["PERCEPTSHIFT_MSGS_MISSING"],
                )
            logger.info("perceptshift_msgs unavailable; API continuing in artifact-store mode")
            return

        self._msg_types = {
            "health": RosRuntimeHealth,
            "profiles": ProfileState,
            "switches": SwitchEvent,
            "traces": InferenceTrace,
            "hold": ControlHoldRequest,
        }
        self._srv_types = {
            "status": GetRuntimeStatus,
            "policy": UpdateRuntimePolicy,
            "pin": PinProfile,
            "clear_pin": ClearProfilePin,
            "recovery": RequestRecovery,
        }
        self._rclpy = rclpy

        with self._lock:
            self._state = RosBridgeState(
                available=True,
                reason_code="ROS_GRAPH_ABSENT",
                message="Waiting for ROS graph",
                connected=False,
                mode="ros",
                health_state="degraded",
                reason_codes=["ROS_GRAPH_ABSENT"],
            )
        self._stop.clear()
        self._thread = threading.Thread(target=self._executor_loop, name="ros-bridge", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        self._thread = None
        with self._lock:
            if self._state.mode == "ros":
                self._state.connected = False
                self._state.reason_code = "ROS_SHUTDOWN"
                self._state.message = "ROS bridge shut down"
                self._ros_client_ready = False

    def _topic(self, suffix: str) -> str:
        return f"/{self._runtime_node}/{suffix}"

    def _service(self, suffix: str) -> str:
        return f"/{self._runtime_node}/{suffix}"

    def _executor_loop(self) -> None:
        assert self._rclpy is not None
        rclpy = self._rclpy
        context_owned = False
        try:
            if not rclpy.ok():
                rclpy.init(args=None)
                context_owned = True

            from rclpy.executors import SingleThreadedExecutor  # type: ignore[import-not-found]
            from rclpy.node import Node  # type: ignore[import-not-found]
            from rclpy.qos import (  # type: ignore[import-not-found]
                DurabilityPolicy,
                HistoryPolicy,
                QoSProfile,
                ReliabilityPolicy,
            )

            node = Node("perceptshift_api_bridge")
            self._node = node

            reliable_tl = QoSProfile(
                history=HistoryPolicy.KEEP_LAST,
                depth=10,
                reliability=ReliabilityPolicy.RELIABLE,
                durability=DurabilityPolicy.TRANSIENT_LOCAL,
            )
            best_effort = QoSProfile(
                history=HistoryPolicy.KEEP_LAST,
                depth=20,
                reliability=ReliabilityPolicy.BEST_EFFORT,
                durability=DurabilityPolicy.VOLATILE,
            )

            self._subs = [
                node.create_subscription(
                    self._msg_types["health"],
                    self._topic("health"),
                    self._on_health,
                    reliable_tl,
                ),
                node.create_subscription(
                    self._msg_types["profiles"],
                    self._topic("profiles"),
                    self._on_profile,
                    reliable_tl,
                ),
                node.create_subscription(
                    self._msg_types["switches"],
                    self._topic("switches"),
                    self._on_switch,
                    reliable_tl,
                ),
                node.create_subscription(
                    self._msg_types["traces"],
                    self._topic("traces"),
                    self._on_trace,
                    best_effort,
                ),
                node.create_subscription(
                    self._msg_types["hold"],
                    self._topic("control_hold_request"),
                    self._on_control_hold,
                    reliable_tl,
                ),
            ]

            self._clients = {
                "status": node.create_client(
                    self._srv_types["status"], self._service("get_runtime_status")
                ),
                "policy": node.create_client(
                    self._srv_types["policy"], self._service("update_runtime_policy")
                ),
                "pin": node.create_client(self._srv_types["pin"], self._service("pin_profile")),
                "clear_pin": node.create_client(
                    self._srv_types["clear_pin"], self._service("clear_profile_pin")
                ),
                "recovery": node.create_client(
                    self._srv_types["recovery"], self._service("request_recovery")
                ),
            }

            executor = SingleThreadedExecutor()
            executor.add_node(node)
            self._executor = executor

            while not self._stop.is_set():
                executor.spin_once(timeout_sec=0.1)
                self._refresh_graph_state()
        except Exception:
            logger.exception("ROS bridge executor failed")
            with self._lock:
                self._state.connected = False
                self._state.reason_code = "ROS_BRIDGE_ERROR"
                self._state.message = "ROS bridge executor failed"
                self._state.reason_codes = ["ROS_BRIDGE_ERROR"]
                self._ros_client_ready = False
        finally:
            self._teardown_ros(context_owned=context_owned)

    def _teardown_ros(self, *, context_owned: bool) -> None:
        try:
            if self._executor is not None and self._node is not None:
                try:
                    self._executor.remove_node(self._node)
                except Exception as exc:  # noqa: BLE001 — best-effort shutdown
                    logger.debug("remove_node during shutdown: %s", exc)
            if self._node is not None:
                try:
                    self._node.destroy_node()
                except Exception as exc:  # noqa: BLE001 — best-effort shutdown
                    logger.debug("destroy_node during shutdown: %s", exc)
            self._node = None
            self._executor = None
            self._clients = {}
            self._subs = []
            self._ros_client_ready = False
            if context_owned and self._rclpy is not None:
                try:
                    if self._rclpy.ok():
                        self._rclpy.shutdown()
                except Exception:
                    logger.debug("rclpy shutdown raised", exc_info=True)
        except Exception:
            logger.exception("ROS bridge teardown failed")

    def _refresh_graph_state(self) -> None:
        status_client = self._clients.get("status")
        ready = bool(status_client is not None and status_client.service_is_ready())
        mutation_ready = all(
            client.service_is_ready()
            for name, client in self._clients.items()
            if name != "status" and client is not None
        )
        # Status client alone is enough to mark connected for reads; mutations check per-client.
        with self._lock:
            self._ros_client_ready = ready
            if ready:
                self._graph_seen = True
                if not self._state.connected:
                    self._publish_event(
                        "connection_status",
                        {"status": "ros_connected", "runtime_node": self._runtime_node},
                    )
                self._state.connected = True
                self._state.available = True
                self._state.mode = "ros"
                self._state.reason_code = "OK"
                self._state.message = "Connected to ROS runtime graph"
                if (
                    self._state.health_state in {"unavailable", "artifact_store", "degraded"}
                    and (
                        "ROS_GRAPH_ABSENT" in self._state.reason_codes
                        or self._state.reason_codes == ["ROS_GRAPH_ABSENT"]
                    )
                    and self._state.last_health_at is None
                ):
                    # Keep last health if we already received messages; otherwise degraded pending.
                    self._state.health_state = "degraded"
                    self._state.reason_codes = ["ROS_AWAITING_HEALTH"]
                if (
                    not mutation_ready
                    and "MUTATION_SERVICES_ABSENT" not in self._state.reason_codes
                ):
                    # Advisory only; mutation endpoints fail closed until clients are ready.
                    pass
            elif self._graph_seen:
                self._state.connected = False
                self._state.reason_code = "ROS_GRAPH_ABSENT"
                self._state.message = "ROS runtime services disappeared"
                self._state.reason_codes = ["ROS_GRAPH_ABSENT"]
            else:
                self._state.connected = False
                self._state.reason_code = "ROS_GRAPH_ABSENT"
                self._state.message = "ROS graph not detected"
                self._state.reason_codes = ["ROS_GRAPH_ABSENT"]

    def _publish_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        trace_id: str | None = None,
    ) -> None:
        callback = self._loop_publish
        if callback is None:
            return
        try:
            callback(event_type, payload, trace_id=trace_id)
        except Exception:
            logger.debug("telemetry publish failed", exc_info=True)

    def _freshness_label(self, stamp: datetime | None) -> str | None:
        if stamp is None:
            return None
        age = (_utc_now() - stamp).total_seconds()
        if age <= self._stale_after_s:
            return "fresh"
        return "stale"

    def _on_health(self, msg: Any) -> None:
        now = _utc_now()
        state_name = HEALTH_STATE_NAMES.get(int(msg.health_state), "unknown")
        reason = str(msg.reason_code or "") or state_name
        memory = None
        if getattr(msg, "available_memory_bytes", 0):
            memory = int(msg.available_memory_bytes)
        temp = None
        if getattr(msg, "primary_temperature_valid", False):
            temp = float(msg.primary_temperature_celsius)
        throttling = None
        if getattr(msg, "throttling_valid", False):
            throttling = bool(msg.throttling)
        with self._lock:
            self._state.last_health_at = now
            self._state.health_state = state_name
            self._state.reason_codes = [reason] if reason else [state_name]
            self._state.active_profile_id = (
                str(msg.active_profile_id) or self._state.active_profile_id
            )
            self._state.control_hold = bool(msg.control_hold_requested)
            self._state.memory_headroom_bytes = memory
            self._state.temperature_c = temp
            self._state.throttling = throttling
            self._state.connected = True
            self._state.mode = "ros"
            self._state.reason_code = "OK"
            self._state.message = "Receiving runtime health"
        self._publish_event(
            "runtime_health",
            {
                "state": state_name,
                "reason_code": reason,
                "active_profile_id": str(msg.active_profile_id),
                "control_hold": bool(msg.control_hold_requested),
                "source_stale": bool(getattr(msg, "source_stale", False)),
            },
            trace_id=str(getattr(msg, "trace_id", "") or None),
        )

    def _on_profile(self, msg: Any) -> None:
        now = _utc_now()
        profile_id = str(msg.profile_id)
        lifecycle = LIFECYCLE_STATE_NAMES.get(int(msg.lifecycle_state), "unknown")
        summary = ProfileSummary(
            profile_id=profile_id,
            label=str(msg.label) or None,
            state=lifecycle,
            eligible=bool(msg.eligible),
            rejection_reasons=[str(r) for r in list(msg.rejection_reason_codes or [])],
            certified_quality=float(msg.certified_quality_value)
            if msg.certified_quality_metric
            else None,
            certified_p99_ms=None,
            online_p99_ms=float(msg.recent_p99_ms) if msg.recent_p99_ms else None,
            online_bound_ms=float(msg.predicted_latency_bound_ms)
            if msg.predicted_latency_bound_ms
            else None,
            peak_rss_bytes=int(msg.peak_rss_attestation_bytes)
            if msg.peak_rss_attestation_bytes
            else None,
            provider=str(msg.provider_summary) or None,
            active=bool(msg.active),
            pinned=bool(msg.manual_pin_active),
        )
        with self._lock:
            self._state.profiles[profile_id] = summary
            self._state.last_profile_at = now
            if summary.active:
                self._state.active_profile_id = profile_id
            if summary.pinned:
                self._state.pinned_profile_id = profile_id
                self._state.policy.pinned_profile_id = profile_id
            elif self._state.pinned_profile_id == profile_id and not summary.pinned:
                self._state.pinned_profile_id = None
                self._state.policy.pinned_profile_id = None
        self._publish_event(
            "profile_state",
            {
                "profile_id": profile_id,
                "state": lifecycle,
                "active": summary.active,
                "eligible": summary.eligible,
                "pinned": summary.pinned,
            },
        )

    def _on_switch(self, msg: Any) -> None:
        now = _utc_now()
        reason = SWITCH_REASON_NAMES.get(int(msg.reason_code), "unknown")
        with self._lock:
            self._state.last_switch_at = now
            self._state.active_profile_id = str(msg.to_profile_id) or self._state.active_profile_id
        self._publish_event(
            "switch_event",
            {
                "from_profile": str(msg.from_profile_id) or None,
                "to_profile": str(msg.to_profile_id) or None,
                "reason": reason,
                "reason_detail": str(msg.reason_detail),
                "evidence": {"summary": str(msg.evidence_summary)},
                "manual": bool(msg.manual),
                "sequence": int(msg.effective_sequence_id),
            },
            trace_id=str(msg.trace_id) or None,
        )

    def _on_trace(self, msg: Any) -> None:
        now = _utc_now()
        total_ms = float(msg.total_ns) / 1_000_000.0 if msg.total_ns else None
        with self._lock:
            self._state.last_trace_at = now
        self._publish_event(
            "inference_trace_summary",
            {
                "profile_id": str(msg.profile_id),
                "sequence_id": int(msg.sequence_id),
                "total_ms": total_ms,
                "deadline_miss": bool(msg.deadline_missed),
                "frame_dropped": bool(msg.frame_dropped),
                "drop_reason": str(msg.drop_reason) or None,
                "execution_provider_summary": str(msg.execution_provider_summary) or None,
            },
            trace_id=str(msg.trace_id) or None,
        )

    def _on_control_hold(self, msg: Any) -> None:
        now = _utc_now()
        with self._lock:
            self._state.last_hold_at = now
            self._state.control_hold = bool(msg.request_active)
            if msg.reason_code:
                codes = list(self._state.reason_codes)
                reason = str(msg.reason_code)
                if reason not in codes:
                    codes.append(reason)
                self._state.reason_codes = codes
        self._publish_event(
            "control_hold",
            {
                "request_active": bool(msg.request_active),
                "reason_code": str(msg.reason_code),
                "summary": str(msg.summary),
            },
            trace_id=str(msg.trace_id) or None,
        )

    def _require_connected(self) -> None:
        with self._lock:
            connected = self._state.connected
            reason = self._state.reason_code
            message = self._state.message
        if not connected:
            raise ApiError(
                "ROS_UNAVAILABLE",
                message or "ROS runtime is not connected",
                status_code=503,
                retryable=True,
                details={"reason_code": reason},
                remediation="Start the perceptshift_runtime node and ensure the API ROS bridge is enabled",
            )

    def _require_client(self, name: str) -> Any:
        self._require_connected()
        client = self._clients.get(name)
        if client is None or not client.service_is_ready():
            raise ApiError(
                "ROS_SERVICE_UNAVAILABLE",
                f"ROS service client '{name}' is not ready",
                status_code=503,
                retryable=True,
                details={"service": name},
                remediation=(
                    "Ensure mutation services are enabled on the runtime "
                    "(enable_mutation_services:=true) and the graph is discoverable"
                ),
            )
        return client

    def _wait_future(self, future: Any, *, service: str) -> Any:
        deadline = time.monotonic() + self._service_timeout_s
        while not future.done():
            if self._stop.is_set():
                raise ApiError(
                    "ROS_SHUTDOWN",
                    f"ROS bridge shutting down while waiting for '{service}'",
                    status_code=503,
                    retryable=True,
                    details={"service": service},
                )
            if time.monotonic() >= deadline:
                raise ApiError(
                    "ROS_TIMEOUT",
                    f"Timed out waiting for ROS service '{service}'",
                    status_code=504,
                    retryable=True,
                    details={"service": service, "timeout_s": self._service_timeout_s},
                    remediation="Retry; if persistent, inspect runtime node load and DDS discovery",
                )
            time.sleep(0.01)
        try:
            return future.result()
        except Exception as exc:
            raise ApiError(
                "ROS_SERVICE_FAILED",
                f"ROS service '{service}' failed: {exc}",
                status_code=503,
                retryable=True,
                details={"service": service},
            ) from exc

    def _call_service(self, name: str, request: Any) -> Any:
        client = self._require_client(name)
        future = client.call_async(request)
        return self._wait_future(future, service=name)

    def runtime_status(self) -> RuntimeStatus:
        with self._lock:
            s = self._state
            unavailable: dict[str, UnavailableField] = {}
            if not s.connected:
                unavailable["runtime"] = UnavailableField(
                    reason_code=s.reason_code,
                    message=s.message,
                )
            freshness = self._freshness_label(s.last_health_at or s.last_status_at)
            return RuntimeStatus(
                connected=s.connected,
                mode="ros" if s.mode == "ros" and s.available else "artifact_store",
                active_profile_id=s.active_profile_id,
                control_hold=s.control_hold,
                deadline_ms=s.deadline_ms if s.deadline_ms is not None else s.policy.deadline_ms,
                source_freshness=None if not s.connected else freshness,
                unavailable=unavailable,
            )

    def runtime_health(self) -> RuntimeHealth:
        with self._lock:
            s = self._state
            unavailable: dict[str, UnavailableField] = {}
            if not s.connected:
                unavailable["health"] = UnavailableField(
                    reason_code=s.reason_code,
                    message=s.message,
                )
            elif self._freshness_label(s.last_health_at) == "stale":
                unavailable["health"] = UnavailableField(
                    reason_code="ROS_STALE",
                    message="Last health sample exceeded freshness window",
                )
            return RuntimeHealth(
                state=s.health_state,
                reason_codes=list(s.reason_codes),
                memory_headroom_bytes=s.memory_headroom_bytes,
                temperature_c=s.temperature_c,
                throttling=s.throttling,
                control_hold=s.control_hold,
                updated_at=s.last_health_at,
                unavailable=unavailable,
            )

    def runtime_policy(self) -> RuntimePolicy:
        with self._lock:
            return self._state.policy.model_copy(deep=True)

    def list_profiles(self) -> list[ProfileSummary]:
        with self._lock:
            profiles = [p.model_copy(deep=True) for p in self._state.profiles.values()]
            active = self._state.active_profile_id
            pinned = self._state.pinned_profile_id
            for profile in profiles:
                profile.active = profile.profile_id == active
                profile.pinned = profile.profile_id == pinned
            return profiles

    def get_profile(self, profile_id: str) -> ProfileDetail | None:
        with self._lock:
            summary = self._state.profiles.get(profile_id)
            if summary is None:
                return None
            data = summary.model_copy(deep=True)
            data.active = profile_id == self._state.active_profile_id
            data.pinned = profile_id == self._state.pinned_profile_id
            return ProfileDetail(
                **data.model_dump(),
                provenance={},
                attestations={},
            )

    def _require_srv_type(self, name: str) -> Any:
        srv = self._srv_types.get(name)
        if srv is None:
            raise ApiError(
                "ROS_UNAVAILABLE",
                "ROS service types are not loaded; bridge is not in ROS mode",
                status_code=503,
                retryable=False,
                details={"service": name},
                remediation="Enable ROS and ensure perceptshift_msgs is on PYTHONPATH",
            )
        return srv

    def set_policy(self, patch: dict[str, Any]) -> RuntimePolicy:
        """Call UpdateRuntimePolicy; only mutate local policy after acceptance."""
        filtered = {k: v for k, v in patch.items() if v is not None}
        if not filtered:
            return self.runtime_policy()

        request = self._require_srv_type("policy").Request()
        if "deadline_ms" in filtered:
            request.deadline_ms = float(filtered["deadline_ms"])
            request.apply_deadline = True
        # Remaining ROS fields are left unset/false unless later API schema expands.
        response = self._call_service("policy", request)
        if not bool(getattr(response, "accepted", False)):
            raise ApiError(
                "ROS_SERVICE_REJECTED",
                getattr(response, "error_message", None) or "UpdateRuntimePolicy rejected",
                status_code=409,
                retryable=False,
                details={
                    "error_code": getattr(response, "error_code", ""),
                    "service": "update_runtime_policy",
                },
            )

        with self._lock:
            data = self._state.policy.model_dump()
            data.update(filtered)
            data["source"] = "operator"
            if "deadline_ms" in filtered:
                self._state.deadline_ms = float(filtered["deadline_ms"])
            self._state.policy = RuntimePolicy(**data)
            return self._state.policy.model_copy(deep=True)

    def pin_profile(self, profile_id: str) -> None:
        request = self._require_srv_type("pin").Request()
        request.profile_id = profile_id
        request.duration_seconds = int(self._pin_duration_seconds)
        request.reason = "operator_api"
        response = self._call_service("pin", request)
        if not bool(getattr(response, "accepted", False)):
            raise ApiError(
                "ROS_SERVICE_REJECTED",
                getattr(response, "error_message", None) or "PinProfile rejected",
                status_code=409,
                retryable=False,
                details={
                    "error_code": getattr(response, "error_code", ""),
                    "service": "pin_profile",
                    "profile_id": profile_id,
                },
            )
        with self._lock:
            self._state.pinned_profile_id = profile_id
            self._state.policy.pinned_profile_id = profile_id

    def clear_pin(self) -> None:
        request = self._require_srv_type("clear_pin").Request()
        request.reason = "operator_api"
        response = self._call_service("clear_pin", request)
        if not bool(getattr(response, "success", False)):
            raise ApiError(
                "ROS_SERVICE_REJECTED",
                getattr(response, "error_message", None) or "ClearProfilePin rejected",
                status_code=409,
                retryable=False,
                details={
                    "error_code": getattr(response, "error_code", ""),
                    "service": "clear_profile_pin",
                },
            )
        with self._lock:
            self._state.pinned_profile_id = None
            self._state.policy.pinned_profile_id = None

    def recovery(self, action: str) -> dict[str, Any]:
        if action == "clear_control_hold":
            reason = "clear_control_hold"
            reload_bundle = False
        elif action == "reload_profiles":
            reason = "reload_profiles"
            reload_bundle = True
        else:
            raise ApiError(
                "VALIDATION_ERROR",
                f"Unsupported recovery action '{action}'",
                status_code=422,
            )
        request = self._require_srv_type("recovery").Request()
        request.reason = reason
        request.reload_bundle = reload_bundle
        response = self._call_service("recovery", request)
        if not bool(getattr(response, "accepted", False)):
            raise ApiError(
                "ROS_SERVICE_REJECTED",
                getattr(response, "error_message", None) or "RequestRecovery rejected",
                status_code=409,
                retryable=False,
                details={
                    "error_code": getattr(response, "error_code", ""),
                    "service": "request_recovery",
                    "resulting_health_reason": getattr(response, "resulting_health_reason", ""),
                },
            )
        with self._lock:
            if action == "clear_control_hold":
                self._state.control_hold = False
            resulting = str(getattr(response, "resulting_health_reason", "") or "")
            if resulting:
                self._state.reason_codes = [resulting]
                self._state.health_state = "recovering"
        return {
            "action": action,
            "status": "accepted",
            "resulting_health_reason": getattr(response, "resulting_health_reason", None),
        }

    def seed_profile(self, profile: ProfileSummary) -> None:
        """Test helper: inject a profile into local state without fabricating metrics."""
        if not allow_test_hooks():
            raise RuntimeError("seed_profile is test-only")
        with self._lock:
            self._state.profiles[profile.profile_id] = profile

    def mark_connected_for_tests(self) -> None:
        """Test-only connection flag. Not reachable from production API routes."""
        if not allow_test_hooks():
            raise RuntimeError(
                "mark_connected_for_tests is test-only; set PERCEPTSHIFT_API_ALLOW_TEST_HOOKS=1"
            )
        with self._lock:
            self._state.connected = True
            self._state.available = True
            self._state.mode = "ros"
            self._state.health_state = "healthy"
            self._state.reason_codes = []
            self._state.reason_code = "OK"
            self._state.message = "Connected"
            self._state.last_health_at = _utc_now()
            # Does not enable mutation success; service clients must still respond.
            self._ros_client_ready = False
