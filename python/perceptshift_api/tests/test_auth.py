"""Auth, mutation gating, and CORS tests."""

from __future__ import annotations

from unittest.mock import MagicMock

from perceptshift_api.auth import constant_time_token_equals
from perceptshift_api.errors import ApiError


def test_constant_time_comparison() -> None:
    assert constant_time_token_equals("abc", "abc") is True
    assert constant_time_token_equals("abc", "abd") is False
    assert constant_time_token_equals("abc", "ab") is False
    assert constant_time_token_equals("ab", "abc") is False


async def test_mutations_disabled_by_default(client) -> None:
    ac, _app = client
    response = await ac.patch(
        "/api/v1/runtime/policy",
        json={"deadline_ms": 12.5},
    )
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "MUTATIONS_DISABLED"


async def test_mutation_requires_bearer(auth_client) -> None:
    ac, _app, token = auth_client
    missing = await ac.patch("/api/v1/runtime/policy", json={"deadline_ms": 10.0})
    assert missing.status_code == 401
    assert missing.json()["error"]["code"] == "AUTH_REQUIRED"

    invalid = await ac.patch(
        "/api/v1/runtime/policy",
        json={"deadline_ms": 10.0},
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert invalid.status_code == 401
    assert invalid.json()["error"]["code"] == "AUTH_INVALID"

    # Authenticated but ROS graph/client absent: mutation must not claim success.
    ok = await ac.patch(
        "/api/v1/runtime/policy",
        json={"deadline_ms": 10.0},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert ok.status_code in {503, 409, 400, 500, 504}
    body = ok.json()
    assert "error" in body
    assert body["error"]["code"] in {
        "ROS_UNAVAILABLE",
        "ROS_SERVICE_FAILED",
        "ROS_SERVICE_UNAVAILABLE",
        "ROS_TIMEOUT",
        "INTERNAL_ERROR",
        "RUNTIME_UNAVAILABLE",
    }


async def test_pin_and_recovery_with_token(auth_client) -> None:
    ac, app, token = auth_client
    headers = {"Authorization": f"Bearer {token}"}
    pin = await ac.post("/api/v1/profiles/p1/pin", json={"confirm": True}, headers=headers)
    # Without a live ROS client, pin must fail closed (not succeed via local memory).
    assert pin.status_code != 200
    assert "error" in pin.json()

    bridge = app.state.ros_bridge
    # mark_connected_for_tests must not unlock mutations by itself.
    bridge.mark_connected_for_tests()
    still_blocked = await ac.post(
        "/api/v1/profiles/p1/pin", json={"confirm": True}, headers=headers
    )
    assert still_blocked.status_code != 200

    # Auth happy-path shape: stub only the service call boundary (not production routes).
    from perceptshift_api.schemas import RuntimePolicy

    bridge.pin_profile = MagicMock()  # type: ignore[method-assign]
    bridge.clear_pin = MagicMock()  # type: ignore[method-assign]
    bridge.recovery = MagicMock(return_value={"action": "clear_control_hold", "status": "accepted"})  # type: ignore[method-assign]
    bridge.set_policy = MagicMock(  # type: ignore[method-assign]
        return_value=RuntimePolicy(deadline_ms=10.0, source="operator")
    )

    pin2 = await ac.post("/api/v1/profiles/p1/pin", json={"confirm": True}, headers=headers)
    assert pin2.status_code == 200
    assert pin2.json()["pinned_profile_id"] == "p1"
    bridge.pin_profile.assert_called_once_with("p1")

    clear = await ac.delete("/api/v1/profiles/pin", headers=headers)
    assert clear.status_code == 200
    assert clear.json()["pinned_profile_id"] is None
    bridge.clear_pin.assert_called_once()

    recovery = await ac.post(
        "/api/v1/runtime/recovery",
        json={"action": "clear_control_hold", "confirm": True},
        headers=headers,
    )
    assert recovery.status_code == 200
    bridge.recovery.assert_called_once_with("clear_control_hold")


async def test_mark_connected_not_exposed_as_route(client) -> None:
    ac, _app = client
    for path in (
        "/api/v1/runtime/mark_connected_for_tests",
        "/api/v1/test/mark_connected",
        "/api/v1/debug/ros/connect",
    ):
        response = await ac.post(path)
        assert response.status_code in {404, 405, 422}


async def test_cors_denied_by_default(client) -> None:
    ac, _app = client
    response = await ac.get(
        "/api/v1/healthz",
        headers={"Origin": "https://evil.example"},
    )
    assert response.status_code == 200
    assert "access-control-allow-origin" not in {k.lower(): v for k, v in response.headers.items()}


async def test_token_not_in_error_body(auth_client) -> None:
    ac, _app, token = auth_client
    response = await ac.patch(
        "/api/v1/runtime/policy",
        json={"deadline_ms": 1.0},
        headers={"Authorization": f"Bearer {token[:-1]}x"},
    )
    assert token not in response.text


async def test_api_error_from_bridge_propagates(auth_client) -> None:
    ac, app, token = auth_client
    bridge = app.state.ros_bridge

    def boom(_patch):
        raise ApiError("ROS_TIMEOUT", "timed out", status_code=504, retryable=True)

    bridge.set_policy = boom  # type: ignore[method-assign]
    response = await ac.patch(
        "/api/v1/runtime/policy",
        json={"deadline_ms": 11.0},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 504
    assert response.json()["error"]["code"] == "ROS_TIMEOUT"
