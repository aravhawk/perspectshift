"""WebSocket telemetry streaming tests."""

from __future__ import annotations

from pathlib import Path

from starlette.testclient import TestClient

from perceptshift_api.app import create_app
from perceptshift_api.config import Settings, reset_settings_cache
from perceptshift_api.database import reset_database_state
from perceptshift_api.telemetry import TelemetryHub


async def test_telemetry_recent_empty(client) -> None:
    ac, _app = client
    response = await ac.get("/api/v1/telemetry/recent")
    assert response.status_code == 200
    body = response.json()
    assert "events" in body
    assert body["dropped_event_count"] >= 0


async def test_hub_drops_for_slow_consumer() -> None:
    hub = TelemetryHub(cache_size=32, queue_size=2, max_clients=4)
    sub = await hub.subscribe()
    for i in range(20):
        await hub.publish(
            "inference_trace_summary",
            {"total_ms": float(i), "deadline_miss": False},
        )
    assert hub.dropped_event_count > 0
    assert sub.dropped > 0
    # Queue remains bounded.
    assert sub.queue.qsize() <= 2
    await hub.unsubscribe(sub.client_id)


def test_websocket_stream_smoke(tmp_path: Path) -> None:
    reset_settings_cache()
    reset_database_state()
    data = tmp_path / "data"
    state = tmp_path / "state"
    (data / "runs").mkdir(parents=True)
    state.mkdir(parents=True)
    settings = Settings(
        host="127.0.0.1",
        enable_ros=False,
        data_dir=data,
        state_dir=state,
        artifact_roots=[data / "runs"],
        database_url=f"sqlite:///{state / 'ws.sqlite'}",
        websocket_queue_size=2,
        websocket_max_clients=4,
        telemetry_cache_size=32,
    )
    app = create_app(settings)

    with TestClient(app) as tc, tc.websocket_connect("/api/v1/telemetry/stream") as ws:
        hello = ws.receive_json()
        assert hello["event_type"] == "connection_status"
        assert "dropped_event_count" in hello
        assert hello["payload"]["status"] == "subscribed"

    reset_database_state()
    reset_settings_cache()


async def test_metrics_unavailable_without_samples(client) -> None:
    ac, _app = client
    response = await ac.get("/api/v1/telemetry/metrics")
    assert response.status_code == 200
    body = response.json()
    assert body["sample_count"] == 0
    assert "metrics" in body["unavailable"]
