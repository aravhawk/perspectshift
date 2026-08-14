"""System and baseline endpoint tests."""

from __future__ import annotations


async def test_healthz(client) -> None:
    ac, _app = client
    response = await ac.get("/api/v1/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readyz_artifact_mode(client) -> None:
    ac, _app = client
    response = await ac.get("/api/v1/readyz")
    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is True
    assert body["database"] is True


async def test_version_and_capabilities(client) -> None:
    ac, _app = client
    version = await ac.get("/api/v1/version")
    assert version.status_code == 200
    assert version.json()["product"] == "perceptshift"

    caps = await ac.get("/api/v1/capabilities")
    assert caps.status_code == 200
    body = caps.json()
    assert body["mutations_enabled"] is False
    assert body["bind_host"] == "127.0.0.1"
    assert body["artifact_store"] is True


async def test_runtime_disconnected_without_ros(client) -> None:
    ac, _app = client
    status = await ac.get("/api/v1/runtime/status")
    assert status.status_code == 200
    body = status.json()
    assert body["connected"] is False
    assert body["mode"] == "artifact_store"
    assert "runtime" in body["unavailable"]
    assert body["unavailable"]["runtime"]["reason_code"] == "ROS_DISABLED"


async def test_empty_profiles_and_runs(client) -> None:
    ac, _app = client
    profiles = await ac.get("/api/v1/profiles")
    assert profiles.status_code == 200
    assert profiles.json() == []

    runs = await ac.get("/api/v1/runs")
    assert runs.status_code == 200
    assert runs.json() == []


async def test_security_headers(client) -> None:
    ac, _app = client
    response = await ac.get("/api/v1/healthz")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'none'" in response.headers["Content-Security-Policy"]
    assert "X-Correlation-ID" in response.headers
